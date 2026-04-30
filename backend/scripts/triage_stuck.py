"""Manual triage tool for settlements parked in NEEDS_REVIEW.

When a batch settlement's on-chain fate becomes ambiguous (process death
mid-flush, Privy 5xx after broadcast, or Privy 400 "already exists"), the
batch_settler parks the rows in NEEDS_REVIEW instead of retrying — retries
drain the campaign wallet because Privy's reference_id check fires after
broadcast (PLAN.md must-fix #4). This script lists those rows and lets an
operator resolve each one based on what actually happened on-chain.

Workflow:

    # 1. List stuck rows (groups by batch — same memo + same campaign +
    #    same publisher → one batch tx if it landed)
    docker compose run --rm backend python scripts/triage_stuck.py list

    # 2. For each batch, eyeball the campaign wallet's recent txs on
    #    Solscan (URL printed in the list output). Look for a tx whose
    #    memo matches the printed memo. If found:
    docker compose run --rm backend python scripts/triage_stuck.py confirm \\
        --row-ids ID1,ID2,... --tx-hash <hash from solscan>

    # 2b. If the tx genuinely never landed (no matching memo on-chain
    #     after blockhash expiry, ~2 minutes after row creation):
    docker compose run --rm backend python scripts/triage_stuck.py compensate \\
        --row-ids ID1,ID2,...

`confirm` marks the rows CONFIRMED with the operator-supplied tx hash and
leaves `spent` untouched (the on-chain payment did happen, the DB just
needs to catch up).

`compensate` decrements `spent` by the row amounts and flips status to
FAILED — same path the batch_settler takes for clean pre-broadcast
refusals. Use ONLY when you have positive evidence the broadcast did NOT
land (no matching memo on-chain past the blockhash window).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")

from sqlalchemy import case, update  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Campaign,
    CampaignStatus,
    Settlement,
    SettlementStatus,
)
from app.services.batch_settler import build_batch_identifiers  # noqa: E402


def _solscan_account_url(addr: str) -> str:
    return f"https://solscan.io/account/{addr}?cluster=devnet"


def _solscan_tx_url(tx_hash: str) -> str:
    return f"https://solscan.io/tx/{tx_hash}?cluster=devnet"


def cmd_list() -> int:
    db = SessionLocal()
    try:
        rows = (
            db.query(Settlement, Campaign)
            .join(Campaign, Settlement.campaign_id == Campaign.id)
            .filter(Settlement.status == SettlementStatus.NEEDS_REVIEW.value)
            .order_by(Settlement.created_at.asc())
            .all()
        )
        if not rows:
            print("No rows in NEEDS_REVIEW. Nothing to triage.")
            return 0

        # Group by (campaign, publisher) — same as batch_settler does.
        groups: dict[tuple[str, str], list[tuple[Settlement, Campaign]]] = {}
        for s, c in rows:
            groups.setdefault((s.campaign_id, s.publisher_wallet), []).append((s, c))

        print(f"{len(rows)} row(s) in NEEDS_REVIEW across {len(groups)} batch group(s)\n")
        for (campaign_id, publisher), members in groups.items():
            members.sort(key=lambda m: m[0].created_at)
            first_settlement, campaign = members[0]
            memo, reference_id = build_batch_identifiers(
                campaign_id, first_settlement.nonce, len(members)
            )
            total_micro = sum(int(s.amount_usdc) for s, _ in members)
            ages = [
                (datetime.now(timezone.utc) - (s.created_at.replace(tzinfo=timezone.utc) if s.created_at and s.created_at.tzinfo is None else s.created_at)).total_seconds()
                for s, _ in members if s.created_at
            ]
            oldest_age = max(ages) if ages else 0

            print("─" * 78)
            print(f"  Campaign: {campaign.name!r} ({campaign_id})")
            print(f"     status={campaign.status}  budget={campaign.budget} spent={campaign.spent}")
            print(f"     wallet: {campaign.wallet_address}")
            print(f"             {_solscan_account_url(campaign.wallet_address)}")
            print(f"  Publisher: {publisher}")
            print(f"  Batch memo (look for this on-chain): {memo!r}")
            print(f"  Reference id: {reference_id!r}")
            print(f"  Rows: {len(members)}  total_micro={total_micro} ({total_micro/1_000_000:.6f} USDC)")
            print(f"  Oldest row age: {oldest_age:.0f}s")
            print()
            print("  Settlement IDs (pass to --row-ids comma-separated):")
            for s, _ in members:
                print(
                    f"    {s.id}  amount_micro={s.amount_usdc:>6}  "
                    f"created={s.created_at.isoformat() if s.created_at else '?'}"
                )
            print()
        return 0
    finally:
        db.close()


def _parse_row_ids(s: str) -> list[str]:
    ids = [x.strip() for x in s.split(",") if x.strip()]
    if not ids:
        raise argparse.ArgumentTypeError("--row-ids must contain at least one id")
    return ids


def cmd_confirm(row_ids: list[str], tx_hash: str) -> int:
    db = SessionLocal()
    try:
        rows = (
            db.query(Settlement)
            .filter(Settlement.id.in_(row_ids))
            .filter(Settlement.status == SettlementStatus.NEEDS_REVIEW.value)
            .all()
        )
        if not rows:
            print(f"[ERROR] no rows matched (must currently be NEEDS_REVIEW): {row_ids}")
            return 1
        missing = set(row_ids) - {r.id for r in rows}
        if missing:
            print(f"[WARN] {len(missing)} id(s) not found or not NEEDS_REVIEW: {missing}")

        result = db.execute(
            update(Settlement)
            .where(Settlement.id.in_([r.id for r in rows]))
            .values(status=SettlementStatus.CONFIRMED.value, tx_hash=tx_hash)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        print(f"  Marked {result.rowcount} row(s) CONFIRMED with tx_hash={tx_hash}")
        print(f"  Solscan: {_solscan_tx_url(tx_hash)}")
        return 0
    finally:
        db.close()


def cmd_compensate(row_ids: list[str]) -> int:
    db = SessionLocal()
    try:
        rows = (
            db.query(Settlement)
            .filter(Settlement.id.in_(row_ids))
            .filter(Settlement.status == SettlementStatus.NEEDS_REVIEW.value)
            .all()
        )
        if not rows:
            print(f"[ERROR] no rows matched (must currently be NEEDS_REVIEW): {row_ids}")
            return 1
        missing = set(row_ids) - {r.id for r in rows}
        if missing:
            print(f"[WARN] {len(missing)} id(s) not found or not NEEDS_REVIEW: {missing}")

        # Per-row compensating UPDATE on the campaign — same shape as
        # batch_settler._compensate_failed: refund spent and flip
        # COMPLETED -> ACTIVE if the refund creates room for one more play.
        for r in rows:
            amount_micro = int(r.amount_usdc)
            db.execute(
                update(Campaign)
                .where(Campaign.id == r.campaign_id)
                .values(
                    spent=Campaign.spent - amount_micro,
                    status=case(
                        (
                            (Campaign.status == CampaignStatus.COMPLETED.value)
                            & (
                                Campaign.budget
                                - (Campaign.spent - amount_micro)
                                >= Campaign.cpm_price / 1000
                            ),
                            CampaignStatus.ACTIVE.value,
                        ),
                        else_=Campaign.status,
                    ),
                )
                .execution_options(synchronize_session=False)
            )
        db.execute(
            update(Settlement)
            .where(Settlement.id.in_([r.id for r in rows]))
            .values(status=SettlementStatus.FAILED.value)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        print(
            f"  Compensated {len(rows)} row(s): spent decremented, status -> FAILED"
        )
        return 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list rows currently in NEEDS_REVIEW")

    p_confirm = sub.add_parser(
        "confirm",
        help="mark rows CONFIRMED with the operator-supplied tx hash",
    )
    p_confirm.add_argument(
        "--row-ids", required=True, type=_parse_row_ids,
        help="comma-separated settlement IDs",
    )
    p_confirm.add_argument(
        "--tx-hash", required=True,
        help="the on-chain tx signature you found via Solscan",
    )

    p_comp = sub.add_parser(
        "compensate",
        help="mark rows FAILED and decrement campaign.spent (use only when "
             "you have positive evidence the broadcast did not land)",
    )
    p_comp.add_argument(
        "--row-ids", required=True, type=_parse_row_ids,
        help="comma-separated settlement IDs",
    )

    args = parser.parse_args()

    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "confirm":
        return cmd_confirm(args.row_ids, args.tx_hash)
    if args.cmd == "compensate":
        return cmd_compensate(args.row_ids)
    return 1


if __name__ == "__main__":
    sys.exit(main())
