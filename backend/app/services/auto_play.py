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
from ..services.tokens import ProofContextClaims
from ..services.venues import get_venues_index

logger = logging.getLogger(__name__)


# Snapshot of an eligible campaign captured under one DB session, safe to
# read from concurrent tasks (each opens its own session for the actual
# settlement write). cpm_price stays in micro per 1000 plays.
_EligibleSnapshot = tuple[str, int, tuple[str, ...]]
# fields: (campaign_id, cpm_price_micro, target_dmas)


async def _settle_one(
    campaign_id: str,
    cpm_price_micro: int,
    device: dict[str, str],
    demo_publisher: str,
) -> None:
    """Queue one settlement on its own DB session. Failures are logged at info
    level — typical between eligibility check and settle is a drained or
    freshly-paused campaign, which we don't want spamming exception logs.

    Session 16.8: this used to broadcast on-chain. Now it just writes a
    pending Settlement row; the batch_settler loop emits the actual tx.
    """
    # Local import to avoid a circular at module load time.
    from ..routers.proof import execute_settlement

    db = SessionLocal()
    try:
        amount_micro = cpm_price_micro // 1000
        claims = ProofContextClaims(
            campaign_id=campaign_id,
            bid_id=f"auto-{uuid4().hex[:8]}",
            wallet_id=demo_publisher,
            nonce=f"auto-{uuid4().hex}",
            created_at=int(time.time()),
            amount_micro=amount_micro,
            device_id=device["device_id"],
        )
        try:
            row = await execute_settlement(claims, db)
            logger.info(
                "auto-play queued: campaign=%s amount_micro=%d device=%s venue=%r dma=%s settlement=%s",
                campaign_id,
                amount_micro,
                device["device_id"],
                device["venue_name"],
                device["dma"],
                row.id[:8],
            )
        except HTTPException as e:
            logger.info(
                "auto-play skipped campaign=%s status=%d detail=%s",
                campaign_id,
                e.status_code,
                e.detail,
            )
    finally:
        db.close()


async def _tick() -> None:
    """Run one iteration: build the eligibility snapshot once, then fire a
    random number of settlements concurrently — uniformly sampled from
    [min, max]. Sampling is with replacement so multiple plays can land on
    the same campaign in a single tick."""
    settings = get_settings()
    venues = get_venues_index()
    today = datetime.now(timezone.utc).date()
    lo = max(1, int(settings.auto_play_plays_per_tick_min))
    hi = max(lo, int(settings.auto_play_plays_per_tick_max))
    plays_per_tick = random.randint(lo, hi)

    # Build the snapshot under a short-lived session so we don't hold a
    # connection through N parallel settlements.
    db = SessionLocal()
    try:
        actives = (
            db.query(Campaign)
            .filter(Campaign.status == CampaignStatus.ACTIVE.value)
            .all()
        )
        # Eligibility: funded for one play, schedule window contains today,
        # has at least one device in the selected DMAs. Mirrors /bid's
        # filters so we only simulate plays the campaign would accept.
        eligible: list[_EligibleSnapshot] = []
        for c in actives:
            cost_per_play_micro = int(c.cpm_price) // 1000
            if int(c.budget) - int(c.spent) < cost_per_play_micro:
                continue
            if c.start_date is not None and c.start_date > today:
                continue
            if c.end_date is not None and c.end_date < today:
                continue  # /bid lazy-flips these; auto-play just skips
            if not c.target_dmas:
                continue
            # Capture only primitives + the DMA list so we can use the
            # snapshot from concurrent tasks after this session closes.
            eligible.append((c.id, int(c.cpm_price), tuple(c.target_dmas)))
    finally:
        db.close()

    if not eligible:
        return

    # Pick N campaign-device pairs. Pick a fresh device per pick (not per
    # campaign) so multiple plays on the same campaign land on different
    # screens — closer to the per-screen frequency the calculator implies.
    tasks: list = []
    for _ in range(plays_per_tick):
        campaign_id, cpm, dmas = random.choice(eligible)
        device = venues.pick_random_device(list(dmas))
        if device is None:
            continue
        tasks.append(
            _settle_one(
                campaign_id,
                cpm,
                device,
                settings.demo_publisher_wallet,
            )
        )

    if not tasks:
        return

    # return_exceptions=True so a single failure doesn't drop sibling plays.
    # Each task already swallows HTTPException; this catches anything else.
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            logger.exception("auto-play task crashed: %r", r)


async def run_auto_play_loop(stop_event: asyncio.Event) -> None:
    """Long-running task: ticks forever (until `stop_event` is set)."""
    settings = get_settings()
    if not settings.auto_play_enabled:
        logger.info("auto-play disabled (AUTO_PLAY_ENABLED=false)")
        return

    interval = max(1, int(settings.auto_play_interval_seconds))
    logger.info("auto-play loop starting — interval=%ds", interval)

    while not stop_event.is_set():
        try:
            await _tick()
        except Exception:
            logger.exception("auto-play iteration crashed; continuing")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue  # expected — interval elapsed, go again

    logger.info("auto-play loop stopped")
