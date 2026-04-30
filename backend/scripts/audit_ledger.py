"""Read-only reconciliation: DB state vs on-chain USDC balances.

Run:
    docker compose run --rm backend python scripts/audit_ledger.py

Three sections:

  1. Publisher reconciliation
     For every publisher_wallet that's received at least one confirmed
     settlement: sum of `amount_usdc` (DB, microUSDC) vs on-chain USDC token
     balance (atomic units).
     SHORT  = on-chain < DB        → bug (we owe / settlement got lost)
     OK     = on-chain == DB       → exact match
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
     DRIFT lines on REFUNDED rows quantify §1.1's leak in micro.

  3. Service wallets — orientation only.

Session 16.9: every comparison is exact integer microUSDC. No tolerance.
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
from app.services.solana import get_usdc_balance_micro  # noqa: E402


def _fmt_micro(micro: int) -> str:
    """Format micro as USDC with 6dp for display (audit precision)."""
    sign = "-" if micro < 0 else ""
    a = abs(int(micro))
    return f"{sign}{a // 1_000_000}.{a % 1_000_000:06d}"


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
    for wallet, expected_micro, n in rows:
        expected = int(expected_micro)
        actual = await get_usdc_balance_micro(wallet)
        diff = actual - expected
        if diff < 0:
            flag = "SHORT"
            short_count += 1
        elif diff == 0:
            flag = "OK"
        else:
            flag = "MORE"  # other inflows; not a bug
        print(
            f"  {_trunc(wallet, 14):<20} {n:>6} "
            f"{_fmt_micro(expected):>14} {_fmt_micro(actual):>14} "
            f"{('+' if diff >= 0 else '') + _fmt_micro(diff):>14}  {flag}"
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

    # Session 16.8: per-campaign pending settlement totals. The /proof atomic
    # UPDATE reserves budget at queue time (so `spent` already reflects them),
    # but the USDC hasn't transferred out of the campaign wallet yet —
    # on-chain balance reads HIGH by `pending_total` until the batch flushes.
    # That's IN-FLIGHT, not DRIFT.
    pending_rows = (
        db.query(
            Settlement.campaign_id,
            func.count(Settlement.id),
            func.coalesce(func.sum(Settlement.amount_usdc), 0),
        )
        .filter(
            Settlement.status.in_(
                (SettlementStatus.PENDING.value, SettlementStatus.FLUSHING.value)
            )
        )
        .group_by(Settlement.campaign_id)
        .all()
    )
    pending_by_campaign: dict[str, tuple[int, int]] = {
        cid: (int(n), int(amt)) for cid, n, amt in pending_rows
    }

    print(
        f"  {'campaign':<32} {'status':<10} {'expected':>10} {'actual':>10} {'diff':>10} {'pending':>9}  flag"
    )
    print(f"  {'-'*32} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*9}  {'-'*9}")

    drift_total_micro = 0
    in_flight_total_micro = 0
    refunded_orphaned_fee_micro = 0
    refunded_stranded_total_micro = 0

    for c in campaigns:
        if not c.wallet_address:
            continue
        budget = int(c.budget or 0)
        spent = int(c.spent or 0)
        fee = int(c.protocol_fee_amount or 0)
        fee_paid = bool(c.protocol_fee_tx_hash)
        pending_n, pending_amt_micro = pending_by_campaign.get(c.id, (0, 0))

        if c.status == CampaignStatus.DRAFT.value:
            expected = 0
        elif c.status == CampaignStatus.REFUNDED.value:
            # Refund only sends `budget - spent`; orphaned fee stays put.
            expected = fee if not fee_paid else 0
        else:
            # active / paused / completed / expired — funded, possibly mid-flight.
            expected = (budget - spent) + (fee if not fee_paid else 0)

        actual = await get_usdc_balance_micro(c.wallet_address)
        diff = actual - expected

        # IN-FLIGHT: actual is HIGH by exactly pending_amt_micro.
        post_flush_diff = diff - pending_amt_micro
        if diff == 0:
            flag = "OK"
        elif pending_n > 0 and post_flush_diff == 0:
            flag = "IN-FLIGHT"
            in_flight_total_micro += pending_amt_micro
        else:
            flag = "DRIFT"
            drift_total_micro += abs(diff)

        if c.status == CampaignStatus.REFUNDED.value:
            refunded_stranded_total_micro += actual
            if not fee_paid:
                refunded_orphaned_fee_micro += fee

        pending_str = (
            f"{pending_n}/{_fmt_micro(pending_amt_micro)[:6]}" if pending_n else "—"
        )
        print(
            f"  {c.id[:32]:<32} {c.status:<10} "
            f"{_fmt_micro(expected)[:10]:>10} {_fmt_micro(actual)[:10]:>10} "
            f"{(('+' if diff >= 0 else '') + _fmt_micro(diff))[:10]:>10} "
            f"{pending_str:>9}  {flag}"
        )

    print()
    print(
        f"  Refunded campaigns — total stranded USDC on-chain: "
        f"{_fmt_micro(refunded_stranded_total_micro)}"
    )
    print(
        f"  Of that, declared orphaned fee (BACKEND-REVIEW §1.1): "
        f"{_fmt_micro(refunded_orphaned_fee_micro)}"
    )
    if in_flight_total_micro > 0:
        print(
            f"  ⏳ in-flight (queued, not yet on-chain): "
            f"{_fmt_micro(in_flight_total_micro)} USDC"
        )
    if drift_total_micro > 0:
        print(
            f"  ⚠  cumulative |drift| across DRIFT rows: "
            f"{_fmt_micro(drift_total_micro)} USDC"
        )
    elif in_flight_total_micro == 0:
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
        sol, usdc_micro = await asyncio.gather(
            _get_sol_balance(client, address),
            get_usdc_balance_micro(address),
        )
        print(
            f"  {role:<18} {_trunc(address, 16):<22} "
            f"{sol:>14.6f} {_fmt_micro(usdc_micro):>14}"
        )


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
