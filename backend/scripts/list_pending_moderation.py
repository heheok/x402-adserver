"""Read-only admin view: list creative moderation rows (Session 19.5).

    docker exec solboards-backend python scripts/list_pending_moderation.py
    docker exec solboards-backend python scripts/list_pending_moderation.py --status review
    docker exec solboards-backend python scripts/list_pending_moderation.py --status reject
    docker exec solboards-backend python scripts/list_pending_moderation.py --advertiser did:privy:abc...
    docker exec solboards-backend python scripts/list_pending_moderation.py --id <creative_id>
    docker exec solboards-backend python scripts/list_pending_moderation.py --limit 200

Pure DB read — no Vertex API calls. The default view filters to verdict=review
(the bucket that needs admin attention); pass --status approve|reject|all to
expand. Manual approve/reject CLIs (writes to reviewed_by / review_decision)
are deferred to a future session — this is read-only.
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Moderation  # noqa: E402


def _trim(s: str | None, n: int) -> str:
    if not s:
        return "—"
    return s if len(s) <= n else s[: n - 1] + "…"


def _join(items: list[str] | None, n: int) -> str:
    if not items:
        return "—"
    joined = ", ".join(items)
    return _trim(joined, n)


def list_rows(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        stmt = select(Moderation).order_by(Moderation.created_at.desc())
        if args.id:
            stmt = stmt.where(Moderation.creative_id == args.id)
        else:
            if args.status and args.status != "all":
                stmt = stmt.where(Moderation.verdict == args.status)
            if args.advertiser:
                stmt = stmt.where(Moderation.advertiser_id == args.advertiser)
            if args.limit:
                stmt = stmt.limit(args.limit)

        rows = db.scalars(stmt).all()
        if not rows:
            print("No moderation rows match.")
            return 0

        header = (
            f"{'creative_id':<14} {'advertiser':<22} {'verdict':<8} "
            f"{'conf':>5} {'categories':<32} {'created':<19}"
        )
        print(header)
        print("-" * len(header))

        counts: dict[str, int] = {}
        for r in rows:
            counts[r.verdict] = counts.get(r.verdict, 0) + 1
            created = r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "—"
            print(
                f"{_trim(r.creative_id, 14):<14} {_trim(r.advertiser_id, 22):<22} "
                f"{r.verdict:<8} {r.confidence:>5.2f} "
                f"{_join(r.categories_flagged, 32):<32} {created:<19}"
            )
            # Full reasons indented under each row — never truncated, since
            # the reason text is what tells the operator *why* it landed in
            # this bucket. Empty list = no reasons (clean approve).
            for reason in r.reasons or []:
                print(f"  · {reason}")

        print("-" * len(header))
        breakdown = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"TOTAL ({len(rows)} rows)   {breakdown}")

        if args.id and len(rows) == 1:
            _detail(rows[0])

    return 0


def _detail(r: Moderation) -> None:
    print()
    print("=" * 78)
    print(f"DETAIL — {r.creative_id}")
    print("=" * 78)
    print(f"  creative_url      : {r.creative_url or '— (rejected, not uploaded)'}")
    print(f"  advertiser_id     : {r.advertiser_id}")
    print(f"  verdict           : {r.verdict}")
    print(f"  confidence        : {r.confidence:.3f}")
    print(f"  categories        : {r.categories_flagged or '—'}")
    print(f"  reasons           :")
    for reason in r.reasons or []:
        print(f"    · {reason}")
    print(f"  created_at        : {r.created_at}")
    if r.reviewed_by:
        print(f"  reviewed_by       : {r.reviewed_by}")
        print(f"  reviewed_at       : {r.reviewed_at}")
        print(f"  review_decision   : {r.review_decision}")


def main() -> int:
    p = argparse.ArgumentParser(description="List creative moderation rows.")
    p.add_argument(
        "--status",
        default="review",
        help="filter by verdict (review|reject|approve|all). Default: review.",
    )
    p.add_argument("--advertiser", help="filter by advertiser_id (Privy DID)")
    p.add_argument("--id", help="show a single moderation row by creative_id")
    p.add_argument("--limit", type=int, default=50, help="max rows (default 50)")
    return list_rows(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
