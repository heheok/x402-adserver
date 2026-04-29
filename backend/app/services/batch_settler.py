"""Batch settlement loop (Session 16.8).

Replaces the per-play on-chain settlement model with a `pending → confirmed`
state machine. `/proof`, `/api/campaigns/:id/simulate-play`, and the
auto-play loop all just write a `pending` Settlement row and return
sub-100ms. This background task flushes pending rows every
`batch_flush_interval_seconds`, grouping by `(campaign, publisher_wallet)`
and emitting ONE Solana USDC transfer per group.

Why batch
---------
Per-play on-chain settlement is fragile under load. Public devnet RPC
rate-limits at 4 req/s/method, so 10–20 concurrent settlements per
auto-play tick saturate `getSignatureStatuses` polling — both
`wait_for_tx_confirmation` and the γ_extra final-status check go blind,
return None, and the compensating UPDATE wrongly rolls back txs that
actually landed. Documented in `PLAN.md Session 16.6` and
`BATCH-SETTLEMENTS.md §1`.

The fix isn't tighter retries — the architecture is wrong. Industry
practice (DOOH, RTB ad networks) accrues impressions and settles in
batches. We adopt that.

Correctness invariants (all preserved here):

  1. Replay protection: nonce insert at /proof time. Unchanged.
  2. Budget overcommit: atomic `UPDATE campaigns SET spent + amount` with
     guard at /proof time. Unchanged. Pending rows still hold reserved
     budget.
  3. Drift on RPC blindness: when getSignatureStatuses goes blind, leave
     the rows as `pending` and try again next loop. **Do not compensate.**
     This is the critical correctness rule; it's what fixes the
     opposite-direction drift the α + γ work introduced.
  4. Race with refund: refund handler calls `flush_campaign(id)`
     synchronously before computing `remaining`. Both pickers share an
     atomic claim step (`UPDATE … SET status='flushing' … WHERE
     status='pending'`) so neither double-broadcasts.
  5. Restart resilience: if the backend dies mid-flush, pending or
     flushing rows survive. Privy `reference_id` is deterministic per
     group (`batch-{campaign[:8]}-{first_nonce[:8]}`) — re-broadcasting
     the same group returns the same tx hash via Privy's idempotency.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import case, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..models import Campaign, CampaignStatus, Settlement, SettlementStatus
from ..services.privy import PrivyClient, PrivyError
from ..services.solana import (
    build_usdc_transfer_tx,
    get_signature_status,
    wait_for_tx_confirmation,
)

logger = logging.getLogger(__name__)


# Batch tx polling cadence. Doubled vs. wait_for_tx_confirmation's default
# so multiple concurrent flushes stay under the 4 req/s/method devnet limit
# (see solana.wait_for_tx_confirmation docstring).
BATCH_POLL_INTERVAL_SECONDS = 2.0
BATCH_WAIT_TIMEOUT_SECONDS = 90.0


@dataclass
class FlushResult:
    confirmed_rows: int = 0
    failed_rows: int = 0
    left_pending_rows: int = 0
    failures: list[str] = field(default_factory=list)


def _claim_pending(
    db: Session, ids: list[str]
) -> list[Settlement]:
    """Atomically flip pending → flushing for the given ids and return the
    rows we own. The WHERE clause filters out any row another worker
    already claimed, so concurrent claimers never overlap.
    """
    if not ids:
        return []
    stmt = (
        update(Settlement)
        .where(Settlement.id.in_(ids))
        .where(Settlement.status == SettlementStatus.PENDING.value)
        .values(status=SettlementStatus.FLUSHING.value)
        .execution_options(synchronize_session=False)
    )
    db.execute(stmt)
    db.commit()
    # Read back; only rows whose status is now 'flushing' AND whose id is
    # in our requested set belong to us.
    return (
        db.query(Settlement)
        .filter(Settlement.id.in_(ids))
        .filter(Settlement.status == SettlementStatus.FLUSHING.value)
        .order_by(Settlement.created_at.asc())
        .all()
    )


def _select_pending_ids(
    db: Session, *, limit: int, campaign_id: str | None = None
) -> list[str]:
    q = db.query(Settlement.id).filter(
        Settlement.status == SettlementStatus.PENDING.value
    )
    if campaign_id is not None:
        q = q.filter(Settlement.campaign_id == campaign_id)
    rows = q.order_by(Settlement.created_at.asc()).limit(limit).all()
    return [r[0] for r in rows]


def _group_by_target(
    rows: Iterable[Settlement],
) -> dict[tuple[str, str], list[Settlement]]:
    groups: dict[tuple[str, str], list[Settlement]] = {}
    for r in rows:
        key = (r.campaign_id, r.publisher_wallet)
        groups.setdefault(key, []).append(r)
    return groups


def _mark_confirmed(db: Session, ids: list[str], tx_hash: str) -> None:
    stmt = (
        update(Settlement)
        .where(Settlement.id.in_(ids))
        .values(status=SettlementStatus.CONFIRMED.value, tx_hash=tx_hash)
        .execution_options(synchronize_session=False)
    )
    db.execute(stmt)
    db.commit()


def _mark_back_to_pending(db: Session, ids: list[str]) -> None:
    """Release flushing rows for the next loop tick. Used when the
    on-chain status is unknown (RPC blind) — re-tries are safe because
    Privy's reference_id idempotency means re-broadcasting the same group
    yields the same tx hash, not a duplicate."""
    stmt = (
        update(Settlement)
        .where(Settlement.id.in_(ids))
        .where(Settlement.status == SettlementStatus.FLUSHING.value)
        .values(status=SettlementStatus.PENDING.value)
        .execution_options(synchronize_session=False)
    )
    db.execute(stmt)
    db.commit()


def _compensate_failed(db: Session, rows: list[Settlement]) -> None:
    """Definitive failure path: flip rows to 'failed' AND release the
    reserved budget on each row's campaign. This is the only place
    `spent` gets decremented after the /proof-time atomic UPDATE, and it
    only fires when we have positive evidence the tx will NEVER land
    (e.g. Privy raised at simulation). RPC blindness is NOT this path —
    that returns to pending.
    """
    epsilon = 1e-9
    for r in rows:
        # Per-row compensating UPDATE on the campaign. Mirrors the shape
        # the old execute_settlement used: refund spent and flip
        # COMPLETED → ACTIVE if the refund creates room for one more play
        # at this CPM.
        refund_stmt = (
            update(Campaign)
            .where(Campaign.id == r.campaign_id)
            .values(
                spent=Campaign.spent - float(r.amount_usdc),
                status=case(
                    (
                        (Campaign.status == CampaignStatus.COMPLETED.value)
                        & (
                            Campaign.budget
                            - (Campaign.spent - float(r.amount_usdc))
                            + epsilon
                            >= Campaign.cpm_price / 1000.0
                        ),
                        CampaignStatus.ACTIVE.value,
                    ),
                    else_=Campaign.status,
                ),
            )
            .execution_options(synchronize_session=False)
        )
        db.execute(refund_stmt)
    fail_stmt = (
        update(Settlement)
        .where(Settlement.id.in_([r.id for r in rows]))
        .values(status=SettlementStatus.FAILED.value)
        .execution_options(synchronize_session=False)
    )
    db.execute(fail_stmt)
    db.commit()


async def _flush_group(
    privy: PrivyClient,
    db: Session,
    rows: list[Settlement],
) -> tuple[int, int, int, list[str]]:
    """Process one (campaign, publisher) group. Returns
    (confirmed, failed, left_pending, failure_messages)."""
    if not rows:
        return (0, 0, 0, [])

    campaign = (
        db.query(Campaign).filter(Campaign.id == rows[0].campaign_id).first()
    )
    if campaign is None:
        logger.error(
            "batch flush: campaign %s missing for %d pending rows; marking failed",
            rows[0].campaign_id,
            len(rows),
        )
        _compensate_failed(db, rows)
        return (0, len(rows), 0, ["campaign not found"])

    publisher = rows[0].publisher_wallet
    total_amount = sum(float(r.amount_usdc) for r in rows)
    first_nonce = rows[0].nonce
    row_ids = [r.id for r in rows]

    # Deterministic per-group identifiers. Same group rebuilt across loop
    # ticks (e.g. crash recovery) yields the same reference_id → Privy
    # returns the same tx hash without re-broadcasting. Memo makes the tx
    # bytes-unique across blockhash windows so the network doesn't dedup
    # different batches that happen to hit the same (from, to, amount).
    #
    # CRITICAL: use the FULL first_nonce, not a truncated prefix. Auto-play
    # nonces are "auto-{32 hex}" → first_nonce[:8] = "auto-XYZ" with only 3
    # hex chars of uniqueness (4096 combos). With ~360 batches per campaign
    # over a 30-min soak, birthday-paradox collisions are near-certain →
    # Privy returns 400 "reference_id already exists" → we used to compensate
    # those batches → drift, because Privy's reference_id check is
    # POST-broadcast (per BUSINESS-CONSTRAINTS.md §3): the colliding tx had
    # already broadcast and paid the publisher by the time we saw the 400.
    # Full first_nonce (37 chars for auto-play) has effectively no collision
    # risk. Total reference_id length: 6 + 8 + 1 + 37 = 52 chars (≤64 limit).
    memo = f"x402-batch:{first_nonce[:8]}-{len(rows)}"
    reference_id = f"batch-{campaign.id[:8]}-{first_nonce}"

    tx_hash: str | None = None
    try:
        tx_b64 = await build_usdc_transfer_tx(
            from_address=campaign.wallet_address,
            to_address=publisher,
            amount_usdc=total_amount,
            memo=memo,
        )
        tx_hash = await privy.sign_and_send_solana(
            wallet_id=campaign.wallet_id,
            transaction_base64=tx_b64,
            reference_id=reference_id,
        )
        confirmed = await wait_for_tx_confirmation(
            tx_hash,
            timeout_seconds=BATCH_WAIT_TIMEOUT_SECONDS,
            poll_interval_seconds=BATCH_POLL_INTERVAL_SECONDS,
        )
        if confirmed:
            _mark_confirmed(db, row_ids, tx_hash)
            logger.info(
                "batch flush confirmed campaign=%s publisher=%s rows=%d "
                "amount=%.6f tx=%s",
                campaign.id,
                publisher,
                len(rows),
                total_amount,
                tx_hash,
            )
            return (len(rows), 0, 0, [])

        # Wait timed out without confirmation. Fall through to status check.
        raise RuntimeError(f"tx {tx_hash} broadcast but not confirmed within wait")

    except (PrivyError, RuntimeError, Exception) as e:  # noqa: BLE001
        # γ_extra: if we got a tx_hash, ask the RPC one more time. If it
        # ever appeared, treat the batch as confirmed (late-landed). This
        # MUST not compensate — compensation under RPC blindness was the
        # bug we're fixing.
        if tx_hash is not None:
            final_status = await get_signature_status(tx_hash)
            if final_status in ("processed", "confirmed", "finalized"):
                _mark_confirmed(db, row_ids, tx_hash)
                logger.warning(
                    "batch flush late-landed campaign=%s rows=%d tx=%s "
                    "final_status=%s",
                    campaign.id,
                    len(rows),
                    tx_hash,
                    final_status,
                )
                return (len(rows), 0, 0, [])
            # tx_hash exists but status is None — we broadcast something
            # but don't know its fate. Could be: dropped (definitively
            # dead), in-flight but RPC-blind, or never-saw-it. Safe move:
            # leave pending. Privy reference_id idempotency means the next
            # loop's re-broadcast either returns this same hash (then
            # we'll see status) or — if Privy thinks the prior request
            # itself failed — sends a new tx that supersedes.
            _mark_back_to_pending(db, row_ids)
            logger.warning(
                "batch flush RPC-blind, leaving pending campaign=%s rows=%d "
                "tx=%s err=%s",
                campaign.id,
                len(rows),
                tx_hash,
                e,
            )
            return (0, 0, len(rows), [str(e)])

        # No tx_hash from Privy. Privy's reference_id check is POST-broadcast
        # (BUSINESS-CONSTRAINTS.md §3): for some response codes, the tx may
        # have actually broadcast before Privy errored. We only compensate
        # when we have positive evidence the broadcast did NOT happen —
        # otherwise leave pending and let the next tick retry (or operator
        # intervene). Compensating-on-uncertainty was the original Session
        # 16.6 bug we're solving.
        post_broadcast_uncertain = False
        if isinstance(e, PrivyError):
            if e.status_code >= 500:
                # 5xx (Cloudflare 520/521/522, gateway errors): Privy's
                # frontend dropped the response. The request may have
                # reached origin and broadcast.
                post_broadcast_uncertain = True
            elif e.status_code == 400 and "already exists" in (e.body or ""):
                # Reference_id collision. Privy validates+broadcasts before
                # recording reference_id, so a duplicate ref_id means a tx
                # (this attempt's, or an earlier identical one) was already
                # broadcast. Per Privy docs §3.
                post_broadcast_uncertain = True
        if post_broadcast_uncertain:
            _mark_back_to_pending(db, row_ids)
            logger.warning(
                "batch flush post-broadcast uncertain, leaving pending "
                "campaign=%s rows=%d err=%s",
                campaign.id,
                len(rows),
                e,
            )
            return (0, 0, len(rows), [str(e)])

        # Truly definitive: simulation rejected, invalid wallet, malformed
        # tx, etc. Privy gave a clean refusal pre-broadcast. Compensate.
        logger.exception(
            "batch flush DEFINITIVE failure campaign=%s rows=%d amount=%.6f",
            campaign.id,
            len(rows),
            total_amount,
        )
        _compensate_failed(db, rows)
        return (0, len(rows), 0, [str(e)])


async def flush_all(privy: PrivyClient | None = None) -> FlushResult:
    """Process up to BATCH_MAX_ROWS_PER_FLUSH pending rows. Public entry
    used by the loop and by e2e_demo for manual draining."""
    if privy is None:
        privy = PrivyClient()
    settings = get_settings()
    result = FlushResult()

    db = SessionLocal()
    try:
        ids = _select_pending_ids(db, limit=settings.batch_max_rows_per_flush)
        if not ids:
            return result
        owned = _claim_pending(db, ids)
    finally:
        db.close()

    if not owned:
        return result

    groups = _group_by_target(owned)
    # Process groups sequentially within a tick. Sequential keeps RPC
    # pressure flat (one outstanding wait_for_tx_confirmation at a time);
    # at hackathon scale (1–10 active campaigns) the wall-clock cost is
    # bounded by N_groups × ~confirmation_time, well under the 30s soak
    # interval we expect.
    for group in groups.values():
        db = SessionLocal()
        try:
            ok, fail, pend, errors = await _flush_group(privy, db, group)
            result.confirmed_rows += ok
            result.failed_rows += fail
            result.left_pending_rows += pend
            result.failures.extend(errors)
        finally:
            db.close()
    return result


async def flush_campaign(
    campaign_id: str, privy: PrivyClient | None = None
) -> FlushResult:
    """Drain all pending rows for one campaign synchronously. Called from
    the refund handler so refund's `remaining = budget - spent` math
    reflects everything actually owed to publishers."""
    if privy is None:
        privy = PrivyClient()
    settings = get_settings()
    result = FlushResult()

    # Drain in passes to avoid an unbounded single-pass on a campaign with
    # many pending rows. Each pass claims up to batch_max_rows_per_flush
    # and processes them; loop until there are no more pending rows for
    # this campaign.
    while True:
        db = SessionLocal()
        try:
            ids = _select_pending_ids(
                db,
                limit=settings.batch_max_rows_per_flush,
                campaign_id=campaign_id,
            )
            if not ids:
                break
            owned = _claim_pending(db, ids)
        finally:
            db.close()

        if not owned:
            break

        groups = _group_by_target(owned)
        for group in groups.values():
            db = SessionLocal()
            try:
                ok, fail, pend, errors = await _flush_group(privy, db, group)
                result.confirmed_rows += ok
                result.failed_rows += fail
                result.left_pending_rows += pend
                result.failures.extend(errors)
            finally:
                db.close()

        # If a pass ended with everything left pending (RPC blind), don't
        # spin — give up and let the caller decide what to do.
        if result.left_pending_rows > 0 and result.confirmed_rows == 0 and result.failed_rows == 0:
            break

    return result


async def run_batch_settler_loop(stop_event: asyncio.Event) -> None:
    """Long-running task: ticks forever (until `stop_event` is set)."""
    settings = get_settings()
    if not settings.batch_enabled:
        logger.info("batch settler disabled (BATCH_ENABLED=false)")
        return

    privy = PrivyClient()
    interval = max(1, int(settings.batch_flush_interval_seconds))
    logger.info("batch settler loop starting — interval=%ds", interval)

    while not stop_event.is_set():
        try:
            result = await flush_all(privy)
            if result.confirmed_rows or result.failed_rows or result.left_pending_rows:
                logger.info(
                    "batch settler tick — confirmed=%d failed=%d left_pending=%d",
                    result.confirmed_rows,
                    result.failed_rows,
                    result.left_pending_rows,
                )
        except Exception:
            logger.exception("batch settler tick crashed; continuing")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue

    logger.info("batch settler loop stopped")
