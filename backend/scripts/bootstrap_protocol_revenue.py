"""Create the protocol-revenue server wallet once, then print env values to paste.

The 2.5% protocol fee is auto-transferred from each campaign wallet to this
wallet right after x402 settle confirms (see app/routers/campaigns.py). It
must be a separate Privy server wallet from treasury so accounting stays
clean — treasury = faucet source, protocol-revenue = fee sink.

Idempotent: if PROTOCOL_REVENUE_WALLET_ID is already set in the env, prints
the existing wallet details and exits.

Run from repo root:

    docker compose run --rm backend python scripts/bootstrap_protocol_revenue.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "/app")

from app.services.privy import PrivyClient  # noqa: E402


async def main() -> int:
    client = PrivyClient()

    existing_id = os.getenv("PROTOCOL_REVENUE_WALLET_ID", "").strip()
    if existing_id:
        print(f"ℹ PROTOCOL_REVENUE_WALLET_ID already set: {existing_id}")
        wallet = await client.get_wallet(existing_id)
        print(f"   address = {wallet.get('address')}")
        print("   (delete the env var and re-run if you want a fresh wallet)")
        return 0

    print("→ creating Solana protocol-revenue server wallet")
    wallet = await client.create_solana_wallet(
        idempotency_key="protocol-revenue-wallet-bootstrap-v1"
    )
    wid = wallet["id"]
    addr = wallet["address"]
    print(f"   ✓ id      = {wid}")
    print(f"   ✓ address = {addr}")

    print()
    print("─" * 60)
    print("Paste into backend/.env, then restart the backend container:")
    print()
    print(f"PROTOCOL_REVENUE_WALLET_ID={wid}")
    print(f"PROTOCOL_REVENUE_WALLET_ADDRESS={addr}")
    print("─" * 60)
    print()
    print("Note: no SOL or USDC ATA pre-creation needed — each campaign wallet")
    print("pays its own fee-transfer tx, and `build_usdc_transfer_tx` creates")
    print("the destination ATA idempotently as part of the same transaction.")
    print()
    print(f"View wallet on Solscan: https://solscan.io/account/{addr}?cluster=devnet")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
