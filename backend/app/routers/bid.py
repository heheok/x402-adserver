from __future__ import annotations

import secrets
import time
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..dependencies import require_publisher_api_key
from ..models import Campaign, CampaignStatus
from ..schemas import BidRequest, BidResponse
from ..services.tokens import ProofContextClaims, encode_proof_context

router = APIRouter(tags=["rtb"])


def _cost_per_play(cpm_price: float) -> float:
    """CPM is the price per 1000 impressions."""
    return float(cpm_price) / 1000.0


def _pick_campaign(db: Session) -> Campaign | None:
    """FIFO: oldest active campaign whose remaining budget covers one play.

    No auction between campaigns — first-come, first-served. Enough for the
    hackathon; real auction logic is deferred.
    """
    candidates = (
        db.query(Campaign)
        .filter(Campaign.status == CampaignStatus.ACTIVE.value)
        .order_by(Campaign.created_at.asc())
        .all()
    )
    for c in candidates:
        remaining = float(c.budget) - float(c.spent)
        if remaining >= _cost_per_play(float(c.cpm_price)):
            return c
    return None


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
    publisher_wallet = (imp.get("ext") or {}).get("wallet_id")
    if not publisher_wallet:
        return BidResponse(id=body.id, seatbid=[], cur="USD")

    campaign = _pick_campaign(db)
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
