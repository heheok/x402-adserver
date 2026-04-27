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
    # Python-side budget check and both increment, last-write-wins, with two
    # on-chain settlements but only one budget tick. The atomic UPDATE makes
    # that impossible.
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

    # Re-load post-update so we have the latest spent/status plus the
    # wallet fields needed for the on-chain transfer.
    campaign = (
        db.query(Campaign).filter(Campaign.id == claims.campaign_id).first()
    )
    if campaign is None:  # belt-and-braces: shouldn't happen
        raise HTTPException(status_code=404, detail="campaign not found")

    # 4. Build + send USDC transfer via Privy. On failure we still persist a
    # failed settlement row so ops can see it and retry later (Session 7).
    try:
        tx_b64 = await build_usdc_transfer_tx(
            from_address=campaign.wallet_address,
            to_address=claims.wallet_id,
            amount_usdc=claims.amount_usdc,
            # Nonce is unique per settlement; tagging the tx with it makes
            # the bytes unique even when multiple concurrent plays share
            # one blockhash window. Without this, the network dedupes
            # identical transfers to a single on-chain tx.
            memo=f"x402:{claims.nonce}",
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
        # Compensating UPDATE: refund the budget reservation. We charged it
        # in step 2-3 expecting the on-chain transfer to land; on Privy
        # failure (notably `transaction_broadcast_failure` — broadcast did
        # not happen by Privy's own admission) the budget should be returned.
        # Also flip status back to ACTIVE if our forward UPDATE flipped it
        # to COMPLETED on what turned out to be a false-final play.
        # Nonce stays consumed — publishers must retry with a fresh /bid +
        # proof_context, not the same one (replay protection).
        refund_stmt = (
            update(Campaign)
            .where(Campaign.id == claims.campaign_id)
            .values(
                spent=Campaign.spent - claims.amount_usdc,
                status=case(
                    (
                        (Campaign.status == CampaignStatus.COMPLETED.value)
                        & (
                            Campaign.budget
                            - (Campaign.spent - claims.amount_usdc)
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
        db.add(
            _settlement_row(
                campaign_id=campaign.id,
                nonce=claims.nonce,
                publisher_wallet=claims.wallet_id,
                amount_usdc=claims.amount_usdc,
                tx_hash=None,
                status_value=SettlementStatus.FAILED.value,
                device_id=claims.device_id,
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
            device_id=claims.device_id,
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
