"""Create N helper Privy server wallets for Circle faucet multiplexing.

Circle's devnet faucet caps at 20 USDC per 2 hours **per address** (verified
2026-04-27 via per-address test). We multiplex it: claim into N helpers
manually, sweep into treasury via `scripts/sweep_helpers.py`. Net throughput
≈ N × 20 USDC per 2h.

Run from repo root:

    docker compose run --rm backend python scripts/bootstrap_helpers.py
    docker compose run --rm backend python scripts/bootstrap_helpers.py --count 5

Each helper is seeded with 0.01 SOL from the treasury so it can pay sweep
fees later. We use the treasury (not the RPC airdrop) because devnet's
airdrop endpoint is rate-limited and unreliable — same lesson as the
campaign-wallet seed flow in `routers/campaigns.py`.

The script does NOT write `.env` for you — paste the printed lines into
`backend/.env`, then `docker compose up -d --force-recreate backend`.

Re-running creates ADDITIONAL wallets every time. There's no persistence
between runs (we don't read existing HELPER_WALLET_IDS), so be careful not
to leak helpers — each unused helper just sits in your Privy app forever.
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
    build_sol_transfer_tx,
    wait_for_tx_confirmation,
)

DEFAULT_COUNT = 3
HELPER_SOL_SEED_LAMPORTS = 10_000_000  # 0.01 SOL — matches campaign wallet seed


async def main(count: int) -> int:
    if count < 1:
        print("count must be >= 1")
        return 2

    settings = get_settings()
    if not settings.treasury_wallet_id or not settings.treasury_wallet_address:
        print("✗ TREASURY_WALLET_ID / TREASURY_WALLET_ADDRESS not set in .env")
        print("  Run scripts/bootstrap_treasury.py first.")
        return 2

    client = PrivyClient()
    helpers: list[tuple[str, str]] = []

    for i in range(count):
        print(f"→ [{i + 1}/{count}] creating Solana helper wallet")
        wallet = await client.create_solana_wallet(
            idempotency_key=f"helper-bootstrap-{uuid.uuid4()}"
        )
        wid = wallet["id"]
        addr = wallet["address"]
        print(f"   ✓ id      = {wid}")
        print(f"   ✓ address = {addr}")
        helpers.append((wid, addr))

        print(f"   → seeding {HELPER_SOL_SEED_LAMPORTS / 1e9} SOL from treasury")
        try:
            tx_b64 = await build_sol_transfer_tx(
                from_address=settings.treasury_wallet_address,
                to_address=addr,
                lamports=HELPER_SOL_SEED_LAMPORTS,
            )
            sig = await client.sign_and_send_solana(
                wallet_id=settings.treasury_wallet_id,
                transaction_base64=tx_b64,
                reference_id=f"helper-seed-{wid}-{uuid.uuid4().hex[:8]}",
            )
            confirmed = await wait_for_tx_confirmation(sig, timeout_seconds=45.0)
            if not confirmed:
                print(f"   ⚠ seed tx {sig} did not confirm in 45s")
                print(f"     Solscan: https://solscan.io/tx/{sig}?cluster=devnet")
                print("     Sweep may fail until it lands; re-check balance later.")
            else:
                print(f"   ✓ seed tx: {sig}")
        except PrivyError as e:
            print(f"   ✗ privy error: {e}")
            print("     Helper created but unfunded — fund manually from")
            print(f"     https://faucet.solana.com/ before sweeping {addr}")
        except Exception as e:  # noqa: BLE001
            print(f"   ✗ seed failed: {e!r}")
            print("     Helper created but unfunded — fund manually from")
            print(f"     https://faucet.solana.com/ before sweeping {addr}")
        print()

    ids_csv = ",".join(wid for wid, _ in helpers)
    addrs_csv = ",".join(addr for _, addr in helpers)

    print("─" * 60)
    print("Paste into backend/.env, then recreate the backend container:")
    print()
    print(f"HELPER_WALLET_IDS={ids_csv}")
    print(f"HELPER_WALLET_ADDRESSES={addrs_csv}")
    print("─" * 60)
    print()
    print("Next: open https://faucet.circle.com (Solana / Devnet) and claim")
    print("into each helper address above. Then:")
    print("  docker compose run --rm backend python scripts/sweep_helpers.py")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help=f"how many helper wallets to create (default {DEFAULT_COUNT})",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.count)))
