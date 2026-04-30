"""Sweep stranded USDC + SOL from every owned wallet back to the treasury.

Owned wallets discovered automatically:
  • All campaign wallets in the DB (campaigns.wallet_id / .wallet_address)
  • Helper wallets (HELPER_WALLET_IDS / _ADDRESSES)
  • Protocol revenue wallet (PROTOCOL_REVENUE_WALLET_ID / _ADDRESS)
  • Demo publisher wallet (looked up via Privy list_wallets, by address match)

NOT swept:
  • Treasury (the destination)
  • Advertiser wallets (Privy embedded, owned by users — not ours to drain)

Usage:
    # Dry run (default) — no on-chain txs, just prints what *would* happen.
    docker compose run --rm backend python scripts/sweep_to_treasury.py

    # For real:
    docker compose run --rm backend python scripts/sweep_to_treasury.py --execute

Order on each wallet: USDC first, then SOL (USDC transfer needs SOL for fee).
Leaves SOL_BUFFER_LAMPORTS (0.001 SOL) on each so the wallet stays alive +
has fee headroom for one final tx if anyone needs to sweep again.

Note on Privy: wallets cannot be deleted (`BUSINESS-CONSTRAINTS.md §3`). After
sweep, every wallet still exists in the Privy app, just with ~0 USDC and ~0
SOL above buffer. This is fine — the addresses are deterministic and any
future flow that needs them just reuses them.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from uuid import uuid4

sys.path.insert(0, "/app")

from solana.rpc.async_api import AsyncClient  # noqa: E402
from solders.pubkey import Pubkey  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Campaign  # noqa: E402
from app.services.privy import PrivyError, get_privy_client  # noqa: E402
from app.services.solana import (  # noqa: E402
    build_sol_transfer_tx,
    build_usdc_transfer_tx,
    get_usdc_balance_micro,
    wait_for_tx_confirmation,
)


# Leave 0.001 SOL on each swept wallet so the account stays alive and there's
# fee headroom for one more tx if we ever need to re-sweep. This costs ~0.05
# SOL across 50 wallets — small enough not to matter.
SOL_BUFFER_LAMPORTS = 1_000_000

# If a wallet has USDC to sweep but less than this much SOL, treasury seeds
# it with GAS_SEED_LAMPORTS first so it can pay its own tx fee. 50_000 ≈ 10×
# one signature's fee — enough headroom for a couple of broadcast retries.
MIN_GAS_LAMPORTS = 50_000
GAS_SEED_LAMPORTS = 1_000_000

USDC_DUST_THRESHOLD_MICRO = 1  # 1 microUSDC — anything smaller is unsweepable
LAMPORTS_PER_SOL = 1_000_000_000


@dataclass
class WalletEntry:
    role: str
    wallet_id: str
    address: str


def _trunc(s: str, n: int = 10) -> str:
    return f"{s[:n]}…{s[-4:]}" if len(s) > n + 4 else s


async def _get_sol_lamports(client: AsyncClient, address: str) -> int:
    try:
        resp = await client.get_balance(Pubkey.from_string(address))
        return int(resp.value or 0)
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARN] could not read SOL for {_trunc(address)}: {exc}")
        return 0


async def _resolve_demo_publisher(privy, demo_address: str) -> str | None:
    """Look up the Privy wallet_id for the demo publisher by address match."""
    cursor: str | None = None
    while True:
        page = await privy.list_wallets(cursor=cursor)
        for w in page.get("data", []):
            if w.get("address") == demo_address:
                return w.get("id")
        cursor = page.get("next_cursor")
        if not cursor:
            return None


async def _collect_wallets(db, settings, privy) -> list[WalletEntry]:
    out: list[WalletEntry] = []

    # Campaign wallets
    rows = db.query(Campaign).order_by(Campaign.created_at.asc()).all()
    for c in rows:
        if c.wallet_id and c.wallet_address:
            out.append(WalletEntry(f"campaign:{c.id[:14]}", c.wallet_id, c.wallet_address))

    # Helpers
    ids = [s.strip() for s in (settings.helper_wallet_ids or "").split(",") if s.strip()]
    addrs = [s.strip() for s in (settings.helper_wallet_addresses or "").split(",") if s.strip()]
    for i, (wid, addr) in enumerate(zip(ids, addrs)):
        out.append(WalletEntry(f"helper-{i}", wid, addr))

    # Protocol revenue
    if settings.protocol_revenue_wallet_id and settings.protocol_revenue_wallet_address:
        out.append(
            WalletEntry(
                "protocol-revenue",
                settings.protocol_revenue_wallet_id,
                settings.protocol_revenue_wallet_address,
            )
        )

    # Demo publisher (look up wallet_id via Privy)
    if settings.demo_publisher_wallet:
        wid = await _resolve_demo_publisher(privy, settings.demo_publisher_wallet)
        if wid:
            out.append(WalletEntry("demo-publisher", wid, settings.demo_publisher_wallet))
        else:
            print(
                f"[WARN] demo publisher {_trunc(settings.demo_publisher_wallet)} not found in Privy "
                "wallet list — skipping (may be an external address)"
            )

    return out


async def _sweep_one(
    privy,
    client: AsyncClient,
    w: WalletEntry,
    treasury_address: str,
    treasury_wallet_id: str,
    *,
    execute: bool,
) -> tuple[int, int]:
    """Returns (usdc_micro_swept, sol_lamports_swept)."""
    usdc_micro = await get_usdc_balance_micro(w.address)
    sol = await _get_sol_lamports(client, w.address)

    print(
        f"  {w.role:<28} {_trunc(w.address):<18} USDC={usdc_micro/1_000_000:>12.6f}  "
        f"SOL={sol/LAMPORTS_PER_SOL:>10.6f}"
    )

    usdc_micro_swept = 0
    sol_swept = 0

    # Gas-seed pass: if there's USDC to sweep but not enough SOL to pay the
    # transfer fee, treasury fronts a small amount first.
    if usdc_micro > USDC_DUST_THRESHOLD_MICRO and sol < MIN_GAS_LAMPORTS:
        if execute:
            try:
                tx = await build_sol_transfer_tx(
                    from_address=treasury_address,
                    to_address=w.address,
                    lamports=GAS_SEED_LAMPORTS,
                )
                ref = f"sweep-gas-{uuid4().hex[:8]}"
                tx_hash = await privy.sign_and_send_solana(
                    wallet_id=treasury_wallet_id, transaction_base64=tx, reference_id=ref
                )
                print(
                    f"    → gas seed {GAS_SEED_LAMPORTS/LAMPORTS_PER_SOL:.6f} SOL from treasury tx={_trunc(tx_hash or '?')}"
                )
                if tx_hash:
                    await wait_for_tx_confirmation(tx_hash, timeout_seconds=30)
                sol = await _get_sol_lamports(client, w.address)
            except (PrivyError, Exception) as exc:  # noqa: BLE001
                print(f"    [FAIL] gas seed: {exc}  — USDC sweep will likely fail")
        else:
            print(f"    → would seed {GAS_SEED_LAMPORTS/LAMPORTS_PER_SOL:.6f} SOL from treasury for gas")

    # USDC sweep
    if usdc_micro > USDC_DUST_THRESHOLD_MICRO:
        if execute:
            try:
                tx = await build_usdc_transfer_tx(
                    from_address=w.address,
                    to_address=treasury_address,
                    amount_micro=usdc_micro,
                    memo=f"sweep:{uuid4().hex[:8]}",
                )
                ref = f"sweep-usdc-{uuid4().hex[:8]}"
                tx_hash = await privy.sign_and_send_solana(
                    wallet_id=w.wallet_id, transaction_base64=tx, reference_id=ref
                )
                print(f"    → USDC swept {usdc_micro/1_000_000:.6f} tx={_trunc(tx_hash or '?')}")
                if tx_hash:
                    await wait_for_tx_confirmation(tx_hash, timeout_seconds=30)
                usdc_micro_swept = usdc_micro
            except (PrivyError, Exception) as exc:  # noqa: BLE001
                print(f"    [FAIL] USDC sweep: {exc}")
        else:
            print(f"    → would sweep USDC {usdc_micro/1_000_000:.6f}")
            usdc_micro_swept = usdc_micro

    # SOL sweep (after USDC, refresh balance to account for the USDC tx fee)
    sol_after_usdc = sol
    if execute and usdc_micro_swept > 0:
        sol_after_usdc = await _get_sol_lamports(client, w.address)

    sweep_lamports = max(0, sol_after_usdc - SOL_BUFFER_LAMPORTS)
    if sweep_lamports > 0:
        if execute:
            try:
                tx = await build_sol_transfer_tx(
                    from_address=w.address,
                    to_address=treasury_address,
                    lamports=sweep_lamports,
                )
                ref = f"sweep-sol-{uuid4().hex[:8]}"
                tx_hash = await privy.sign_and_send_solana(
                    wallet_id=w.wallet_id, transaction_base64=tx, reference_id=ref
                )
                print(
                    f"    → SOL swept {sweep_lamports/LAMPORTS_PER_SOL:.6f} tx={_trunc(tx_hash or '?')}"
                )
                if tx_hash:
                    await wait_for_tx_confirmation(tx_hash, timeout_seconds=30)
                sol_swept = sweep_lamports
            except (PrivyError, Exception) as exc:  # noqa: BLE001
                print(f"    [FAIL] SOL sweep: {exc}")
        else:
            print(f"    → would sweep SOL {sweep_lamports/LAMPORTS_PER_SOL:.6f}")
            sol_swept = sweep_lamports

    return usdc_micro_swept, sol_swept


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run the sweeps. Default is dry-run.",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.treasury_wallet_address:
        print("[FATAL] TREASURY_WALLET_ADDRESS not set; cannot determine sweep destination.")
        return 1
    if not settings.treasury_wallet_id:
        print("[FATAL] TREASURY_WALLET_ID not set; cannot sign gas-seed txs from treasury.")
        return 1

    db = SessionLocal()
    privy = get_privy_client()

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"=== sweep_to_treasury — {mode} — destination: {_trunc(settings.treasury_wallet_address)}")

    try:
        async with AsyncClient(settings.solana_rpc_url) as client:
            wallets = await _collect_wallets(db, settings, privy)
            print(f"\nDiscovered {len(wallets)} wallets to consider:\n")
            print(f"  {'role':<28} {'address':<18} {'USDC':>14}     {'SOL':>14}")
            print(f"  {'-'*28} {'-'*18} {'-'*14}     {'-'*14}")

            total_usdc_micro = 0
            total_sol = 0
            for w in wallets:
                usdc_micro, sol = await _sweep_one(
                    privy,
                    client,
                    w,
                    settings.treasury_wallet_address,
                    settings.treasury_wallet_id,
                    execute=args.execute,
                )
                total_usdc_micro += usdc_micro
                total_sol += sol

            print(
                f"\n{'(would sweep)' if not args.execute else 'Swept'}: "
                f"{total_usdc_micro/1_000_000:.6f} USDC + {total_sol/LAMPORTS_PER_SOL:.6f} SOL"
            )
            if not args.execute:
                print("\nRe-run with --execute to actually move funds.")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
