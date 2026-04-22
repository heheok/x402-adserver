"""Retry every pending-failed settlement in the database.

    docker compose run --rm backend python scripts/retry_settlements.py
    docker compose run --rm backend python scripts/retry_settlements.py --limit 20

Exit code: 0 if all attempts either confirmed or left untouched; 1 if any are
still failing after the retry so ops sees the failure in automation logs.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, "/app")

from app.database import SessionLocal  # noqa: E402
from app.services.privy import PrivyClient  # noqa: E402
from app.services.retry import retry_failed_settlements  # noqa: E402


async def main(limit: int) -> int:
    db = SessionLocal()
    try:
        privy = PrivyClient()
        results = await retry_failed_settlements(db, privy, limit=limit)
    finally:
        db.close()

    if not results:
        print("no failed settlements to retry")
        return 0

    confirmed = sum(1 for r in results if r.outcome == "confirmed")
    still_failing = sum(1 for r in results if r.outcome == "still_failing")
    skipped = sum(1 for r in results if r.outcome == "skipped")

    print(f"scanned {len(results)} failed settlement(s):")
    for r in results:
        line = f"  {r.outcome:<14} nonce={r.nonce}"
        if r.tx_hash:
            line += f" tx={r.tx_hash}"
        if r.error:
            line += f" error={r.error[:120]}"
        print(line)

    print()
    print(f"summary: {confirmed} confirmed, {still_failing} still failing, {skipped} skipped")
    return 0 if still_failing == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.limit)))
