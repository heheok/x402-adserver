from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..dependencies import require_publisher_api_key
from ..models import Campaign, CampaignStatus, Settlement, SettlementStatus, UsedNonce
from ..schemas import ProofRequest, ProofResponse
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
    device_id: str | None = None,
) -> Settlement:
    return Settlement(
        id=str(uuid4()),
        campaign_id=campaign_id,
        nonce=nonce,
        publisher_wallet=publisher_wallet,
        amount_usdc=amount_usdc,
        tx_hash=tx_hash,
        status=status_value,
        device_id=device_id,
    )


async def execute_settlement(
    claims: ProofContextClaims,
    db: Session,
) -> Settlement:
    """Run nonce-claim → budget reservation → write a pending Settlement row.

    Shared between `/proof` (publisher-authed, JWT-verified) and the dashboard's
    simulate-play endpoint (advertiser-authed, claims minted server-side). The
    caller has already authorized the claims; this helper owns the DB state
    changes. Returns the new pending Settlement row (no tx_hash yet — the
    background batch settler will broadcast and update). Raises HTTPException
    on every failure path — 4xx for validation, no on-chain failure path
    here because there's no on-chain call.

    Session 16.8: this used to broadcast a Solana tx and block on confirmation
    per play. That model produced false-rollback drift under RPC rate limits.
    The on-chain work moved to `services.batch_settler`, which groups pending
    rows by (campaign, publisher) and emits one tx per group per flush
    interval. See `BATCH-SETTLEMENTS.md` for the full design.
    """
    # 1. Atomic nonce claim — first writer wins, duplicates get 409
    try:
        db.add(UsedNonce(nonce=claims.nonce))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="nonce already used") from None

    # 2 + 3. Atomic budget reservation. One UPDATE that both checks
    # `budget - spent >= amount` and increments `spent`, plus flips status to
    # COMPLETED in the same statement when the new remaining can't fund
    # another play at this CPM. `rowcount == 0` means either the campaign
    # doesn't exist, isn't ACTIVE, or has insufficient budget — we re-read
    # to disambiguate for a useful error message.
    #
    # `+ 1e-9` epsilon survives the move to SQL: summing 0.001 many times
    # drifts ~1e-16 per step, so the "final" play can nominally have
    # remaining == cost but compare as remaining < cost. Eats the dust that
    # would otherwise leave campaigns stuck ACTIVE with an unspendable
    # remainder.
    #
    # This is the fix for PLAN's must-fix-before-mainnet #2: previously
    # two concurrent /proof calls on the same campaign could both pass the
    # Python-side budget check and both increment, last-write-wins. The
    # atomic UPDATE makes that impossible. Pending Settlement rows still
    # hold the reserved budget; if the batch settler ever has to compensate
    # (definitive on-chain failure), it decrements `spent` back at that point.
    epsilon = 1e-9
    new_spent = Campaign.spent + claims.amount_usdc
    play_cost = Campaign.cpm_price / 1000.0
    stmt = (
        update(Campaign)
        .where(Campaign.id == claims.campaign_id)
        .where(Campaign.status == CampaignStatus.ACTIVE.value)
        .where(Campaign.budget - Campaign.spent + epsilon >= claims.amount_usdc)
        .values(
            spent=new_spent,
            status=case(
                (
                    Campaign.budget - new_spent + epsilon < play_cost,
                    CampaignStatus.COMPLETED.value,
                ),
                else_=Campaign.status,
            ),
        )
        .execution_options(synchronize_session=False)
    )
    result = db.execute(stmt)
    db.commit()

    if result.rowcount == 0:
        # Disambiguate the failure with a follow-up read.
        existing = (
            db.query(Campaign).filter(Campaign.id == claims.campaign_id).first()
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        if existing.status != CampaignStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"campaign not active: {existing.status}",
            )
        raise HTTPException(status_code=400, detail="insufficient campaign budget")

    # 4. Queue for batch settlement. The batch_settler loop picks pending
    # rows up every BATCH_FLUSH_INTERVAL_SECONDS and emits one Solana tx
    # per (campaign, publisher) group.
    row = _settlement_row(
        campaign_id=claims.campaign_id,
        nonce=claims.nonce,
        publisher_wallet=claims.wallet_id,
        amount_usdc=claims.amount_usdc,
        tx_hash=None,
        status_value=SettlementStatus.PENDING.value,
        device_id=claims.device_id,
    )
    db.add(row)
    db.commit()
    return row


@router.post(
    "/proof",
    response_model=ProofResponse,
    dependencies=[Depends(require_publisher_api_key)],
)
async def proof(
    body: ProofRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
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

    # Session 16.8: queue for batch settlement. Sub-100ms response, no
    # tx_hash yet — the background batch_settler will broadcast and update
    # the row's status + tx_hash within BATCH_FLUSH_INTERVAL_SECONDS.
    row = await execute_settlement(claims, db)
    return ProofResponse(status=row.status, tx_hash=None, settlement_id=row.id)
