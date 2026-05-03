from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import AdvertiserIdentity, require_advertiser
from ..models import Campaign, Settlement, SettlementStatus
from ..schemas import DashboardActivityRow, DashboardSummary
from ..services.batches import (
    RECENT_BATCHES_LIMIT,
    RECENT_SETTLEMENTS_FETCH,
    group_settlements_into_batches,
)
from ..services.venues import get_venues_index

router = APIRouter(prefix="/api", tags=["dashboard"])


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
    # pending + flushing + confirmed + needs_review (the play happened the
    # moment /proof returned; settlement state is implementation detail).
    # FLUSHING covers the brief window while batch_settler is broadcasting,
    # NEEDS_REVIEW is a stuck row awaiting operator triage. Failed rows
    # (compensated, the play didn't happen) still excluded.
    counted = (
        SettlementStatus.PENDING.value,
        SettlementStatus.FLUSHING.value,
        SettlementStatus.CONFIRMED.value,
        SettlementStatus.NEEDS_REVIEW.value,
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
    # 'failed' rows differently) but ordered by recency. Overfetches enough
    # raw settlement rows to produce RECENT_BATCHES_LIMIT batches after the
    # tx_hash grouping in services.batches.
    recent_rows = (
        db.query(Settlement, Campaign.name)
        .join(Campaign, Settlement.campaign_id == Campaign.id)
        .filter(Campaign.advertiser_id == advertiser.user_id)
        .order_by(Settlement.created_at.desc())
        .limit(RECENT_SETTLEMENTS_FETCH)
        .all()
    )

    venues = get_venues_index()
    raw_settlements = [s for s, _ in recent_rows]
    name_by_campaign = {s.campaign_id: name for s, name in recent_rows}
    grouped = group_settlements_into_batches(
        raw_settlements, venues, include_campaign_id=True
    )
    activity: list[DashboardActivityRow] = []
    for g in grouped[:RECENT_BATCHES_LIMIT]:
        cid = g.get("campaign_id") or ""
        activity.append(
            DashboardActivityRow(
                **g,
                campaign_name=name_by_campaign.get(cid, ""),
                solscan_url=_solscan_tx_url(g["tx_hash"]),
            )
        )

    return DashboardSummary(
        total_plays=total_plays,
        last_24h_plays=last_24h_plays,
        recent_activity=activity,
    )
