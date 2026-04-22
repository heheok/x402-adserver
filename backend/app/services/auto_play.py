"""Demo-only background loop that auto-settles plays on active campaigns.

Purpose: in a live demo we want the advertiser dashboard to visibly tick along
without the judge having to click "Simulate play" twenty times. When enabled
via the `AUTO_PLAY_ENABLED` env flag, a single asyncio task runs for the life
of the backend process and, every `auto_play_interval_seconds`, randomly picks
one active + sufficiently-funded campaign and runs the same `execute_settlement`
pipeline that `/proof` uses.

**This is not how production works.** Real publishers serve ads and call /bid
+ /proof with their own API key and wallet. Auto-play exists only to make the
demo feel alive; it mints `ProofContextClaims` server-side against the
`DEMO_PUBLISHER_WALLET` address. Do not enable in production.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from uuid import uuid4

from fastapi import HTTPException

from ..config import get_settings
from ..database import SessionLocal
from ..models import Campaign, CampaignStatus
from ..services.privy import PrivyClient
from ..services.tokens import ProofContextClaims

logger = logging.getLogger(__name__)


async def _tick(privy: PrivyClient) -> None:
    """Run one iteration: pick a random active + funded campaign and settle."""
    # Local import to avoid a circular at module load time
    # (routers/proof -> services/solana -> ... -> services/auto_play).
    from ..routers.proof import execute_settlement

    settings = get_settings()
    db = SessionLocal()
    try:
        actives = (
            db.query(Campaign)
            .filter(Campaign.status == CampaignStatus.ACTIVE.value)
            .all()
        )
        funded = [
            c
            for c in actives
            if float(c.budget) - float(c.spent) + 1e-9
            >= float(c.cpm_price) / 1000.0
        ]
        if not funded:
            return

        campaign = random.choice(funded)
        amount = float(campaign.cpm_price) / 1000.0
        claims = ProofContextClaims(
            campaign_id=campaign.id,
            bid_id=f"auto-{uuid4().hex[:8]}",
            wallet_id=settings.demo_publisher_wallet,
            nonce=f"auto-{uuid4().hex}",
            created_at=int(time.time()),
            amount_usdc=amount,
        )

        try:
            tx_hash = await execute_settlement(claims, db, privy)
            logger.info(
                "auto-play: campaign=%s amount=%s tx=%s",
                campaign.id,
                amount,
                tx_hash[:16] + "…",
            )
        except HTTPException as e:
            # Typical on a drained or freshly-paused campaign between tick
            # and settlement — log at info level, not an error.
            logger.info(
                "auto-play skipped campaign=%s status=%d detail=%s",
                campaign.id,
                e.status_code,
                e.detail,
            )
    finally:
        db.close()


async def run_auto_play_loop(stop_event: asyncio.Event) -> None:
    """Long-running task: ticks forever (until `stop_event` is set)."""
    settings = get_settings()
    if not settings.auto_play_enabled:
        logger.info("auto-play disabled (AUTO_PLAY_ENABLED=false)")
        return

    privy = PrivyClient()
    interval = max(1, int(settings.auto_play_interval_seconds))
    logger.info("auto-play loop starting — interval=%ds", interval)

    while not stop_event.is_set():
        try:
            await _tick(privy)
        except Exception:
            logger.exception("auto-play iteration crashed; continuing")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue  # expected — interval elapsed, go again

    logger.info("auto-play loop stopped")
