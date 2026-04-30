from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..dependencies import AdvertiserIdentity, require_advertiser
from ..models import Campaign, CampaignStatus, Settlement, SettlementStatus
from ..schemas import (
    CampaignStats,
    CampaignSummary,
    CreateCampaignRequest,
    QuoteRequest,
    QuoteResponse,
    RefundResponse,
    SettlementSummary,
    SimulatePlayResponse,
)
from ..services import x402 as x402_service
from ..services.calc import CalcError, compute_quote, required_sol_seed_lamports
from ..services.money import micro_str
from ..services.privy import PrivyClient, PrivyError, get_privy_client
from ..services.solana import (
    build_campaign_bootstrap_tx,
    build_sol_transfer_tx,
    build_usdc_transfer_tx,
    get_sol_lamports,
    wait_for_tx_confirmation,
)
from ..services.tokens import ProofContextClaims
from ..services.venues import get_venues_index
from .proof import execute_settlement

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

RECENT_SETTLEMENTS_LIMIT = 10


def _solscan_tx_url(tx_hash: str | None) -> str | None:
    if not tx_hash:
        return None
    return f"https://solscan.io/tx/{tx_hash}?cluster=devnet"


def _to_summary(c: Campaign) -> CampaignSummary:
    budget_micro = int(c.budget)
    spent_micro = int(c.spent)
    return CampaignSummary(
        id=c.id,
        name=c.name,
        status=c.status,
        budget=micro_str(budget_micro),
        spent=micro_str(spent_micro),
        remaining=micro_str(budget_micro - spent_micro),
        wallet_address=c.wallet_address,
        target_dmas=c.target_dmas,
        start_date=c.start_date,
        end_date=c.end_date,
        protocol_fee_amount=(
            micro_str(int(c.protocol_fee_amount))
            if c.protocol_fee_amount is not None
            else None
        ),
        protocol_fee_tx_hash=c.protocol_fee_tx_hash,
        protocol_fee_solscan_url=_solscan_tx_url(c.protocol_fee_tx_hash),
    )


def _to_settlement_summary(s: Settlement) -> SettlementSummary:
    # SQLite drops tzinfo on read even when the column is DateTime(timezone=True),
    # so the value comes back naive. We always write UTC (_utcnow), so attach
    # UTC before isoformat — otherwise the browser parses the wire string as
    # local time and rows look "3h ago" the moment they're created.
    created = s.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    dma = (
        get_venues_index().label_for_device(s.device_id) if s.device_id else None
    )
    return SettlementSummary(
        id=s.id,
        nonce=s.nonce,
        publisher_wallet=s.publisher_wallet,
        amount_usdc=micro_str(int(s.amount_usdc)),
        tx_hash=s.tx_hash,
        solscan_url=_solscan_tx_url(s.tx_hash),
        status=s.status,
        created_at=created.isoformat() if created else "",
        dma=dma,
    )


def _owned_campaign(
    db: Session, campaign_id: str, advertiser: AdvertiserIdentity
) -> Campaign:
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="campaign not found")
    if c.advertiser_id != advertiser.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your campaign")
    return c


async def _resolve_advertiser_wallet(
    advertiser: AdvertiserIdentity, privy: PrivyClient
) -> str:
    if advertiser.wallet_address:
        return advertiser.wallet_address
    addr = await privy.get_user_solana_wallet(advertiser.user_id)
    if not addr:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no Solana wallet linked to this Privy user",
        )
    advertiser.wallet_address = addr
    return addr


# ---------------------------------------------------------------------------
# Quote — Session 15
# ---------------------------------------------------------------------------


