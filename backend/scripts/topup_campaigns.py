"""One-shot SOL top-up for existing campaigns provisioned before the
right-sized-seed change (PLAN.md Session 16.6).

For each active/paused/expired campaign, computes the SOL needed to fund
every remaining play (`(budget - spent) / cpm * 1000` plays * 6_000 lamports
+ 50_000 reserve) and sends the shortfall from treasury → campaign wallet.

Idempotent: re-running is safe — only tops up wallets that are below their
required level. Use after upgrading the codebase + before resuming auto-play
on long-running campaigns.

Usage:
    docker compose run --rm backend python scripts/topup_campaigns.py        # dry run
    docker compose run --rm backend python scripts/topup_campaigns.py --execute
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
from app.services.calc import (  # noqa: E402
    SOL_BASE_RESERVE_LAMPORTS,
    SOL_PER_PLAY_LAMPORTS,
)
from app.services.privy import PrivyError, get_privy_client  # noqa: E402
from app.services.solana import (  # noqa: E402
    build_sol_transfer_tx,
    get_sol_lamports,
    wait_for_tx_confirmation,
)


LAMPORTS_PER_SOL = 1_000_000_000


def _required_lamports_for_remaining(c: Campaign) -> int:
    remaining_usdc = max(0.0, float(c.budget) - float(c.spent))
    cpm = float(c.cpm_price) if c.cpm_price else 0.0
    if cpm <= 0:
        return 0
    cost_per_play = cpm / 1000.0
    plays_remaining = int(remaining_usdc / cost_per_play + 0.5)
    return plays_remaining * SOL_PER_PLAY_LAMPORTS + SOL_BASE_RESERVE_LAMPORTS


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="actually run the txs")
    args = parser.parse_args()

    settings = get_settings()
    if not (settings.treasury_wallet_id and settings.treasury_wallet_address):
        print("[FATAL] treasury not configured")
        return 1

    db = SessionLocal()
    privy = get_privy_client()

    fundable = (
        db.query(Campaign)
        .filter(
            Campaign.status.in_(
                [
                    CampaignStatus.ACTIVE.value,
                    CampaignStatus.PAUSED.value,
                    CampaignStatus.EXPIRED.value,
                ]
            )
        )
        .all()
    )

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"=== topup_campaigns — {mode} — {len(fundable)} candidate(s)\n")
    print(f"  {'campaign':<14} {'status':<10} {'have SOL':>12} {'need SOL':>12} {'topup':>12}")
    print(f"  {'-'*14} {'-'*10} {'-'*12} {'-'*12} {'-'*12}")

    total_topup = 0
    for c in fundable:
        if not c.wallet_address:
            continue
        have = await get_sol_lamports(c.wallet_address)
        need = _required_lamports_for_remaining(c)
        gap = max(0, need - have)
        marker = ""
        if gap > 0:
            total_topup += gap
            marker = "← top up"
        print(
            f"  {c.id[:14]:<14} {c.status:<10} "
            f"{have/LAMPORTS_PER_SOL:>12.6f} "
            f"{need/LAMPORTS_PER_SOL:>12.6f} "
            f"{gap/LAMPORTS_PER_SOL:>12.6f}  {marker}"
        )

        if gap > 0 and args.execute:
            try:
                tx = await build_sol_transfer_tx(
                    from_address=settings.treasury_wallet_address,
                    to_address=c.wallet_address,
                    lamports=gap,
                )
                ref = f"topup-{c.id[:8]}-{uuid4().hex[:6]}"
                tx_hash = await privy.sign_and_send_solana(
                    wallet_id=settings.treasury_wallet_id,
                    transaction_base64=tx,
                    reference_id=ref,
                )
                await wait_for_tx_confirmation(tx_hash, timeout_seconds=30)
                print(f"      → tx {tx_hash[:14]}…")
            except (PrivyError, Exception) as e:  # noqa: BLE001
                print(f"      [FAIL] {e}")

    print(
        f"\nTotal topup: {total_topup/LAMPORTS_PER_SOL:.6f} SOL "
        f"({total_topup} lamports)"
    )
    if not args.execute:
        print("Re-run with --execute to send the topups.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
