"""Read-only reconciliation: DB state vs on-chain USDC balances.

Run:
    docker compose run --rm backend python scripts/audit_ledger.py

Three sections:

  1. Publisher reconciliation
     For every publisher_wallet that's received at least one confirmed
     settlement: sum of `amount_usdc` (DB) vs `get_usdc_balance` (on-chain).
     SHORT  = on-chain < DB        → bug (we owe / settlement got lost)
     OK     = on-chain == DB       → green
     MORE   = on-chain > DB        → ignore on devnet for our test publisher,
                                      expected for real publishers

  2. Campaign wallet reconciliation
     Per campaign, expected on-chain USDC depends on lifecycle stage:
       DRAFT       → 0 (never funded)
       ACTIVE/PAUSED/COMPLETED/EXPIRED →
         budget - spent (+ protocol_fee_amount if fee tx never confirmed)
       REFUNDED    → 0 (+ protocol_fee_amount if fee was orphaned —
                        BACKEND-REVIEW.md §1.1: refund only sends
                        budget - spent, leaks orphaned fee permanently)
     DRIFT lines on REFUNDED rows quantify §1.1's leak in dollars.

  3. Service wallet balances
     Treasury, protocol revenue, helpers, demo publisher — just print SOL +
     USDC for orientation. No expected vs actual; treasuries fluctuate.

Tolerance: 1e-6 USDC (= 1 microUSDC, the smallest possible on-chain unit).
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

from solana.rpc.async_api import AsyncClient  # noqa: E402
from solders.pubkey import Pubkey  # noqa: E402
from sqlalchemy import func  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Campaign, CampaignStatus, Settlement, SettlementStatus  # noqa: E402
from app.services.solana import get_usdc_balance  # noqa: E402


USDC_TOLERANCE = 1e-6
CAMPAIGN_TOLERANCE = 1e-3  # campaign wallets carry a few cents of dust from float math


def _trunc(addr: str, n: int = 6) -> str:
    return f"{addr[:n]}…{addr[-4:]}" if len(addr) > n + 4 else addr


async def _get_sol_balance(client: AsyncClient, address: str) -> float:
    try:
        resp = await client.get_balance(Pubkey.from_string(address))
        return (resp.value or 0) / 1_000_000_000
    except Exception:  # noqa: BLE001 — report 0, don't fail the audit
        return 0.0


async def _section_publishers(db) -> None:
    print("=" * 78)
    print("1. PUBLISHER RECONCILIATION")
    print("=" * 78)
    rows = (
        db.query(
            Settlement.publisher_wallet,
            func.coalesce(func.sum(Settlement.amount_usdc), 0),
            func.count(Settlement.id),
        )
        .filter(Settlement.status == SettlementStatus.CONFIRMED.value)
        .group_by(Settlement.publisher_wallet)
        .all()
    )
    if not rows:
        print("  (no confirmed settlements in DB)")
        return

    print(f"  {'wallet':<20} {'plays':>6} {'expected':>14} {'actual':>14} {'diff':>14}  flag")
    print(f"  {'-'*20} {'-'*6} {'-'*14} {'-'*14} {'-'*14}  {'-'*5}")
    short_count = 0
    for wallet, expected, n in rows:
        expected = float(expected)
        actual = await get_usdc_balance(wallet)
        diff = actual - expected
        if diff < -USDC_TOLERANCE:
            flag = "SHORT"
            short_count += 1
        elif abs(diff) <= USDC_TOLERANCE:
            flag = "OK"
        else:
            flag = "MORE"  # other inflows; not a bug
        print(
            f"  {_trunc(wallet, 14):<20} {n:>6} {expected:>14.6f} {actual:>14.6f} {diff:>+14.6f}  {flag}"
        )

    if short_count:
        print(f"\n  ⚠  {short_count} publisher(s) flagged SHORT — on-chain less than DB says we paid.")
    else:
        print("\n  ✓ no SHORT flags — every confirmed settlement landed on-chain.")


async def _section_campaigns(db) -> None:
    print()
    print("=" * 78)
    print("2. CAMPAIGN WALLET RECONCILIATION")
    print("=" * 78)
    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
    if not campaigns:
        print("  (no campaigns)")
        return

    print(
        f"  {'campaign':<32} {'status':<10} {'expected':>10} {'actual':>10} {'diff':>10}  flag"
    )
    print(f"  {'-'*32} {'-'*10} {'-'*10} {'-'*10} {'-'*10}  {'-'*5}")

    drift_total = 0.0
    refunded_orphaned_fee = 0.0
    refunded_stranded_total = 0.0

    for c in campaigns:
        if not c.wallet_address:
            continue
        budget = float(c.budget or 0)
        spent = float(c.spent or 0)
        fee = float(c.protocol_fee_amount or 0)
        fee_paid = bool(c.protocol_fee_tx_hash)

        if c.status == CampaignStatus.DRAFT.value:
            expected = 0.0
        elif c.status == CampaignStatus.REFUNDED.value:
            # Refund only sends `budget - spent`; orphaned fee stays put.
            expected = fee if not fee_paid else 0.0
        else:
            # active / paused / completed / expired — funded, possibly mid-flight.
            expected = (budget - spent) + (fee if not fee_paid else 0.0)

        actual = await get_usdc_balance(c.wallet_address)
        diff = actual - expected

        if abs(diff) <= CAMPAIGN_TOLERANCE:
            flag = "OK"
        else:
            flag = "DRIFT"
            drift_total += abs(diff)

        if c.status == CampaignStatus.REFUNDED.value:
            refunded_stranded_total += actual
            if not fee_paid:
                refunded_orphaned_fee += fee

        print(
            f"  {c.id[:32]:<32} {c.status:<10} {expected:>10.4f} {actual:>10.4f} {diff:>+10.4f}  {flag}"
        )

    print()
    print(f"  Refunded campaigns — total stranded USDC on-chain: {refunded_stranded_total:.4f}")
    print(f"  Of that, declared orphaned fee (BACKEND-REVIEW §1.1): {refunded_orphaned_fee:.4f}")
    if drift_total > 0:
        print(f"  ⚠  cumulative |drift| across DRIFT rows: {drift_total:.4f} USDC")
    else:
        print("  ✓ no DRIFT rows (every campaign matches expected).")


async def _section_service_wallets(client: AsyncClient) -> None:
    print()
    print("=" * 78)
    print("3. SERVICE WALLETS")
    print("=" * 78)
    settings = get_settings()

    targets: list[tuple[str, str]] = []
    if settings.treasury_wallet_address:
        targets.append(("treasury", settings.treasury_wallet_address))
    if settings.protocol_revenue_wallet_address:
        targets.append(("protocol revenue", settings.protocol_revenue_wallet_address))
    if settings.helper_wallet_addresses:
        for i, addr in enumerate(
            a.strip() for a in settings.helper_wallet_addresses.split(",") if a.strip()
        ):
            targets.append((f"helper {i}", addr))
    if settings.demo_publisher_wallet:
        targets.append(("demo publisher", settings.demo_publisher_wallet))

    print(f"  {'role':<18} {'address':<22} {'SOL':>14} {'USDC':>14}")
    print(f"  {'-'*18} {'-'*22} {'-'*14} {'-'*14}")
    for role, address in targets:
        sol, usdc = await asyncio.gather(
            _get_sol_balance(client, address),
            get_usdc_balance(address),
        )
        print(f"  {role:<18} {_trunc(address, 16):<22} {sol:>14.6f} {usdc:>14.6f}")


async def main() -> int:
    settings = get_settings()
    db = SessionLocal()
    try:
        async with AsyncClient(settings.solana_rpc_url) as client:
            await _section_publishers(db)
            await _section_campaigns(db)
            await _section_service_wallets(client)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
