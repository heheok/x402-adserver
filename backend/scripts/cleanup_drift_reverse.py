"""Reverse-direction drift cleanup: publisher → campaigns.

The audit (scripts/audit_ledger.py) currently shows:

  publisher 3pMCrwRq…V8W9: +0.0055 USDC MORE on-chain than DB
  campaign  c298e3bc:      -0.0030 DRIFT (on-chain short of DB)
  campaign  ac89a867:      -0.0025 DRIFT (on-chain short of DB)

Root cause: the α + γ_safe + γ_extra iteration was rate-limited by public
devnet RPC during a high-concurrency burst. wait_for_tx_confirmation went
blind (429s), γ_extra get_signature_status also went blind (also 429s),
returned None → code interpreted as "definitively dead" → compensating
UPDATE rolled `spent` back AND wrote `failed` settlement rows for txs
that ACTUALLY landed on-chain.

Result: publisher got paid 0.0055 USDC for plays the DB now says failed.

This script transfers the missing USDC from publisher back to each
affected campaign wallet, zeroing out all three audit flags before the
new batch-settlement code begins processing.

Usage:
    docker compose run --rm backend python scripts/cleanup_drift_reverse.py
    docker compose run --rm backend python scripts/cleanup_drift_reverse.py --execute
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import uuid4

sys.path.insert(0, "/app")

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Campaign  # noqa: E402
from app.services.privy import PrivyClient, PrivyError, get_privy_client  # noqa: E402
from app.services.solana import (  # noqa: E402
    build_usdc_transfer_tx,
    get_usdc_balance,
    wait_for_tx_confirmation,
)


async def _resolve_publisher_wallet_id(privy: PrivyClient, address: str) -> str | None:
    """Walk the Privy wallet list to find the wallet_id for an address."""
    cursor: str | None = None
    while True:
        page = await privy.list_wallets(cursor=cursor)
        for w in page.get("data", []):
            if w.get("address") == address:
                return w.get("id")
        cursor = page.get("next_cursor")
        if not cursor:
            return None


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    db = SessionLocal()
    privy = get_privy_client()

    publisher = settings.demo_publisher_wallet
    publisher_wallet_id = await _resolve_publisher_wallet_id(privy, publisher)
    if not publisher_wallet_id:
        print(f"[ABORT] couldn't resolve wallet_id for publisher {publisher}")
        return 1

    publisher_balance = await get_usdc_balance(publisher)
    print(f"publisher: {publisher}")
    print(f"  wallet_id:        {publisher_wallet_id}")
    print(f"  on-chain USDC:    {publisher_balance:.6f}")
    print()

    # Compute per-campaign drift from DB vs on-chain. Only target campaigns
    # whose on-chain balance is BELOW their DB-expected `budget - spent`.
    candidates = (
        db.query(Campaign)
        .filter(Campaign.wallet_address.isnot(None))
        .filter(Campaign.status.in_(["active", "paused", "completed", "expired"]))
        .all()
    )

    transfers: list[tuple[Campaign, float]] = []
    for c in candidates:
        on_chain = await get_usdc_balance(c.wallet_address)
        db_remaining = float(c.budget) - float(c.spent)
        # Match the audit's expected calculation: include unpaid protocol
        # fee. Without this, a campaign with an unpaid fee can hide
        # settlement drift behind the still-in-wallet fee USDC.
        unpaid_fee = (
            float(c.protocol_fee_amount or 0) if not c.protocol_fee_tx_hash else 0.0
        )
        expected = db_remaining + unpaid_fee
        drift = expected - on_chain  # positive = campaign short
        if drift > 1e-6:
            transfers.append((c, drift))
            print(f"campaign {c.id[:8]}  status={c.status}")
            print(f"  budget - spent (DB):  {db_remaining:.6f}")
            if unpaid_fee > 0:
                print(f"  unpaid protocol fee:  +{unpaid_fee:.6f}")
            print(f"  expected on-chain:    {expected:.6f}")
            print(f"  on-chain:             {on_chain:.6f}")
            print(f"  needs:                +{drift:.6f}")
            print()

    if not transfers:
        print("no campaigns short of DB-expected. nothing to do.")
        return 0

    total_needed = sum(amt for _, amt in transfers)
    print(f"total to transfer publisher → campaigns: {total_needed:.6f} USDC")
    print(f"publisher has: {publisher_balance:.6f} USDC")
    if total_needed > publisher_balance + 1e-6:
        print(f"[ABORT] publisher doesn't hold enough USDC")
        return 2

    if not args.execute:
        print("\ndry-run only. Re-run with --execute to send.")
        return 0

    print()
    for c, amount in transfers:
        try:
            tx_b64 = await build_usdc_transfer_tx(
                from_address=publisher,
                to_address=c.wallet_address,
                amount_usdc=amount,
                memo=f"drift-rev:{uuid4().hex[:8]}",
            )
            tx_hash = await privy.sign_and_send_solana(
                wallet_id=publisher_wallet_id,
                transaction_base64=tx_b64,
                reference_id=f"drift-rev-{c.id[:8]}-{uuid4().hex[:6]}",
            )
            print(f"  {c.id[:8]}  +{amount:.6f}  tx={tx_hash}")
            confirmed = await wait_for_tx_confirmation(tx_hash, timeout_seconds=30)
            print(f"             confirmed={confirmed}")
        except (PrivyError, Exception) as e:  # noqa: BLE001
            print(f"  {c.id[:8]}  FAILED: {e}")
            return 3

    print("\ndone. re-run scripts/audit_ledger.py to confirm zero drift.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