@router.post("/quote", response_model=QuoteResponse)
def quote_campaign(
    body: QuoteRequest,
    _advertiser: AdvertiserIdentity = Depends(require_advertiser),
) -> QuoteResponse:
    """Calculator endpoint for the wizard.

    Server-derived breakdown — clients can't tamper with the budget. The same
    `compute_quote` runs on POST /api/campaigns to determine the actual escrow
    amount (so the dashboard's preview always matches what gets charged).

    Session 16.9: Quote internals are int micro; wire fields are micro strings
    under their legacy names (cpm_price / total_usdc / protocol_fee_usdc /
    total_to_escrow_usdc) so frontend type changes stay diff-mechanical.
    """
    try:
        q = compute_quote(body.target_dmas, body.start_date, body.end_date)
    except CalcError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return QuoteResponse(
        screens=q.screens,
        plays_per_screen_per_day=q.plays_per_screen_per_day,
        days=q.days,
        total_plays=q.total_plays,
        cpm_price=micro_str(q.cpm_price_micro),
        total_usdc=micro_str(q.total_micro),
        protocol_fee_pct=q.protocol_fee_pct,
        protocol_fee_usdc=micro_str(q.protocol_fee_micro),
        total_to_escrow_usdc=micro_str(q.total_to_escrow_micro),
    )


# ---------------------------------------------------------------------------
# Create (x402 handshake) — Session 3
# ---------------------------------------------------------------------------


