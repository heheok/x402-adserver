"""One-shot probe: does Privy gas sponsorship work for our Solana devnet app?

Picks a paused campaign wallet, sends 0.0005 USDC to DEMO_PUBLISHER_WALLET
with `sponsor=True`, then checks:
  1. Did the tx confirm on-chain?
  2. Did the campaign wallet's SOL balance stay unchanged?
     (If yes → Privy paid the fee → sponsorship works.)

Usage:
    docker compose run --rm backend python scripts/probe_sponsorship.py [campaign_id]

If campaign_id is omitted, picks the first paused/active campaign with a
non-zero USDC balance.
"""

from __future__ import annotations

import asyncio
import sys
from uuid import uuid4

sys.path.insert(0, "/app")

from solana.rpc.async_api import AsyncClient  # noqa: E402
from solders.pubkey import Pubkey  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Campaign, CampaignStatus  # noqa: E402
from app.services.privy import PrivyError, get_privy_client  # noqa: E402
from app.services.solana import (  # noqa: E402
    build_usdc_transfer_tx,
    get_usdc_balance,
    wait_for_tx_confirmation,
)


PROBE_AMOUNT_USDC = 0.0005


async def _sol_lamports(client: AsyncClient, address: str) -> int:
    resp = await client.get_balance(Pubkey.from_string(address))
    return int(resp.value or 0)


async def main() -> int:
    settings = get_settings()
    db = SessionLocal()
    privy = get_privy_client()

    # Pick a campaign
    if len(sys.argv) > 1:
        c = db.query(Campaign).filter(Campaign.id == sys.argv[1]).first()
        if not c:
            print(f"campaign {sys.argv[1]} not found")
            return 1
    else:
        c = (
            db.query(Campaign)
            .filter(
                Campaign.status.in_(
                    [CampaignStatus.PAUSED.value, CampaignStatus.ACTIVE.value]
                )
            )
            .order_by(Campaign.created_at.desc())
            .first()
        )
        if not c:
            print("no paused/active campaign with a wallet — pick one explicitly")
            return 1

    print(f"probing with campaign: {c.id}  status={c.status}  wallet={c.wallet_address}")

    if not settings.demo_publisher_wallet:
        print("DEMO_PUBLISHER_WALLET not set — needed as the destination")
        return 1

    async with AsyncClient(settings.solana_rpc_url) as client:
        # Snapshot pre-state
        sol_pre = await _sol_lamports(client, c.wallet_address)
        usdc_pre_src = await get_usdc_balance(c.wallet_address)
        usdc_pre_dst = await get_usdc_balance(settings.demo_publisher_wallet)
        print(
            f"\nPRE:\n"
            f"  campaign  SOL={sol_pre/1e9:.9f}  USDC={usdc_pre_src:.6f}\n"
            f"  publisher                       USDC={usdc_pre_dst:.6f}"
        )

        if usdc_pre_src < PROBE_AMOUNT_USDC:
            print(f"\ncampaign wallet has < {PROBE_AMOUNT_USDC} USDC; pick another")
            return 1

        # Build + send WITH sponsor=True
        tx_b64 = await build_usdc_transfer_tx(
            from_address=c.wallet_address,
            to_address=settings.demo_publisher_wallet,
            amount_usdc=PROBE_AMOUNT_USDC,
            memo=f"sponsor-probe:{uuid4().hex[:8]}",
        )

        print("\nbroadcasting with sponsor=True ...")
        try:
            tx_hash = await privy.sign_and_send_solana(
                wallet_id=c.wallet_id,
                transaction_base64=tx_b64,
                reference_id=f"sponsor-probe-{uuid4().hex[:8]}",
                sponsor=True,
            )
        except PrivyError as e:
            print(f"\n[FAIL] Privy rejected sponsored tx: {e}")
            print("  → sponsorship likely not enabled on the dashboard, or our")
            print("    tx shape is incompatible. Fall back to Option A (top-up).")
            return 2

        print(f"  tx hash: {tx_hash}")
        print(f"  solscan: https://solscan.io/tx/{tx_hash}?cluster=devnet")

        # Wait for confirmation
        print("\nwaiting for confirmation ...")
        confirmed = await wait_for_tx_confirmation(tx_hash, timeout_seconds=30)
        print(f"  confirmed: {confirmed}")

        # Snapshot post-state
        sol_post = await _sol_lamports(client, c.wallet_address)
        usdc_post_src = await get_usdc_balance(c.wallet_address)
        usdc_post_dst = await get_usdc_balance(settings.demo_publisher_wallet)

        sol_delta = sol_post - sol_pre
        usdc_src_delta = usdc_post_src - usdc_pre_src
        usdc_dst_delta = usdc_post_dst - usdc_pre_dst

        print(
            f"\nPOST:\n"
            f"  campaign  SOL={sol_post/1e9:.9f} (Δ={sol_delta:+d} lamports)  USDC={usdc_post_src:.6f} (Δ={usdc_src_delta:+.6f})\n"
            f"  publisher                                                       USDC={usdc_post_dst:.6f} (Δ={usdc_dst_delta:+.6f})"
        )

        # Verdict
        print("\n=== VERDICT ===")
        if abs(usdc_src_delta + PROBE_AMOUNT_USDC) > 1e-9:
            print(f"❌  campaign USDC delta unexpected ({usdc_src_delta:+.6f}, expected {-PROBE_AMOUNT_USDC:+.6f})")
            return 3
        if abs(usdc_dst_delta - PROBE_AMOUNT_USDC) > 1e-9:
            print(f"❌  publisher USDC delta unexpected ({usdc_dst_delta:+.6f}, expected {+PROBE_AMOUNT_USDC:+.6f})")
            return 3
        if sol_delta == 0:
            print(f"✅  USDC moved correctly AND campaign wallet's SOL is unchanged.")
            print(f"    Privy paid the gas. SPONSORSHIP WORKS on devnet.")
            return 0
        elif sol_delta < 0:
            print(f"⚠️   USDC moved correctly BUT campaign wallet lost {-sol_delta} lamports of SOL.")
            print(f"    Privy did not sponsor — campaign wallet paid as usual.")
            print(f"    Check the dashboard toggle, or sponsorship may be off for this network.")
            return 4
        else:
            print(f"❓  USDC moved correctly AND campaign wallet GAINED {sol_delta} lamports of SOL.")
            print(f"    Unexpected. Inspect the tx on Solscan.")
            return 5


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
