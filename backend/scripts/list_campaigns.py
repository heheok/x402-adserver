"""Read-only admin view: list campaigns with status, money, and settlement counts.

    docker exec solboards-backend python scripts/list_campaigns.py
    docker exec solboards-backend python scripts/list_campaigns.py --status active
    docker exec solboards-backend python scripts/list_campaigns.py --advertiser did:privy:abc...
    docker exec solboards-backend python scripts/list_campaigns.py --id <campaign_id>   # one row + settlements breakdown
    docker exec solboards-backend python scripts/list_campaigns.py --limit 200

Pure DB read — no on-chain calls. For drift / on-chain reconciliation use audit_ledger.py.
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "/app")

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Campaign, Settlement, SettlementStatus  # noqa: E402


def _usdc(micro: int | None) -> str:
    return f"{(micro or 0) / 1_000_000:.6f}"


def _trim(s: str | None, n: int) -> str:
    if not s:
        return "—"
    return s if len(s) <= n else s[: n - 1] + "…"


def list_rows(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        stmt = select(Campaign).order_by(Campaign.created_at.desc())
        if args.status:
            stmt = stmt.where(Campaign.status == args.status)
        if args.advertiser:
            stmt = stmt.where(Campaign.advertiser_id == args.advertiser)
        if args.id:
            stmt = stmt.where(Campaign.id == args.id)
        if args.limit and not args.id:
            stmt = stmt.limit(args.limit)
        campaigns = db.scalars(stmt).all()

        if not campaigns:
            print("No campaigns match.")
            return 0

        # Per-campaign settlement aggregates in one query.
        agg_stmt = (
            select(
                Settlement.campaign_id,
                Settlement.status,
                func.count().label("n"),
                func.coalesce(func.sum(Settlement.amount_usdc), 0).label("sum"),
            )
            .where(Settlement.campaign_id.in_([c.id for c in campaigns]))
            .group_by(Settlement.campaign_id, Settlement.status)
        )
        agg: dict[str, dict[str, tuple[int, int]]] = {}
        for cid, status_, n, total in db.execute(agg_stmt):
            agg.setdefault(cid, {})[status_] = (n, total)

        header = (
            f"{'id':<14} {'advertiser':<22} {'name':<24} {'status':<10} "
            f"{'budget':>11} {'spent':>11} {'remaining':>11} "
            f"{'conf':>5} {'pend':>5} {'rev':>4} {'created':<19}"
        )
        print(header)
        print("-" * len(header))

        totals = {"budget": 0, "spent": 0, "remaining": 0, "conf": 0, "pend": 0, "rev": 0}
        for c in campaigns:
            a = agg.get(c.id, {})
            conf_n = a.get(SettlementStatus.CONFIRMED.value, (0, 0))[0]
            pend_n = a.get(SettlementStatus.PENDING.value, (0, 0))[0]
            flush_n = a.get(SettlementStatus.FLUSHING.value, (0, 0))[0]
            review_n = a.get(SettlementStatus.NEEDS_REVIEW.value, (0, 0))[0]
            in_flight_n = pend_n + flush_n
            remaining = (c.budget or 0) - (c.spent or 0)

            totals["budget"] += c.budget or 0
            totals["spent"] += c.spent or 0
            totals["remaining"] += remaining
            totals["conf"] += conf_n
            totals["pend"] += in_flight_n
            totals["rev"] += review_n

            created = c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else "—"
            print(
                f"{_trim(c.id, 14):<14} {_trim(c.advertiser_id, 22):<22} "
                f"{_trim(c.name, 24):<24} {c.status:<10} "
                f"{_usdc(c.budget):>11} {_usdc(c.spent):>11} {_usdc(remaining):>11} "
                f"{conf_n:>5} {in_flight_n:>5} {review_n:>4} {created:<19}"
            )

        print("-" * len(header))
        print(
            f"{'TOTAL':<14} {'':<22} {f'({len(campaigns)} rows)':<24} {'':<10} "
            f"{_usdc(totals['budget']):>11} {_usdc(totals['spent']):>11} "
            f"{_usdc(totals['remaining']):>11} "
            f"{totals['conf']:>5} {totals['pend']:>5} {totals['rev']:>4}"
        )

        if args.id and len(campaigns) == 1:
            _detail(db, campaigns[0])

    return 0


def _detail(db, c: Campaign) -> None:
    print()
    print("=" * 78)
    print(f"DETAIL — {c.id}")
    print("=" * 78)
    print(f"  name              : {c.name}")
    print(f"  advertiser_id     : {c.advertiser_id}")
    print(f"  advertiser_wallet : {c.advertiser_wallet}")
    print(f"  campaign wallet   : {c.wallet_address}")
    print(f"  status            : {c.status}")
    print(f"  cpm_price (micro) : {c.cpm_price}  ({_usdc(c.cpm_price)} USDC / 1000 plays)")
    print(f"  budget / spent    : {_usdc(c.budget)} / {_usdc(c.spent)} USDC")
    print(f"  duration          : {c.duration}s")
    print(f"  target_dmas       : {c.target_dmas or '—'}")
    print(f"  start / end       : {c.start_date or '—'} / {c.end_date or '—'}")
    print(f"  protocol_fee      : {_usdc(c.protocol_fee_amount)}  tx={c.protocol_fee_tx_hash or '—'}")
    print(f"  refund_tx_hash    : {c.refund_tx_hash or '—'}")
    print(f"  created_at        : {c.created_at}")

    rows = db.execute(
        select(
            Settlement.status,
            func.count().label("n"),
            func.coalesce(func.sum(Settlement.amount_usdc), 0).label("sum"),
        )
        .where(Settlement.campaign_id == c.id)
        .group_by(Settlement.status)
    ).all()
    if rows:
        print()
        print(f"  settlements: {'status':<14} {'count':>8} {'amount (USDC)':>16}")
        for status_, n, total in rows:
            print(f"               {status_:<14} {n:>8} {_usdc(total):>16}")


def main() -> int:
    p = argparse.ArgumentParser(description="List campaigns from the SQLite DB.")
    p.add_argument("--status", help="filter by status (draft|active|paused|completed|refunded|expired)")
    p.add_argument("--advertiser", help="filter by advertiser_id (Privy DID)")
    p.add_argument("--id", help="show a single campaign by id, with settlement breakdown")
    p.add_argument("--limit", type=int, default=50, help="max rows (default 50; ignored with --id)")
    return list_rows(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
