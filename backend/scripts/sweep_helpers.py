"""Sweep USDC from helper wallets back to the treasury.

Default mode reads HELPER_WALLET_IDS / HELPER_WALLET_ADDRESSES (comma-separated,
matching order) from env, walks each helper, and if its USDC balance is > 0
builds a USDC transfer to TREASURY_WALLET_ADDRESS and broadcasts via Privy.

Rescue mode (--wallet-id + --wallet-address) sweeps a single wallet not yet
in env — used to recover funds from one-off helpers (e.g. the throwaway
created by `create_helper_wallet.py` before the fleet was bootstrapped).

Exit codes:
    0 = every non-empty helper swept successfully
    1 = one or more sweeps failed (check logs)
    2 = misconfigured args / env

Run from repo root:

    docker compose run --rm backend python scripts/sweep_helpers.py
    docker compose run --rm backend python scripts/sweep_helpers.py \\
        --wallet-id <id> --wallet-address <addr>
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

sys.path.insert(0, "/app")

from app.config import get_settings  # noqa: E402
from app.services.privy import PrivyClient, PrivyError  # noqa: E402
from app.services.solana import (  # noqa: E402
    build_usdc_transfer_tx,
    get_usdc_balance_micro,
)


def _solscan_tx_url(tx_hash: str) -> str:
    return f"https://solscan.io/tx/{tx_hash}?cluster=devnet"


async def _sweep_one(
    client: PrivyClient,
    wallet_id: str,
    wallet_address: str,
    treasury_address: str,
) -> bool:
    """Sweep one wallet's full USDC balance to the treasury. Returns True on success or skip."""
    print(f"→ {wallet_address}")
    balance_micro = await get_usdc_balance_micro(wallet_address)
    print(f"   balance: {balance_micro/1_000_000:.6f} USDC")
    if balance_micro <= 0:
        print("   skip — empty")
        return True

    # Privy reference_id is NOT strict pre-broadcast idempotency
    # (see BUSINESS-CONSTRAINTS §3). Unique suffix per call so retries
    # of *this script* don't collide with prior runs. Capped at 64 chars
    # by Privy — full uuid is 36, so use the short hex form.
    ref = f"sweep-{wallet_id}-{uuid.uuid4().hex[:8]}"
    try:
        tx_b64 = await build_usdc_transfer_tx(
            from_address=wallet_address,
            to_address=treasury_address,
            amount_micro=balance_micro,
        )
        tx_hash = await client.sign_and_send_solana(
            wallet_id=wallet_id,
            transaction_base64=tx_b64,
            reference_id=ref,
        )
    except PrivyError as e:
        print(f"   ✗ privy error: {e}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"   ✗ failed: {e!r}")
        return False

    print(f"   ✓ tx: {tx_hash}")
    print(f"   {_solscan_tx_url(tx_hash)}")
    return True


async def main(wallet_id: str | None, wallet_address: str | None) -> int:
    settings = get_settings()

    treasury = settings.treasury_wallet_address.strip()
    if not treasury:
        print("✗ TREASURY_WALLET_ADDRESS not set in .env")
        return 2

    # Determine the target list.
    if wallet_id or wallet_address:
        if not (wallet_id and wallet_address):
            print("✗ --wallet-id and --wallet-address must be passed together")
            return 2
        targets = [(wallet_id, wallet_address)]
    else:
        ids = [s.strip() for s in settings.helper_wallet_ids.split(",") if s.strip()]
        addrs = [
            s.strip()
            for s in settings.helper_wallet_addresses.split(",")
            if s.strip()
        ]
        if not ids or not addrs:
            print("✗ HELPER_WALLET_IDS / HELPER_WALLET_ADDRESSES not set in .env")
            print("  Run scripts/bootstrap_helpers.py first.")
            return 2
        if len(ids) != len(addrs):
            print(
                f"✗ HELPER_WALLET_IDS ({len(ids)}) and HELPER_WALLET_ADDRESSES "
                f"({len(addrs)}) length mismatch"
            )
            return 2
        targets = list(zip(ids, addrs))

    print(f"sweeping {len(targets)} wallet(s) → {treasury}")
    print()

    client = PrivyClient()
    failures = 0
    for wid, addr in targets:
        ok = await _sweep_one(client, wid, addr, treasury)
        if not ok:
            failures += 1
        print()

    if failures:
        print(f"✗ {failures}/{len(targets)} sweeps failed")
        return 1
    print(f"✓ all {len(targets)} sweep(s) ok")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--wallet-id",
        help="rescue mode: privy id of a single wallet to sweep (with --wallet-address)",
    )
    parser.add_argument(
        "--wallet-address",
        help="rescue mode: solana address of the wallet (with --wallet-id)",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.wallet_id, args.wallet_address)))
