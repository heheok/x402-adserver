from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import AdvertiserIdentity, require_advertiser
from ..models import Campaign, Settlement, SettlementStatus
from ..schemas import DashboardActivityRow, DashboardSummary
from ..services.money import micro_str
from ..services.venues import get_venues_index

router = APIRouter(prefix="/api", tags=["dashboard"])

RECENT_ACTIVITY_LIMIT = 10


def _solscan_tx_url(tx_hash: str | None) -> str | None:
    if not tx_hash:
        return None
    return f"https://solscan.io/tx/{tx_hash}?cluster=devnet"


@router.get("/dashboard-summary", response_model=DashboardSummary)
def dashboard_summary(
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    db: Session = Depends(get_db),
) -> DashboardSummary:
    """Cross-campaign aggregates for the Overview tab. One query per page tick
    instead of N stats calls — see PLAN Session 16 findings."""

    # SQLite stores DateTime(timezone=True) as naive UTC; the cutoff has to be
    # naive too or the comparison silently misses rows.
    cutoff_24h = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        hours=24
    )

    # Plays across all of this advertiser's campaigns. Session 16.8: count
    # pending + confirmed (the play happened the moment /proof returned;
    # settlement state is implementation detail). Failed rows still excluded.
    counted = (
        SettlementStatus.PENDING.value,
        SettlementStatus.CONFIRMED.value,
    )
    base_q = (
        db.query(Settlement)
        .join(Campaign, Settlement.campaign_id == Campaign.id)
        .filter(
            Campaign.advertiser_id == advertiser.user_id,
            Settlement.status.in_(counted),
        )
    )
    total_plays = base_q.count()
    last_24h_plays = base_q.filter(Settlement.created_at >= cutoff_24h).count()

    # Cross-campaign recent activity feed. Pulls all statuses (the UI styles
    # 'failed' rows differently) but ordered by recency, capped at 10.
    recent_rows = (
        db.query(Settlement, Campaign.name)
        .join(Campaign, Settlement.campaign_id == Campaign.id)
        .filter(Campaign.advertiser_id == advertiser.user_id)
        .order_by(Settlement.created_at.desc())
        .limit(RECENT_ACTIVITY_LIMIT)
        .all()
    )

    venues = get_venues_index()
    activity: list[DashboardActivityRow] = []
    for s, campaign_name in recent_rows:
        # Same UTC stamping as in routers.campaigns._to_settlement_summary —
        # SQLite drops tzinfo on read, naive ISO on the wire is interpreted as
        # local by the browser. Stamp UTC before isoformat.
        created = s.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        dma = venues.label_for_device(s.device_id) if s.device_id else None
        activity.append(
            DashboardActivityRow(
                id=s.id,
                nonce=s.nonce,
                campaign_id=s.campaign_id,
                campaign_name=campaign_name,
                publisher_wallet=s.publisher_wallet,
                amount_usdc=micro_str(int(s.amount_usdc)),
                tx_hash=s.tx_hash,
                solscan_url=_solscan_tx_url(s.tx_hash),
                status=s.status,
                created_at=created.isoformat() if created else "",
                dma=dma,
            )
        )

    return DashboardSummary(
        total_plays=total_plays,
        last_24h_plays=last_24h_plays,
        recent_activity=activity,
    )
