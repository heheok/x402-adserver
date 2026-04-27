from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..dependencies import require_publisher_api_key
from ..models import Campaign, CampaignStatus
from ..schemas import BidRequest, BidResponse
from ..services.tokens import ProofContextClaims, encode_proof_context
from ..services.venues import get_venues_index

router = APIRouter(tags=["rtb"])


def _cost_per_play(cpm_price: float) -> float:
    """CPM is the price per 1000 impressions."""
    return float(cpm_price) / 1000.0


def _pick_campaign(db: Session, dma_label: str) -> Campaign | None:
    """FIFO: oldest active campaign matching DMA + schedule + budget.

    Filters in order: DMA membership in target_dmas, schedule window
    [start_date, end_date] containing today, remaining budget covers one play.
    No auction between campaigns — first-come, first-served. Enough for the
    hackathon; real auction logic is deferred.

    Side effect: any active campaign whose end_date is already in the past is
    flipped to EXPIRED while we iterate. This is the lazy garbage collector
    for stale schedules — periodic sweeps are an option but a per-bid pass
    keeps the list tight without a separate cron.

    The `+ 1e-9` tolerance forgives float-addition drift — summing 0.001 many
    times accumulates ~1e-16 of error per step, which can leave `remaining`
    at 0.000999999… when the semantically-correct answer is "exactly one more
    play is affordable." Without the tolerance the final play is rejected.
    Production should track money as integer microUSDC, not float.
    """
    today = datetime.now(timezone.utc).date()
    candidates = (
        db.query(Campaign)
        .filter(Campaign.status == CampaignStatus.ACTIVE.value)
        .order_by(Campaign.created_at.asc())
        .all()
    )
    pick: Campaign | None = None
    flipped_any = False
    for c in candidates:
        if c.end_date is not None and c.end_date < today:
            c.status = CampaignStatus.EXPIRED.value
            flipped_any = True
            continue
        if pick is not None:
            # Found a match already; keep going only to flip stale rows.
            continue
        if c.start_date is not None and c.start_date > today:
            continue
        if not c.target_dmas or dma_label not in c.target_dmas:
            continue
        remaining = float(c.budget) - float(c.spent)
        if remaining + 1e-9 >= _cost_per_play(float(c.cpm_price)):
            pick = c
    if flipped_any:
        db.commit()
    return pick


def _build_proof_context(
    campaign: Campaign,
    bid_id: str,
    publisher_wallet: str,
    settings: Settings,
) -> str:
    claims = ProofContextClaims(
        campaign_id=campaign.id,
        bid_id=bid_id,
        wallet_id=publisher_wallet,
        nonce=secrets.token_urlsafe(16),
        created_at=int(time.time()),
        amount_usdc=_cost_per_play(float(campaign.cpm_price)),
    )
    return encode_proof_context(
        claims, secret=settings.jwt_server_secret, algorithm=settings.jwt_algorithm
    )


@router.post(
    "/bid",
    response_model=BidResponse,
    dependencies=[Depends(require_publisher_api_key)],
)
def bid(
    body: BidRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BidResponse:
    # OpenRTB-lite: we act on the first impression slot. Publisher contract sends one.
    if not body.imp:
        return BidResponse(id=body.id, seatbid=[], cur="USD")

    imp = body.imp[0]
    imp_id = str(imp.get("id", "1"))
    ext = imp.get("ext") or {}
    publisher_wallet = ext.get("wallet_id")
    device_id = ext.get("device_id")
    if not publisher_wallet or not device_id:
        return BidResponse(id=body.id, seatbid=[], cur="USD")

    # Resolve device_id → DMA via the publisher inventory index. Unknown
    # device → no-bid (we don't trust the publisher to assert DMA itself,
    # which is why the index is server-side).
    dma_label = get_venues_index().label_for_device(device_id)
    if dma_label is None:
        return BidResponse(id=body.id, seatbid=[], cur="USD")

    campaign = _pick_campaign(db, dma_label)
    if campaign is None:
        return BidResponse(id=body.id, seatbid=[], cur="USD")

    bid_id = f"bid-{uuid4().hex[:12]}"
    proof_context = _build_proof_context(campaign, bid_id, publisher_wallet, settings)

    video = imp.get("video") or {}
    width = int(video.get("w", 1920))
    height = int(video.get("h", 1080))

    return BidResponse(
        id=body.id,
        cur="USD",
        seatbid=[
            {
                "bid": [
                    {
                        "id": bid_id,
                        "impid": imp_id,
                        "price": float(campaign.cpm_price),
                        "adm": campaign.creative_url,
                        "crid": campaign.creative_id,
                        "w": width,
                        "h": height,
                        "ext": {
                            "duration": int(campaign.duration),
                            "mime_type": "video/mp4",
                            "proof_context": proof_context,
                        },
                    }
                ],
                "seat": f"advertiser-{campaign.advertiser_id[:12]}",
            }
        ],
    )
