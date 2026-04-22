from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..dependencies import require_publisher_api_key
from ..models import Campaign, CampaignStatus, Settlement, SettlementStatus, UsedNonce
from ..schemas import ProofRequest, ProofResponse
from ..services.privy import PrivyClient, PrivyError, get_privy_client
from ..services.solana import build_usdc_transfer_tx
from ..services.tokens import (
    ProofContextClaims,
    ProofContextError,
    decode_proof_context,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rtb"])

MIN_PLAY_DURATION_SECONDS = 1


def _settlement_row(
    campaign_id: str,
    nonce: str,
    publisher_wallet: str,
    amount_usdc: float,
    tx_hash: str | None,
    status_value: str,
) -> Settlement:
    return Settlement(
        id=str(uuid4()),
        campaign_id=campaign_id,
        nonce=nonce,
        publisher_wallet=publisher_wallet,
        amount_usdc=amount_usdc,
        tx_hash=tx_hash,
        status=status_value,
    )


async def execute_settlement(
    claims: ProofContextClaims,
    db: Session,
    privy: PrivyClient,
) -> str:
    """Run nonce-claim → budget decrement → Privy USDC transfer → settlement row.

    Shared between `/proof` (publisher-authed, JWT-verified) and the dashboard's
    simulate-play endpoint (advertiser-authed, claims minted server-side). The
    caller has already authorized the claims; this helper owns the on-chain + DB
    state changes. Returns the confirmed tx hash. Raises HTTPException on every
    failure path — 4xx for validation, 502 for on-chain settlement failure
    (after persisting a failed settlement row so ops can retry).
    """
    # 1. Atomic nonce claim — first writer wins, duplicates get 409
    try:
        db.add(UsedNonce(nonce=claims.nonce))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="nonce already used") from None

    # 2. Load + validate campaign
    campaign = db.query(Campaign).filter(Campaign.id == claims.campaign_id).first()
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    if campaign.status != CampaignStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"campaign not active: {campaign.status}",
        )
    remaining = float(campaign.budget) - float(campaign.spent)
    if remaining < claims.amount_usdc:
        raise HTTPException(status_code=400, detail="insufficient campaign budget")

    # 3. Decrement budget before settling — nonce already claimed, so a retry
    # can't double-pay even if this request crashes after commit
    campaign.spent = float(campaign.spent) + claims.amount_usdc
    if float(campaign.spent) + 1e-9 >= float(campaign.budget):
        campaign.status = CampaignStatus.COMPLETED.value
    db.commit()

    # 4. Build + send USDC transfer via Privy. On failure we still persist a
    # failed settlement row so ops can see it and retry later (Session 7).
    try:
        tx_b64 = await build_usdc_transfer_tx(
            from_address=campaign.wallet_address,
            to_address=claims.wallet_id,
            amount_usdc=claims.amount_usdc,
        )
        tx_hash = await privy.sign_and_send_solana(
            wallet_id=campaign.wallet_id,
            transaction_base64=tx_b64,
            reference_id=f"settlement-{claims.nonce}",
        )
    except (PrivyError, Exception) as e:  # noqa: BLE001
        logger.exception(
            "settlement failed campaign=%s nonce=%s publisher=%s amount=%s",
            campaign.id,
            claims.nonce,
            claims.wallet_id,
            claims.amount_usdc,
        )
        db.add(
            _settlement_row(
                campaign_id=campaign.id,
                nonce=claims.nonce,
                publisher_wallet=claims.wallet_id,
                amount_usdc=claims.amount_usdc,
                tx_hash=None,
                status_value=SettlementStatus.FAILED.value,
            )
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"settlement failed: {e}",
        ) from e

    # 5. Success — record settlement row
    db.add(
        _settlement_row(
            campaign_id=campaign.id,
            nonce=claims.nonce,
            publisher_wallet=claims.wallet_id,
            amount_usdc=claims.amount_usdc,
            tx_hash=tx_hash,
            status_value=SettlementStatus.CONFIRMED.value,
        )
    )
    db.commit()
    return tx_hash


@router.post(
    "/proof",
    response_model=ProofResponse,
    dependencies=[Depends(require_publisher_api_key)],
)
async def proof(
    body: ProofRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    privy: PrivyClient = Depends(get_privy_client),
) -> ProofResponse:
    # 1. Decode + verify signature
    try:
        claims = decode_proof_context(
            body.proof_context, settings.jwt_server_secret, settings.jwt_algorithm
        )
    except ProofContextError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # 2. TTL: reject if older than configured window
    now = int(time.time())
    age = now - claims.created_at
    if age > settings.proof_context_ttl_seconds:
        raise HTTPException(status_code=400, detail=f"proof_context expired ({age}s)")
    if age < -60:  # modest skew tolerance
        raise HTTPException(status_code=400, detail="proof_context has future timestamp")

    # 3. Duration sanity
    if body.duration < MIN_PLAY_DURATION_SECONDS:
        raise HTTPException(status_code=400, detail="duration too short")

    tx_hash = await execute_settlement(claims, db, privy)
    return ProofResponse(status="confirmed", tx_hash=tx_hash)
