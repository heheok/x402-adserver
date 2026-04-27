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
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from ..config import get_settings
from ..database import SessionLocal
from ..models import Campaign, CampaignStatus
from ..services.privy import PrivyClient
from ..services.tokens import ProofContextClaims
from ..services.venues import get_venues_index

logger = logging.getLogger(__name__)


async def _tick(privy: PrivyClient) -> None:
    """Run one iteration: pick a random eligible campaign + device and settle."""
    # Local import to avoid a circular at module load time
    # (routers/proof -> services/solana -> ... -> services/auto_play).
    from ..routers.proof import execute_settlement

    settings = get_settings()
    venues = get_venues_index()
    today = datetime.now(timezone.utc).date()
    db = SessionLocal()
    try:
        actives = (
            db.query(Campaign)
            .filter(Campaign.status == CampaignStatus.ACTIVE.value)
            .all()
        )
        # Eligibility: funded for one play, schedule window contains today,
        # has at least one device in the selected DMAs. Schedule + DMA
        # filtering mirrors /bid so the demo only ever simulates plays the
        # campaign's targeting would actually accept.
        eligible: list[tuple[Campaign, dict[str, str]]] = []
        for c in actives:
            if float(c.budget) - float(c.spent) + 1e-9 < float(c.cpm_price) / 1000.0:
                continue
            if c.start_date is not None and c.start_date > today:
                continue
            if c.end_date is not None and c.end_date < today:
                continue  # /bid lazy-flips these; auto-play just skips
            if not c.target_dmas:
                continue
            device = venues.pick_random_device(list(c.target_dmas))
            if device is None:
                continue
            eligible.append((c, device))
        if not eligible:
            return

        campaign, device = random.choice(eligible)
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
                "auto-play: campaign=%s amount=%s device=%s venue=%r dma=%s tx=%s",
                campaign.id,
                amount,
                device["device_id"],
                device["venue_name"],
                device["dma"],
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
