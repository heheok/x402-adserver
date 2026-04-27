"""One-shot: create a single throwaway helper Privy server wallet.

Use this to manually validate the Circle multi-wallet workaround before
committing to the full Session 12 bootstrap+sweep scripting.

Prints the helper address big and clear so you can paste it into
faucet.circle.com. Also requests ~0.05 devnet SOL so the wallet can
later sign a sweep tx back to the treasury.

Run from repo root:

    docker compose run --rm backend python scripts/create_helper_wallet.py

This wallet is NOT persisted to .env — it's a throwaway. The Session 12
bootstrap script will create the long-lived helper set.
"""
from __future__ import annotations

import asyncio
import sys
import uuid

sys.path.insert(0, "/app")

from app.services.privy import PrivyClient  # noqa: E402
from app.services.solana import airdrop_sol  # noqa: E402


async def main() -> int:
    client = PrivyClient()

    print("→ creating throwaway Solana helper wallet")
    # Unique idempotency key so re-running gives a fresh wallet.
    wallet = await client.create_solana_wallet(
        idempotency_key=f"helper-probe-{uuid.uuid4()}"
    )
    wid = wallet["id"]
    addr = wallet["address"]

    print()
    print("─" * 60)
    print(f"  HELPER ADDRESS:  {addr}")
    print(f"  privy id:        {wid}")
    print("─" * 60)
    print()

    print("→ requesting 0.05 devnet SOL for future sweep fee")
    try:
        sig = await airdrop_sol(addr, 0.05)
        print(f"   ✓ airdrop signature: {sig}")
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠ airdrop failed ({e!r})")
        print("     If you need to sweep manually, send ~0.01 SOL to the address above")
        print("     from https://faucet.solana.com/ first.")

    print()
    print("Next step: paste the HELPER ADDRESS above into")
    print("  https://faucet.circle.com/  (chain = Solana, network = Devnet)")
    print("Then immediately try claiming again at the TREASURY address.")
    print("If both claims succeed, the per-address rate-limit theory holds")
    print("and Session 12 scripting is worth doing.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
