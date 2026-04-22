"""Create the treasury server wallet once, then print the values to paste into .env.

Idempotent: if TREASURY_WALLET_ID is already set in the env, prints the existing
wallet details and exits. Requires a network-reachable Privy API.

Run from repo root:

    docker compose run --rm backend python scripts/bootstrap_treasury.py
"""
from __future__ import annotations

import asyncio
import os
import sys

# make `app` importable when executed via `python scripts/bootstrap_treasury.py`
sys.path.insert(0, "/app")

from app.services.privy import PrivyClient  # noqa: E402
from app.services.solana import airdrop_sol  # noqa: E402


async def main() -> int:
    client = PrivyClient()

    existing_id = os.getenv("TREASURY_WALLET_ID", "").strip()
    if existing_id:
        print(f"ℹ TREASURY_WALLET_ID already set: {existing_id}")
        wallet = await client.get_wallet(existing_id)
        print(f"   address = {wallet.get('address')}")
        print("   (delete the env var and re-run if you want a fresh wallet)")
        return 0

    print("→ creating Solana treasury server wallet")
    wallet = await client.create_solana_wallet(idempotency_key="treasury-wallet-bootstrap-v1")
    wid = wallet["id"]
    addr = wallet["address"]
    print(f"   ✓ id      = {wid}")
    print(f"   ✓ address = {addr}")

    print()
    print("→ requesting devnet SOL airdrop for tx fees (1 SOL)")
    try:
        sig = await airdrop_sol(addr, 1.0)
    except Exception as e:  # noqa: BLE001
        sig = None
        print(f"   (airdrop errored: {e!r})")
    if sig:
        print(f"   ✓ airdrop signature: {sig}")
    else:
        print("   ⚠ RPC airdrop unavailable (rate-limited or down).")
        print("     Use https://faucet.solana.com/ — paste the address, request 1 devnet SOL.")

    print()
    print("─" * 60)
    print("Paste into backend/.env, then restart the backend container:")
    print()
    print(f"TREASURY_WALLET_ID={wid}")
    print(f"TREASURY_WALLET_ADDRESS={addr}")
    print("─" * 60)
    print()
    print("Next step: fund the treasury with devnet USDC.")
    print(" 1. Go to https://faucet.circle.com")
    print(" 2. Choose network: Solana Devnet")
    print(f" 3. Paste the treasury address: {addr}")
    print(" 4. Request 1000 USDC (or whatever the faucet caps at — re-run if needed)")
    print(" 5. Wait ~10 seconds, then verify on Solscan:")
    print(f"      https://solscan.io/account/{addr}?cluster=devnet")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
