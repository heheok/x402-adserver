"""Print SOL + USDC balance for any Solana devnet address.

    docker compose run --rm backend python scripts/check_balance.py <address>
    docker compose run --rm backend python scripts/check_balance.py  # uses TREASURY_WALLET_ADDRESS
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "/app")

from solana.rpc.async_api import AsyncClient  # noqa: E402
from solders.pubkey import Pubkey  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.services.solana import get_usdc_balance_micro  # noqa: E402


async def main() -> int:
    settings = get_settings()
    if len(sys.argv) > 1:
        address = sys.argv[1]
    else:
        address = os.getenv("TREASURY_WALLET_ADDRESS", settings.treasury_wallet_address)
    if not address:
        print("usage: check_balance.py <address>   (or set TREASURY_WALLET_ADDRESS)")
        return 1

    async with AsyncClient(settings.solana_rpc_url) as c:
        sol_resp = await c.get_balance(Pubkey.from_string(address))
        sol = (sol_resp.value or 0) / 1_000_000_000

    usdc_micro = await get_usdc_balance_micro(address)
    print(f"address: {address}")
    print(f"SOL:     {sol:.6f}")
    print(f"USDC:    {usdc_micro/1_000_000:.6f} ({usdc_micro} micro)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
