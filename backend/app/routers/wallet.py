from fastapi import APIRouter, Depends, HTTPException, status

from ..config import Settings, get_settings
from ..dependencies import AdvertiserIdentity, require_advertiser
from ..schemas import FaucetResponse, WalletInfo
from ..services.privy import PrivyClient, PrivyError, get_privy_client
from ..services.solana import build_usdc_transfer_tx, get_usdc_balance

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
    balance = await get_usdc_balance(address)
    return WalletInfo(wallet_address=address, usdc_balance=balance)


@router.post("/faucet", response_model=FaucetResponse)
async def faucet(
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    privy: PrivyClient = Depends(get_privy_client),
    settings: Settings = Depends(get_settings),
) -> FaucetResponse:
    if not settings.treasury_wallet_id or not settings.treasury_wallet_address:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="treasury not configured — run scripts/bootstrap_treasury.py",
        )

    recipient = await _resolve_advertiser_wallet(advertiser, privy)

    tx_b64 = await build_usdc_transfer_tx(
        from_address=settings.treasury_wallet_address,
        to_address=recipient,
        amount_usdc=settings.faucet_amount_usdc,
    )

    try:
        tx_hash = await privy.sign_and_send_solana(
            wallet_id=settings.treasury_wallet_id,
            transaction_base64=tx_b64,
            reference_id=f"faucet-{advertiser.user_id}",
        )
    except PrivyError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    return FaucetResponse(amount=settings.faucet_amount_usdc, tx_hash=tx_hash)