@router.post("")
async def create_campaign(
    body: CreateCampaignRequest,
    request: Request,
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    privy: PrivyClient = Depends(get_privy_client),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    """
    Two-step x402 flow: first call creates draft + wallet, returns 402;
    retry with X-PAYMENT verifies via facilitator and activates.
    """
    x_payment = request.headers.get("x-payment")
    advertiser_wallet = await _resolve_advertiser_wallet(advertiser, privy)

    # Compute the escrow breakdown server-side. Same call the wizard's /quote
    # endpoint runs; clients can't tamper with the budget number.
    try:
        quote = compute_quote(body.target_dmas, body.start_date, body.end_date)
    except CalcError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not x_payment:
        if not (settings.treasury_wallet_id and settings.treasury_wallet_address):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="treasury not configured — run scripts/bootstrap_treasury.py",
            )

        try:
            wallet = await privy.create_solana_wallet(
                idempotency_key=f"campaign-{advertiser.user_id}-{body.name}-{uuid4().hex[:8]}"
            )
        except PrivyError as e:
            logger.exception("privy create_solana_wallet failed for advertiser=%s", advertiser.user_id)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

        # Bootstrap the fresh campaign wallet in a single tx: seed SOL (so it
        # can pay its own fees on /proof + refund) AND create its USDC ATA
        # (the x402-solana client refuses to build its transfer tx unless the
        # destination's ATA already exists). Must confirm before returning 402.
        #
        # SOL seed is right-sized to the campaign's expected play count (see
        # services/calc.required_sol_seed_lamports). A campaign that runs
        # auto-play to completion drains all of this seeded SOL into validator
        # fees; partial-play refunds are swept back to treasury at refund time.
        seed_lamports = required_sol_seed_lamports(quote.total_plays)
        try:
            bootstrap_tx_b64 = await build_campaign_bootstrap_tx(
                funder_address=settings.treasury_wallet_address,
                beneficiary_address=wallet["address"],
                lamports=seed_lamports,
            )
            bootstrap_sig = await privy.sign_and_send_solana(
                wallet_id=settings.treasury_wallet_id,
                transaction_base64=bootstrap_tx_b64,
                reference_id=f"campaign-bootstrap-{wallet['id']}",
            )
            confirmed = await wait_for_tx_confirmation(bootstrap_sig, timeout_seconds=45.0)
            if not confirmed:
                raise RuntimeError(
                    f"bootstrap tx {bootstrap_sig} did not confirm in time"
                )
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "bootstrap campaign wallet %s failed", wallet["address"]
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"campaign wallet bootstrap failed: {e}",
            ) from e

        # Commit the draft only after bootstrap succeeds, so a failed bootstrap
        # doesn't leave a zombie DRAFT row that the retry path would pick up.
        # `budget` is the playable amount (total minus fee) so /bid + /proof's
        # remaining-budget math doesn't have to know about the fee. The
        # campaign wallet receives `budget + fee` from x402 settle, then we
        # immediately transfer `fee` out to the protocol-revenue wallet on the
        # retry path. CPM is locked at DEMO_CPM; duration is the standard 15s
        # spot length (kept on the model so the bid response still surfaces it).
        campaign = Campaign(
            id=str(uuid4()),
            advertiser_id=advertiser.user_id,
            advertiser_wallet=advertiser_wallet,
            name=body.name,
            creative_url=body.creative_url,
            creative_id=body.creative_id,
            cpm_price=quote.cpm_price_micro,
            budget=quote.total_micro,
            spent=0,
            status=CampaignStatus.DRAFT.value,
            wallet_id=wallet["id"],
            wallet_address=wallet["address"],
            duration=15,
            target_dmas=list(body.target_dmas),
            start_date=body.start_date,
            end_date=body.end_date,
            protocol_fee_amount=quote.protocol_fee_micro,
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)

        try:
            facilitator_fee_payer = await x402_service.get_facilitator_fee_payer()
        except x402_service.X402Error as e:
            logger.exception("facilitator fee payer lookup failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
            ) from e

        # Charge total_to_escrow (budget + 2.5% fee). The campaign wallet
        # receives this full amount; the fee gets transferred out to
        # PROTOCOL_REVENUE_WALLET on the retry path right after settle confirms.
        requirements = x402_service.build_payment_requirements(
            amount_micro=quote.total_to_escrow_micro,
            pay_to_address=wallet["address"],
            resource_url=str(request.url),
            description=f"Fund campaign {body.name}",
            fee_payer=facilitator_fee_payer,
        )
        return JSONResponse(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            content=x402_service.build_402_body([requirements]),
        )

    try:
        payment_payload = x402_service.decode_payment_header(x_payment)
    except x402_service.X402Error as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.advertiser_id == advertiser.user_id,
            Campaign.status == CampaignStatus.DRAFT.value,
        )
        .order_by(Campaign.created_at.desc())
        .first()
    )
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no draft campaign found to fund — call without X-PAYMENT first",
        )

    try:
        facilitator_fee_payer = await x402_service.get_facilitator_fee_payer()
    except x402_service.X402Error as e:
        logger.exception("facilitator fee payer lookup failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        ) from e

    # Reproduce the exact amount the original 402 emitted so the facilitator
    # /verify matches the client's signed payload. budget + fee == total escrow.
    # Integer micro arithmetic produces bit-identical bytes vs. the original.
    escrow_amount_micro = int(campaign.budget) + int(campaign.protocol_fee_amount or 0)
    requirements = x402_service.build_payment_requirements(
        amount_micro=escrow_amount_micro,
        pay_to_address=campaign.wallet_address,
        resource_url=str(request.url),
        description=f"Fund campaign {campaign.name}",
        fee_payer=facilitator_fee_payer,
    )

    try:
        verify_result = await x402_service.verify(payment_payload, requirements)
    except x402_service.X402Error as e:
        logger.exception("x402 verify failed for campaign=%s", campaign.id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    if not verify_result.get("isValid"):
        logger.warning(
            "x402 verify invalid campaign=%s reason=%s",
            campaign.id,
            verify_result.get("invalidReason"),
        )
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"verify failed: {verify_result.get('invalidReason', 'unknown')}",
        )

    try:
        settle_result = await x402_service.settle(payment_payload, requirements)
    except x402_service.X402Error as e:
        logger.exception("x402 settle failed for campaign=%s", campaign.id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    if not settle_result.get("success"):
        logger.warning(
            "x402 settle unsuccessful campaign=%s reason=%s",
            campaign.id,
            settle_result.get("errorReason"),
        )
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"settle failed: {settle_result.get('errorReason', 'unknown')}",
        )

    # Settle confirmed — campaign wallet now holds budget + fee. Transfer the
    # fee out to the protocol-revenue wallet. Best-effort: a failure here
    # leaves the fee sitting in the campaign wallet (will be returned to the
    # advertiser on refund), logs at exception level, but the campaign still
    # flips ACTIVE. Hackathon scope; production would want a retry queue
    # similar to services/retry.py for failed settlements.
    fee_amount_micro = int(campaign.protocol_fee_amount or 0)
    if fee_amount_micro > 0 and settings.protocol_revenue_wallet_address:
        try:
            fee_tx_b64 = await build_usdc_transfer_tx(
                from_address=campaign.wallet_address,
                to_address=settings.protocol_revenue_wallet_address,
                amount_micro=fee_amount_micro,
            )
            campaign.protocol_fee_tx_hash = await privy.sign_and_send_solana(
                wallet_id=campaign.wallet_id,
                transaction_base64=fee_tx_b64,
                reference_id=f"protocol-fee-{campaign.id}",
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "protocol fee transfer failed campaign=%s amount_micro=%d — campaign still activates",
                campaign.id,
                fee_amount_micro,
            )

    campaign.status = CampaignStatus.ACTIVE.value
    db.commit()
    db.refresh(campaign)

    # mode="json" serializes date/datetime to ISO strings — needed because
    # JSONResponse goes through plain json.dumps (no Pydantic encoder hook).
    response = JSONResponse(content=_to_summary(campaign).model_dump(mode="json"))
    response.headers["X-PAYMENT-RESPONSE"] = str(settle_result.get("transaction", ""))
    return response


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@router.get("", response_model=list[CampaignSummary])
def list_campaigns(
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    db: Session = Depends(get_db),
) -> list[CampaignSummary]:
    rows = (
        db.query(Campaign)
        .filter(
            Campaign.advertiser_id == advertiser.user_id,
            Campaign.status != CampaignStatus.DRAFT.value,
        )
        .order_by(Campaign.created_at.desc())
        .all()
    )
    return [_to_summary(c) for c in rows]


@router.get("/{campaign_id}", response_model=CampaignSummary)
def get_campaign(
    campaign_id: str,
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    db: Session = Depends(get_db),
) -> CampaignSummary:
    return _to_summary(_owned_campaign(db, campaign_id, advertiser))


@router.get("/{campaign_id}/stats", response_model=CampaignStats)
def campaign_stats(
    campaign_id: str,
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    db: Session = Depends(get_db),
) -> CampaignStats:
    c = _owned_campaign(db, campaign_id, advertiser)

    # Session 16.8: count pending + flushing + confirmed + needs_review for
    # play-counting purposes (the play happened the moment /proof returned;
    # settlement state is an implementation detail). FLUSHING is the brief
    # window while the batch_settler is broadcasting; NEEDS_REVIEW is a
    # stuck row awaiting operator triage. From the publisher/impression
    # perspective both still represent a play that happened. USDC totals
    # stay confirmed-only — that's money-actually-moved-on-chain.
    counted_statuses = (
        SettlementStatus.PENDING.value,
        SettlementStatus.FLUSHING.value,
        SettlementStatus.CONFIRMED.value,
        SettlementStatus.NEEDS_REVIEW.value,
    )
    total_plays = (
        db.query(func.count(Settlement.id))
        .filter(
            Settlement.campaign_id == c.id,
            Settlement.status.in_(counted_statuses),
        )
        .scalar()
        or 0
    )
    total_confirmed_usdc = (
        db.query(func.coalesce(func.sum(Settlement.amount_usdc), 0))
        .filter(
            Settlement.campaign_id == c.id,
            Settlement.status == SettlementStatus.CONFIRMED.value,
        )
        .scalar()
        or 0
    )
    pending_plays = (
        db.query(func.count(Settlement.id))
        .filter(
            Settlement.campaign_id == c.id,
            Settlement.status.in_(
                (
                    SettlementStatus.PENDING.value,
                    SettlementStatus.FLUSHING.value,
                )
            ),
        )
        .scalar()
        or 0
    )

    recent = (
        db.query(Settlement)
        .filter(Settlement.campaign_id == c.id)
        .order_by(Settlement.created_at.desc())
        .limit(RECENT_SETTLEMENTS_LIMIT)
        .all()
    )
    cutoff_24h = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        hours=24
    )
    last_24h_plays = (
        db.query(Settlement)
        .filter(
            Settlement.campaign_id == c.id,
            Settlement.status.in_(counted_statuses),
            Settlement.created_at >= cutoff_24h,
        )
        .count()
    )

    # Lifetime per-DMA play counts. Drives the live activity map's per-marker
    # tween. NULL device_id rows (legacy + auto-play before Session 16.5) are
    # dropped by the GROUP BY same as before; devices no longer in the venues
    # file resolve to None and bucket under "Unknown". Counts pending +
    # confirmed so the map ticks at /proof time, not at flush time.
    by_device = (
        db.query(Settlement.device_id, func.count(Settlement.id))
        .filter(
            Settlement.campaign_id == c.id,
            Settlement.status.in_(counted_statuses),
            Settlement.device_id.isnot(None),
        )
        .group_by(Settlement.device_id)
        .all()
    )
    venues = get_venues_index()
    plays_by_dma: dict[str, int] = {}
    for device_id, n in by_device:
        label = venues.label_for_device(device_id) or "Unknown"
        plays_by_dma[label] = plays_by_dma.get(label, 0) + int(n)

    budget_micro = int(c.budget)
    spent_micro = int(c.spent)
    return CampaignStats(
        campaign_id=c.id,
        status=c.status,
        budget=micro_str(budget_micro),
        spent=micro_str(spent_micro),
        remaining_budget=micro_str(budget_micro - spent_micro),
        total_plays=int(total_plays),
        last_24h_plays=last_24h_plays,
        pending_plays=int(pending_plays),
        total_confirmed_usdc=micro_str(int(total_confirmed_usdc)),
        cpm_price=micro_str(int(c.cpm_price)),
        target_dmas=c.target_dmas,
        start_date=c.start_date,
        end_date=c.end_date,
        protocol_fee_amount=(
            micro_str(int(c.protocol_fee_amount))
            if c.protocol_fee_amount is not None
            else None
        ),
        protocol_fee_tx_hash=c.protocol_fee_tx_hash,
        protocol_fee_solscan_url=_solscan_tx_url(c.protocol_fee_tx_hash),
        plays_by_dma=plays_by_dma,
        recent_settlements=[_to_settlement_summary(s) for s in recent],
    )


