"""Sweep stranded SOL from terminal campaign wallets back to treasury.

Recovers SOL from three terminal states none of which auto-sweep today:

  • REFUNDED — two pre-fix bugs left SOL stuck:
      1. The refund handler skipped the SOL sweep entirely when a campaign
         drained to zero (early-return at `remaining_micro <= 0`). Full seed
         leaked on every fully-played refund.
      2. When the sweep DID run, a 10k-lamport buffer was too tight to
         absorb devnet RPC replica lag — `get_sol_lamports` occasionally
         returned a pre-tx balance, the sweep tx asked for too much, and
         the broadcast failed `insufficient lamports` off-by-fee.
    Both fixed in `app/routers/campaigns.py`. This script recovers the
    balances stranded BEFORE that fix.

  • COMPLETED — proof.py:109 atomically flips status to COMPLETED when the
    last settle drains the budget. USDC balance is guaranteed 0 by the
    flip rule (`models.py` + `proof.py:73`), but the unburned seed SOL is
    never swept. Safe to drain.

  • EXPIRED — bid.py:56 lazily flips active→expired when end_date has
    passed. The wallet may STILL hold leftover USDC the advertiser hasn't
    refunded. We do an on-chain USDC check and skip wallets with non-zero
    USDC (operator must click refund there — that path moves the USDC AND
    sweeps SOL via the patched handler).

Active/paused/draft campaigns are never touched.

Usage:
    # Dry run (default) — no txs, just prints what would happen.
    docker compose run --rm backend python scripts/recover_refunded_sol.py

    # Limit to one campaign (sanity-check before bulk):
    docker compose run --rm backend python scripts/recover_refunded_sol.py \\
        --campaign-id <id>

    # Restrict to one status family (default: all three terminal states):
    docker compose run --rm backend python scripts/recover_refunded_sol.py \\
        --status refunded

    # Execute for real:
    docker compose run --rm backend python scripts/recover_refunded_sol.py --execute

Idempotency: re-running on a swept wallet is a no-op (balance below buffer).
Privy reference_id includes a per-run uuid so transient retries don't
collide with prior tx records.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import uuid4

sys.path.insert(0, "/app")

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Campaign, CampaignStatus  # noqa: E402
from app.services.privy import PrivyError, get_privy_client  # noqa: E402
from app.services.solana import (  # noqa: E402
    build_sol_transfer_tx,
    get_sol_lamports,
    get_usdc_balance_micro,
)


LAMPORTS_PER_SOL = 1_000_000_000

# Same conservative buffer as sweep_to_treasury.py — 0.001 SOL leaves the
# wallet rent-safe and absorbs devnet replica lag with room to spare.
SOL_BUFFER_LAMPORTS = 1_000_000

# EXPIRED wallets are eligible only if their on-chain USDC balance is at
# or below this dust threshold. Keeps us from accidentally bricking a wallet
# whose advertiser still has a pending USDC refund to claim.
USDC_DUST_THRESHOLD_MICRO = 1_000  # $0.001

ELIGIBLE_STATUSES = {
    CampaignStatus.REFUNDED.value,
    CampaignStatus.COMPLETED.value,
    CampaignStatus.EXPIRED.value,
}


def _trunc(s: str | None, n: int = 8) -> str:
    if not s:
        return "—"
    return f"{s[:n]}…" if len(s) > n else s


async def _recover_one(privy, c: Campaign, treasury_address: str, *, execute: bool) -> int:
    """Returns lamports actually swept (or would-be-swept in dry-run)."""
    # Safety check for EXPIRED: skip if there's still real USDC the
    # advertiser hasn't refunded. COMPLETED is exempt by definition
    # (proof.py flips status only when budget is exhausted), and REFUNDED
    # already had its USDC moved by the refund handler.
    if c.status == CampaignStatus.EXPIRED.value:
        usdc_micro = await get_usdc_balance_micro(c.wallet_address)
        if usdc_micro > USDC_DUST_THRESHOLD_MICRO:
            print(
                f"  {c.id[:14]:<14}  {_trunc(c.wallet_address):<10}  "
                f"[skip EXPIRED — on-chain USDC={usdc_micro/1_000_000:.6f}, "
                f"refund-click first]"
            )
            return 0

    sol_lamports = await get_sol_lamports(c.wallet_address)
    sweep_lamports = max(0, sol_lamports - SOL_BUFFER_LAMPORTS)

    line = (
        f"  {c.id[:14]:<14}  [{c.status:<9}] {_trunc(c.wallet_address):<10}  "
        f"on-chain={sol_lamports/LAMPORTS_PER_SOL:>10.6f} SOL  "
        f"would-sweep={sweep_lamports/LAMPORTS_PER_SOL:>10.6f} SOL"
    )

    if sweep_lamports <= 0:
        print(f"{line}  [skip — below buffer]")
        return 0

    if not execute:
        print(f"{line}  [dry-run]")
        return sweep_lamports

    try:
        tx_b64 = await build_sol_transfer_tx(
            from_address=c.wallet_address,
            to_address=treasury_address,
            lamports=sweep_lamports,
        )
        # Per-run unique suffix so a re-execute after a transient Privy 5xx
        # gets a fresh reference_id (prior call's reference may be tied to
        # a tx that never broadcast cleanly).
        ref = f"recover-sol-{c.id}-{uuid4().hex[:6]}"
        tx_hash = await privy.sign_and_send_solana(
            wallet_id=c.wallet_id,
            transaction_base64=tx_b64,
            reference_id=ref,
        )
        print(f"{line}  → swept tx={_trunc(tx_hash, 16)}")
        return sweep_lamports
    except PrivyError as exc:
        print(f"{line}  [FAIL] {exc}")
        return 0
    except Exception as exc:  # noqa: BLE001 — log + keep going
        print(f"{line}  [FAIL] {type(exc).__name__}: {exc}")
        return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually broadcast sweep txs. Default is dry-run.",
    )
    parser.add_argument(
        "--campaign-id",
        type=str,
        default=None,
        help="Limit to a single campaign id (sanity-check before bulk).",
    )
    parser.add_argument(
        "--status",
        type=str,
        choices=sorted(ELIGIBLE_STATUSES),
        default=None,
        help=(
            "Restrict to one terminal status. Default: all of "
            f"{sorted(ELIGIBLE_STATUSES)}."
        ),
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.treasury_wallet_address:
        print("[FATAL] TREASURY_WALLET_ADDRESS not set.")
        return 1

    statuses = {args.status} if args.status else ELIGIBLE_STATUSES

    db = SessionLocal()
    try:
        q = db.query(Campaign).filter(
            Campaign.status.in_(statuses),
            Campaign.wallet_address.isnot(None),
            Campaign.wallet_id.isnot(None),
        )
        if args.campaign_id:
            q = q.filter(Campaign.id == args.campaign_id)
        rows = q.order_by(Campaign.created_at.asc()).all()

        if not rows:
            print(f"No matching campaigns (statuses={sorted(statuses)}).")
            return 0

        mode = "EXECUTE" if args.execute else "DRY-RUN"
        print(f"=== recover_refunded_sol [{mode}] ===")
        print(f"treasury: {settings.treasury_wallet_address}")
        print(f"buffer:   {SOL_BUFFER_LAMPORTS/LAMPORTS_PER_SOL:.6f} SOL per wallet")
        print(f"statuses: {sorted(statuses)}")
        print(f"targets:  {len(rows)} campaign(s)")
        print()

        privy = get_privy_client()
        total = 0
        for c in rows:
            swept = await _recover_one(
                privy, c, settings.treasury_wallet_address, execute=args.execute
            )
            total += swept

        print()
        verb = "swept" if args.execute else "would sweep"
        print(f"=== total: {verb} {total/LAMPORTS_PER_SOL:.6f} SOL ===")
        if not args.execute:
            print("Re-run with --execute to actually broadcast.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
