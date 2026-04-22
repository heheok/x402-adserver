"""Pending-settlement retry stub.

When `POST /proof` cannot reach Privy or the facilitator, the request writes a
`Settlement` row with `status=failed` and `tx_hash=None` (see `routers/proof.py`).
Those rows are the queue. This module scans them and retries the USDC transfer,
flipping the row to `confirmed` on success.

Privy-side idempotency: every retry reuses `reference_id=settlement-<nonce>`, so
if the first attempt actually made it on-chain but our response was dropped,
Privy returns the original tx hash instead of double-paying.

Intentionally minimal — no scheduler, no backoff, no attempt counter. Ops runs
`scripts/retry_settlements.py` manually until Session 11 polish wires it up.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Campaign, Settlement, SettlementStatus
from .privy import PrivyClient, PrivyError
from .solana import build_usdc_transfer_tx

logger = logging.getLogger(__name__)


@dataclass
class RetryResult:
    settlement_id: str
    nonce: str
    outcome: str  # "confirmed" | "still_failing" | "skipped"
    tx_hash: str | None = None
    error: str | None = None


async def retry_failed_settlements(
    db: Session, privy: PrivyClient, limit: int = 50
) -> list[RetryResult]:
    """Retry every settlement row with status=failed, newest first.

    Stops at `limit` to keep one run bounded. Each attempt is independent —
    one failure does not halt the rest.
    """
    failed = (
        db.query(Settlement)
        .filter(Settlement.status == SettlementStatus.FAILED.value)
        .order_by(Settlement.created_at.desc())
        .limit(limit)
        .all()
    )
    results: list[RetryResult] = []

    for s in failed:
        campaign = db.query(Campaign).filter(Campaign.id == s.campaign_id).first()
        if campaign is None:
            results.append(
                RetryResult(s.id, s.nonce, "skipped", error="campaign missing")
            )
            continue

        try:
            tx_b64 = await build_usdc_transfer_tx(
                from_address=campaign.wallet_address,
                to_address=s.publisher_wallet,
                amount_usdc=float(s.amount_usdc),
            )
            tx_hash = await privy.sign_and_send_solana(
                wallet_id=campaign.wallet_id,
                transaction_base64=tx_b64,
                reference_id=f"settlement-{s.nonce}",
            )
        except (PrivyError, Exception) as e:  # noqa: BLE001
            logger.exception("retry failed settlement=%s nonce=%s", s.id, s.nonce)
            results.append(
                RetryResult(s.id, s.nonce, "still_failing", error=str(e))
            )
            continue

        s.status = SettlementStatus.CONFIRMED.value
        s.tx_hash = tx_hash
        db.commit()
        logger.info("retry confirmed settlement=%s tx=%s", s.id, tx_hash)
        results.append(RetryResult(s.id, s.nonce, "confirmed", tx_hash=tx_hash))

    return results