@router.get("/{campaign_id}/settlements", response_model=list[SettlementSummary])
def campaign_settlements(
    campaign_id: str,
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    db: Session = Depends(get_db),
) -> list[SettlementSummary]:
    c = _owned_campaign(db, campaign_id, advertiser)
    rows = (
        db.query(Settlement)
        .filter(Settlement.campaign_id == c.id)
        .order_by(Settlement.created_at.desc())
        .all()
    )
    return [_to_settlement_summary(s) for s in rows]


# ---------------------------------------------------------------------------
# Lifecycle actions
# ---------------------------------------------------------------------------


@router.post("/{campaign_id}/pause", response_model=CampaignSummary)
def pause_campaign(
    campaign_id: str,
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    db: Session = Depends(get_db),
) -> CampaignSummary:
    c = _owned_campaign(db, campaign_id, advertiser)
    if c.status != CampaignStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"can only pause active campaigns (current: {c.status})",
        )
    c.status = CampaignStatus.PAUSED.value
    db.commit()
    db.refresh(c)
    return _to_summary(c)


@router.post("/{campaign_id}/resume", response_model=CampaignSummary)
def resume_campaign(
    campaign_id: str,
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    db: Session = Depends(get_db),
) -> CampaignSummary:
    c = _owned_campaign(db, campaign_id, advertiser)
    if c.status != CampaignStatus.PAUSED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"can only resume paused campaigns (current: {c.status})",
        )
    if int(c.budget) - int(c.spent) <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="campaign has no remaining budget — refund instead of resume",
        )
    c.status = CampaignStatus.ACTIVE.value
    db.commit()
    db.refresh(c)
    return _to_summary(c)


