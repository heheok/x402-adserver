"""One-shot cleanup for the 0.0055 USDC drift on campaign ac89a867.

The audit (scripts/audit_ledger.py) showed:
  publisher 3pMCrwRq…V8W9: 844 plays expected 1.9070 USDC, on-chain 1.9015 (SHORT 0.0055)
  campaign  ac89a867:   expected 5.4205 USDC, on-chain 5.4260 (DRIFT +0.0055)

Root cause (PLAN.md Session 16.6 finding): pre-fix, execute_settlement
wrote `confirmed` rows on Privy's 200 without verifying on-chain landing.
~11 settlements broadcast but never landed → DB confirmed but USDC stayed in
the campaign wallet.

This script transfers the missing 0.0055 USDC from the campaign wallet to
the publisher, reconciling DB and on-chain. After running this + restarting
auto-play (with the new wait_for_tx_confirmation logic), the audit should
return zero drift across all sections.

Usage:
    docker compose run --rm backend python scripts/cleanup_drift.py
    docker compose run --rm backend python scripts/cleanup_drift.py --execute
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import uuid4

sys.path.insert(0, "/app")

from sqlalchemy import func  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Campaign, Settlement, SettlementStatus  # noqa: E402
from app.services.privy import PrivyError, get_privy_client  # noqa: E402
from app.services.solana import (  # noqa: E402
    build_usdc_transfer_tx,
    get_usdc_balance_micro,
    wait_for_tx_confirmation,
)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--campaign",
        default="ac89a867-d1c6-4ba8-8b43-8b0ee001f2f7",
        help="campaign id to reconcile (default: the one in the audit)",
    )
    args = parser.parse_args()

    settings = get_settings()
    db = SessionLocal()
    privy = get_privy_client()

    c = db.query(Campaign).filter(Campaign.id == args.campaign).first()
    if not c:
        print(f"campaign {args.campaign} not found")
        return 1

    # Total expected to publisher across ALL campaigns (aggregate audit shape).
    # Session 16.9: amount_usdc is integer micro.
    total_expected_to_publisher_micro = int(
        db.query(func.coalesce(func.sum(Settlement.amount_usdc), 0))
        .filter(
            Settlement.status == SettlementStatus.CONFIRMED.value,
            Settlement.publisher_wallet == settings.demo_publisher_wallet,
        )
        .scalar()
    )

    on_chain_publisher_micro = await get_usdc_balance_micro(settings.demo_publisher_wallet)
    on_chain_campaign_micro = await get_usdc_balance_micro(c.wallet_address)
    db_remaining_micro = int(c.budget) - int(c.spent)
    drift_micro = on_chain_campaign_micro - db_remaining_micro
    publisher_short_micro = total_expected_to_publisher_micro - on_chain_publisher_micro

    print(f"campaign:           {c.id}")
    print(f"  status:           {c.status}")
    print(f"  budget - spent:   {db_remaining_micro/1_000_000:.6f}  (DB-expected on-chain)")
    print(f"  actual on-chain:  {on_chain_campaign_micro/1_000_000:.6f}")
    print(f"  drift:            {drift_micro/1_000_000:+.6f}  (this is what's stranded)")
    print()
    print("publisher (demo, AGGREGATE across all campaigns):")
    print(f"  expected from DB: {total_expected_to_publisher_micro/1_000_000:.6f}")
    print(f"  actual on-chain:  {on_chain_publisher_micro/1_000_000:.6f}")
    print(f"  publisher SHORT:  {publisher_short_micro/1_000_000:+.6f}")

    if drift_micro <= 0:
        print("\nno drift to clean up.")
        return 0

    # Sanity: the campaign's drift should be ≤ the aggregate publisher SHORT.
    # If campaign drift > publisher short, something else is stranded here
    # (e.g., orphaned protocol fee — different bug, different fix path).
    if drift_micro - publisher_short_micro > 1_000:  # > 0.001 USDC
        print(
            f"\n[ABORT] campaign drift ({drift_micro/1_000_000:+.6f}) exceeds publisher SHORT "
            f"({publisher_short_micro/1_000_000:+.6f}); the extra is from a different cause "
            f"(e.g. orphaned protocol fee). Investigate before transferring."
        )
        return 2

    print(
        f"\nproposed action: transfer {drift_micro/1_000_000:.6f} USDC from campaign → publisher\n"
        f"  this reconciles DB-says-paid against on-chain-paid for this campaign."
    )

    if not args.execute:
        print("\ndry-run only. Re-run with --execute to send.")
        return 0

    try:
        tx_b64 = await build_usdc_transfer_tx(
            from_address=c.wallet_address,
            to_address=settings.demo_publisher_wallet,
            amount_micro=drift_micro,
            memo=f"drift-cleanup:{uuid4().hex[:8]}",
        )
        tx_hash = await privy.sign_and_send_solana(
            wallet_id=c.wallet_id,
            transaction_base64=tx_b64,
            reference_id=f"drift-{c.id[:8]}-{uuid4().hex[:6]}",
        )
        print(f"\nbroadcast: {tx_hash}")
        confirmed = await wait_for_tx_confirmation(tx_hash, timeout_seconds=30)
        print(f"confirmed: {confirmed}")
    except (PrivyError, Exception) as e:  # noqa: BLE001
        print(f"\n[FAIL] {e}")
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
