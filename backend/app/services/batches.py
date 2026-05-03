"""Group raw Settlement rows into the batch shape exposed on the wire.

Why this lives here. The batch settler emits one Solana tx per (campaign,
publisher) group; multiple Settlement rows share the resulting tx_hash.
The dashboard wants to see one row per batch — confirmed batches collapse
by tx_hash, and pending plays awaiting the next flush collapse by
(campaign, publisher) so the user sees a single "queued" row that flips
into the confirmed batch once the flush lands.

PENDING and FLUSHING rows are normalized to a single "pending" status for
display + grouping — they're the same thing UX-wise (a play hasn't yet
moved on chain). FAILED and NEEDS_REVIEW keep their own bucket per
(campaign, publisher) so they don't get visually mixed with healthy
queued plays. CONFIRMED rows always have a tx_hash and bucket by it.

Used by:
  - app/routers/campaigns.py    — /api/campaigns/{id}/stats.recent_settlements
  - app/routers/dashboard.py    — /api/dashboard-summary.recent_activity

Both call sites overfetch (~RECENT_SETTLEMENTS_FETCH rows) and pass the
list here; we group in Python and slice to RECENT_BATCHES_LIMIT batches.
At demo scale (≤10 campaigns, a few thousand settlements per campaign),
the in-Python grouping is sub-millisecond. PLAN.md tracks the SQL
GROUP BY follow-up for production multi-tenant scale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from ..models import Settlement, SettlementStatus
from ..services.money import micro_str
from ..services.venues import VenuesIndex


# Pull this many raw settlement rows from the DB before grouping. Sized to
# accommodate several flushes' worth of plays (auto-play burst-fires up to
# ~20 plays per 5s tick, so 300 rows ≈ 15 batches' worth at peak).
RECENT_SETTLEMENTS_FETCH = 300

# Max number of batches returned to the dashboard.
RECENT_BATCHES_LIMIT = 10


@dataclass
class _BatchAcc:
    """Mutable accumulator while we walk the row list."""

    id: str
    publisher_wallet: str
    amount_micro: int
    tx_hash: str | None
    status: str
    created_at: datetime
    play_count: int
    device_ids: list[str] = field(default_factory=list)
    campaign_id: str | None = None  # only used by the dashboard variant


def _stamp_utc(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo on read even when the column is DateTime(timezone=True),
    so the value comes back naive. We always write UTC, so attach UTC before
    comparing — otherwise the browser parses the wire string as local time.
    Mirrors the helper inline in the previous routers."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _display_status(raw: str) -> str:
    """Collapse FLUSHING into PENDING for display/grouping. From the
    advertiser's perspective the play is queued in either case; the
    flushing window is a brief implementation detail (~5s)."""
    if raw == SettlementStatus.FLUSHING.value:
        return SettlementStatus.PENDING.value
    return raw


def _batch_key(s: Settlement, display_status: str) -> str:
    """Confirmed batches key on tx_hash (1:1 with the on-chain tx).
    Everything else keys on (status, campaign, publisher) so pending,
    failed, and needs_review never get mixed."""
    if s.tx_hash:
        return s.tx_hash
    return f"{display_status}:{s.campaign_id}:{s.publisher_wallet}"


def _resolve_dmas(device_ids: Iterable[str], venues: VenuesIndex) -> list[str]:
    """Map device_ids → DMA labels, dedupe in first-occurrence order. Returns
    the labels publishers want to keep semi-private as venue-name; only the
    DMA label is surfaced (Session 14 findings)."""
    out: list[str] = []
    seen: set[str] = set()
    for did in device_ids:
        if not did:
            continue
        label = venues.label_for_device(did)
        if label and label not in seen:
            out.append(label)
            seen.add(label)
    return out


def group_settlements_into_batches(
    rows: list[Settlement],
    venues: VenuesIndex,
    *,
    include_campaign_id: bool = False,
) -> list[dict]:
    """Group settlements as described in the module docstring.

    `rows` must be in descending created_at order — the first occurrence of
    each batch key determines its position (and provides the latest
    created_at for the batch). Returns a list of plain dicts so callers can
    spread them into either SettlementSummary or DashboardActivityRow.
    """
    by_key: dict[str, _BatchAcc] = {}
    order: list[str] = []  # preserve first-occurrence order

    for s in rows:
        disp_status = _display_status(s.status)
        key = _batch_key(s, disp_status)
        amt = int(s.amount_usdc)
        existing = by_key.get(key)
        if existing is None:
            acc = _BatchAcc(
                id=key,  # synthetic; React key
                publisher_wallet=s.publisher_wallet,
                amount_micro=amt,
                tx_hash=s.tx_hash,
                status=disp_status,
                created_at=_stamp_utc(s.created_at) or datetime.now(timezone.utc),
                play_count=1,
                device_ids=[s.device_id] if s.device_id else [],
                campaign_id=s.campaign_id if include_campaign_id else None,
            )
            by_key[key] = acc
            order.append(key)
        else:
            existing.amount_micro += amt
            existing.play_count += 1
            if s.device_id:
                existing.device_ids.append(s.device_id)

    out: list[dict] = []
    for key in order:
        acc = by_key[key]
        d: dict = {
            "id": acc.id,
            "publisher_wallet": acc.publisher_wallet,
            "amount_usdc": micro_str(acc.amount_micro),
            "tx_hash": acc.tx_hash,
            "status": acc.status,
            "created_at": acc.created_at.isoformat(),
            "play_count": acc.play_count,
            "dmas": _resolve_dmas(acc.device_ids, venues),
        }
        if include_campaign_id:
            d["campaign_id"] = acc.campaign_id
        out.append(d)
    return out