@router.post("/{campaign_id}/refund", response_model=RefundResponse)
async def refund_campaign(
    campaign_id: str,
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    privy: PrivyClient = Depends(get_privy_client),
    db: Session = Depends(get_db),
) -> RefundResponse:
    c = _owned_campaign(db, campaign_id, advertiser)

    if c.status == CampaignStatus.REFUNDED.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already refunded")
    refundable = {
        CampaignStatus.PAUSED.value,
        CampaignStatus.COMPLETED.value,
        CampaignStatus.EXPIRED.value,
    }
    if c.status not in refundable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"pause the campaign before refunding (current: {c.status})",
        )

    # Session 16.8: drain any pending settlements for this campaign before
    # computing the refund amount. `spent` already reflects them (the /proof
    # atomic UPDATE reserves budget at queue time), but the on-chain USDC
    # they're owed is still sitting in the campaign wallet. If we refunded
    # without flushing first, the pending batch tx would later try to pay
    # the publisher from a wallet whose USDC just walked back to the
    # advertiser → tx fails on insufficient balance, drift forms.
    #
    # If the flush itself can't make progress (RPC blind), bail with 503;
    # the advertiser retries shortly and the next batch loop will catch up.
    from ..services.batch_settler import flush_campaign as _flush_campaign

    flush_result = await _flush_campaign(c.id, privy=privy)
    if flush_result.left_pending_rows > 0 or flush_result.failures:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"pending settlements not yet flushed "
                f"(pending={flush_result.left_pending_rows}, "
                f"failures={len(flush_result.failures)}); retry refund shortly"
            ),
        )

    # Refuse refund if any rows are NEEDS_REVIEW — those have ambiguous
    # on-chain state. Refunding now would either over-pay (if the original
    # broadcast landed and we send `budget - spent` not knowing the wallet
    # already paid out) or under-credit the publisher (if the broadcast
    # didn't land). Operator must triage via scripts/triage_stuck.py first.
    needs_review_count = (
        db.query(Settlement)
        .filter(
            Settlement.campaign_id == c.id,
            Settlement.status == SettlementStatus.NEEDS_REVIEW.value,
        )
        .count()
    )
    if needs_review_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"campaign has {needs_review_count} settlement(s) requiring manual "
                f"review (run scripts/triage_stuck.py before refunding)"
            ),
        )

    # Re-load post-flush so `spent` reflects everything paid out.
    db.refresh(c)

    remaining_micro = int(c.budget) - int(c.spent)
    if remaining_micro <= 0:
        c.status = CampaignStatus.REFUNDED.value
        db.commit()
        return RefundResponse(refund_amount=micro_str(0), tx_hash=None, solscan_url=None)

    if not c.advertiser_wallet:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="advertiser_wallet missing on campaign — cannot refund",
        )

    settings = get_settings()
    try:
        tx_b64 = await build_usdc_transfer_tx(
            from_address=c.wallet_address,
            to_address=c.advertiser_wallet,
            amount_micro=remaining_micro,
        )
        tx_hash = await privy.sign_and_send_solana(
            wallet_id=c.wallet_id,
            transaction_base64=tx_b64,
            reference_id=f"refund-{c.id}",
        )
    except PrivyError as e:
        logger.exception("refund failed for campaign=%s wallet=%s", c.id, c.wallet_id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    c.status = CampaignStatus.REFUNDED.value
    c.refund_tx_hash = tx_hash
    db.commit()

    # Best-effort SOL sweep back to treasury. The campaign wallet was
    # right-sized at creation (services/calc.required_sol_seed_lamports);
    # whatever didn't get burned on validator fees over the campaign's
    # life should return to treasury rather than sit stranded forever
    # (Privy doesn't support wallet deletion).
    if settings.treasury_wallet_address:
        try:
            await wait_for_tx_confirmation(tx_hash, timeout_seconds=30.0)
            sol_lamports = await get_sol_lamports(c.wallet_address)
            sweep_lamports = max(0, sol_lamports - 10_000)  # leave 2 fees worth
            if sweep_lamports > 0:
                sol_tx_b64 = await build_sol_transfer_tx(
                    from_address=c.wallet_address,
                    to_address=settings.treasury_wallet_address,
                    lamports=sweep_lamports,
                )
                sol_sweep_hash = await privy.sign_and_send_solana(
                    wallet_id=c.wallet_id,
                    transaction_base64=sol_tx_b64,
                    reference_id=f"refund-sol-{c.id}",
                )
                logger.info(
                    "refund SOL sweep campaign=%s lamports=%d tx=%s",
                    c.id,
                    sweep_lamports,
                    sol_sweep_hash,
                )
        except Exception:  # noqa: BLE001 — non-blocking, just log
            logger.exception(
                "refund SOL sweep failed (non-blocking) campaign=%s wallet=%s",
                c.id,
                c.wallet_id,
            )

    return RefundResponse(
        refund_amount=micro_str(remaining_micro),
        tx_hash=tx_hash,
        solscan_url=_solscan_tx_url(tx_hash),
    )


@router.post("/{campaign_id}/simulate-play", response_model=SimulatePlayResponse)
async def simulate_play(
    campaign_id: str,
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> SimulatePlayResponse:
    """Dashboard-only helper: mint a proof_context server-side and settle it.

    Production publishers call /bid + /proof themselves with their own API key;
    this endpoint exists so the demo dashboard can drive an end-to-end "ad played"
    event without exposing the publisher API key in the browser. Ownership of the
    campaign is required (same auth as the rest of /api/campaigns).
    """
    c = _owned_campaign(db, campaign_id, advertiser)
    if c.status != CampaignStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"campaign not active: {c.status}",
        )
    amount_micro = int(c.cpm_price) // 1000
    if int(c.budget) - int(c.spent) < amount_micro:
        raise HTTPException(status_code=400, detail="insufficient campaign budget")

    # Schedule window must contain today (mirrors /bid).
    today = datetime.now(timezone.utc).date()
    if c.start_date is not None and c.start_date > today:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"campaign starts {c.start_date} (not yet eligible)",
        )
    if c.end_date is not None and c.end_date < today:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"campaign ended {c.end_date} (refund instead)",
        )

    if not c.target_dmas:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="campaign has no target DMAs",
        )
    device = get_venues_index().pick_random_device(list(c.target_dmas))
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no devices available for the campaign's target DMAs",
        )

    claims = ProofContextClaims(
        campaign_id=c.id,
        bid_id=f"simulate-{uuid4().hex[:8]}",
        wallet_id=settings.demo_publisher_wallet,
        nonce=f"simulate-{uuid4().hex}",
        created_at=int(time.time()),
        amount_micro=amount_micro,
        device_id=device["device_id"],
    )

    # Session 16.8: queue-only. tx_hash is None at this point — the
    # batch_settler emits the actual on-chain transfer within
    # BATCH_FLUSH_INTERVAL_SECONDS. UI shows the row as "queued" until then.
    row = await execute_settlement(claims, db)
    return SimulatePlayResponse(
        amount_usdc=micro_str(amount_micro),
        tx_hash=None,
        solscan_url=None,
        publisher_wallet=settings.demo_publisher_wallet,
        dma=device["dma"],
        settlement_id=row.id,
        status=row.status,
    )
