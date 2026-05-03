import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..dependencies import AdvertiserIdentity, require_advertiser
from ..models import FaucetClaim, FaucetClaimStatus
from ..schemas import FaucetResponse, WalletInfo
from ..services.money import micro_str, to_micro
from ..services.privy import PrivyClient, PrivyError, get_privy_client
from ..services.solana import build_usdc_transfer_tx, get_usdc_balance_micro

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["wallet"])


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


@router.get("/wallet", response_model=WalletInfo)
async def get_wallet(
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    privy: PrivyClient = Depends(get_privy_client),
) -> WalletInfo:
    address = await _resolve_advertiser_wallet(advertiser, privy)
    balance_micro = await get_usdc_balance_micro(address)
    return WalletInfo(wallet_address=address, usdc_balance=micro_str(balance_micro))


@router.post("/faucet", response_model=FaucetResponse)
async def faucet(
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    privy: PrivyClient = Depends(get_privy_client),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> FaucetResponse:
    if not settings.treasury_wallet_id or not settings.treasury_wallet_address:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="treasury not configured — run scripts/bootstrap_treasury.py",
        )

    recipient = await _resolve_advertiser_wallet(advertiser, privy)
    faucet_amount_micro = to_micro(settings.faucet_amount_usdc)
    cap_micro = to_micro(settings.faucet_lifetime_cap_usdc)

    # Lifetime cap enforcement. Pending counts toward the cap so a user
    # spamming the button during the broadcast window can't bypass it.
    # Failed rows do NOT count (Privy refused pre-broadcast — no funds left).
    # Returned rows do NOT count (advertiser already drained back to treasury
    # via POST /api/faucet/reset).
    spent_micro = db.scalar(
        select(func.coalesce(func.sum(FaucetClaim.amount_usdc), 0))
        .where(FaucetClaim.advertiser_id == advertiser.user_id)
        .where(
            FaucetClaim.status.in_(
                [
                    FaucetClaimStatus.PENDING.value,
                    FaucetClaimStatus.CONFIRMED.value,
                ]
            )
        )
    ) or 0

    if spent_micro + faucet_amount_micro > cap_micro:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="faucet lifetime cap reached",
        )

    # Reserve the slot before broadcasting. If we crash between commit and
    # the Privy call, the row sits at PENDING and counts toward the cap —
    # safe over-counting. Operator can reconcile via Solscan if needed.
    claim = FaucetClaim(
        id=str(uuid4()),
        advertiser_id=advertiser.user_id,
        advertiser_wallet=recipient,
        amount_usdc=faucet_amount_micro,
        status=FaucetClaimStatus.PENDING.value,
    )
    db.add(claim)
    db.commit()

    tx_b64 = await build_usdc_transfer_tx(
        from_address=settings.treasury_wallet_address,
        to_address=recipient,
        amount_micro=faucet_amount_micro,
    )

    # Each click is a separate logical transfer, so the reference_id needs a
    # unique suffix. Privy rejects duplicate reference_ids with
    # "A transaction with this reference_id already exists for this app",
    # which would make the very first click the only one that ever works
    # for a given user.
    try:
        tx_hash = await privy.sign_and_send_solana(
            wallet_id=settings.treasury_wallet_id,
            transaction_base64=tx_b64,
            reference_id=f"faucet-{advertiser.user_id}-{uuid4().hex[:8]}",
        )
    except PrivyError as e:
        claim.status = FaucetClaimStatus.FAILED.value
        db.commit()
        logger.exception("faucet failed for advertiser=%s recipient=%s", advertiser.user_id, recipient)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    claim.tx_hash = tx_hash
    claim.status = FaucetClaimStatus.CONFIRMED.value
    db.commit()

    return FaucetResponse(amount=micro_str(faucet_amount_micro), tx_hash=tx_hash)


@router.post("/faucet/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_faucet(
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    db: Session = Depends(get_db),
) -> None:
    """Release the calling advertiser's faucet cap.

    Called by the dashboard after a user-initiated drain-to-treasury (the
    user wallet's USDC has been returned to the treasury), so the lifetime
    cap doesn't keep blocking them. Marks every PENDING + CONFIRMED claim
    for this advertiser as RETURNED — preserved for audit, excluded from
    the cap math.

    Trust model (intentional, demo scope): no on-chain verification of an
    actual return tx. Cycling drain → reset → faucet doesn't net the user
    any USDC; the only cost is broadcast gas (Privy-sponsored). If/when
    we move to mainnet this should take a tx_hash and verify on Solana
    that it's a recent USDC transfer from this advertiser's wallet to
    the treasury for at least the released amount.
    """
    db.query(FaucetClaim).filter(
        FaucetClaim.advertiser_id == advertiser.user_id,
        FaucetClaim.status.in_(
            [FaucetClaimStatus.PENDING.value, FaucetClaimStatus.CONFIRMED.value]
        ),
    ).update(
        {FaucetClaim.status: FaucetClaimStatus.RETURNED.value},
        synchronize_session=False,
    )
    db.commit()
