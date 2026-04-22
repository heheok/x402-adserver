from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import AdvertiserIdentity, require_advertiser
from ..models import Campaign, CampaignStatus, Settlement, SettlementStatus
from ..schemas import (
    CampaignStats,
    CampaignSummary,
    CreateCampaignRequest,
    RefundResponse,
    SettlementSummary,
)
from ..services import x402 as x402_service
from ..services.privy import PrivyClient, PrivyError, get_privy_client
from ..services.solana import airdrop_sol, build_usdc_transfer_tx

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

RECENT_SETTLEMENTS_LIMIT = 10


def _solscan_tx_url(tx_hash: str | None) -> str | None:
    if not tx_hash:
        return None
    return f"https://solscan.io/tx/{tx_hash}?cluster=devnet"


def _to_summary(c: Campaign) -> CampaignSummary:
    return CampaignSummary(
        id=c.id,
        name=c.name,
        status=c.status,
        budget=float(c.budget),
        spent=float(c.spent),
        remaining=float(c.budget) - float(c.spent),
        wallet_address=c.wallet_address,
    )


def _to_settlement_summary(s: Settlement) -> SettlementSummary:
    return SettlementSummary(
        id=s.id,
        nonce=s.nonce,
        publisher_wallet=s.publisher_wallet,
        amount_usdc=float(s.amount_usdc),
        tx_hash=s.tx_hash,
        solscan_url=_solscan_tx_url(s.tx_hash),
        status=s.status,
        created_at=s.created_at.isoformat() if s.created_at else "",
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
# Create (x402 handshake) — Session 3
# ---------------------------------------------------------------------------


@router.post("")
async def create_campaign(
    body: CreateCampaignRequest,
    request: Request,
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    privy: PrivyClient = Depends(get_privy_client),
    db: Session = Depends(get_db),
):
    """
    Two-step x402 flow: first call creates draft + wallet, returns 402;
    retry with X-PAYMENT verifies via facilitator and activates.
    """
    x_payment = request.headers.get("x-payment")
    advertiser_wallet = await _resolve_advertiser_wallet(advertiser, privy)

    if not x_payment:
        try:
            wallet = await privy.create_solana_wallet(
                idempotency_key=f"campaign-{advertiser.user_id}-{body.name}-{uuid4().hex[:8]}"
            )
        except PrivyError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

        campaign = Campaign(
            id=str(uuid4()),
            advertiser_id=advertiser.user_id,
            advertiser_wallet=advertiser_wallet,
            name=body.name,
            creative_url=body.creative_url,
            creative_id=body.creative_id,
            cpm_price=body.cpm_price,
            budget=body.budget,
            spent=0.0,
            status=CampaignStatus.DRAFT.value,
            wallet_id=wallet["id"],
            wallet_address=wallet["address"],
            duration=body.duration,
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)

        try:
            await airdrop_sol(wallet["address"], 1.0)
        except Exception:  # noqa: BLE001
            pass

        requirements = x402_service.build_payment_requirements(
            amount_usdc=body.budget,
            pay_to_address=wallet["address"],
            resource_url=str(request.url),
            description=f"Fund campaign {body.name}",
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

    requirements = x402_service.build_payment_requirements(
        amount_usdc=float(campaign.budget),
        pay_to_address=campaign.wallet_address,
        resource_url=str(request.url),
        description=f"Fund campaign {campaign.name}",
    )

    try:
        verify_result = await x402_service.verify(payment_payload, requirements)
    except x402_service.X402Error as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    if not verify_result.get("isValid"):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"verify failed: {verify_result.get('invalidReason', 'unknown')}",
        )

    try:
        settle_result = await x402_service.settle(payment_payload, requirements)
    except x402_service.X402Error as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    if not settle_result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"settle failed: {settle_result.get('errorReason', 'unknown')}",
        )

    campaign.status = CampaignStatus.ACTIVE.value
    db.commit()
    db.refresh(campaign)

    response = JSONResponse(content=_to_summary(campaign).model_dump())
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
        .filter(Campaign.advertiser_id == advertiser.user_id)
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

    confirmed = (
        db.query(Settlement)
        .filter(
            Settlement.campaign_id == c.id,
            Settlement.status == SettlementStatus.CONFIRMED.value,
        )
        .all()
    )
    recent = (
        db.query(Settlement)
        .filter(Settlement.campaign_id == c.id)
        .order_by(Settlement.created_at.desc())
        .limit(RECENT_SETTLEMENTS_LIMIT)
        .all()
    )

    return CampaignStats(
        campaign_id=c.id,
        status=c.status,
        budget=float(c.budget),
        spent=float(c.spent),
        remaining_budget=float(c.budget) - float(c.spent),
        total_plays=len(confirmed),
        total_confirmed_usdc=sum(float(s.amount_usdc) for s in confirmed),
        cpm_price=float(c.cpm_price),
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
    if float(c.budget) - float(c.spent) <= 0:
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
    if c.status not in {CampaignStatus.PAUSED.value, CampaignStatus.COMPLETED.value}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"pause the campaign before refunding (current: {c.status})",
        )

    remaining = float(c.budget) - float(c.spent)
    if remaining <= 0:
        c.status = CampaignStatus.REFUNDED.value
        db.commit()
        return RefundResponse(refund_amount=0.0, tx_hash=None, solscan_url=None)

    if not c.advertiser_wallet:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="advertiser_wallet missing on campaign — cannot refund",
        )

    try:
        tx_b64 = await build_usdc_transfer_tx(
            from_address=c.wallet_address,
            to_address=c.advertiser_wallet,
            amount_usdc=remaining,
        )
        tx_hash = await privy.sign_and_send_solana(
            wallet_id=c.wallet_id,
            transaction_base64=tx_b64,
            reference_id=f"refund-{c.id}",
        )
    except PrivyError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    c.status = CampaignStatus.REFUNDED.value
    c.refund_tx_hash = tx_hash
    db.commit()

    return RefundResponse(
        refund_amount=remaining,
        tx_hash=tx_hash,
        solscan_url=_solscan_tx_url(tx_hash),
    )
