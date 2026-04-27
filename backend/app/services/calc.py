"""Campaign budget calculator — single source of truth for the wizard quote
and the actual escrow amount on POST /api/campaigns.

Inputs the advertiser controls: target DMAs, start date, end date.
Inputs the server controls: CPM, frequency constants, screen counts, fee %.

The wizard hits POST /api/campaigns/quote during Step 4 and renders whatever
this returns. The same function runs server-side on POST /api/campaigns to
derive the actual `total_to_escrow_usdc` charged via x402 — clients don't get
to negotiate the number.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..config import get_settings
from .venues import get_venues_index


@dataclass(frozen=True)
class Quote:
    screens: int
    plays_per_screen_per_day: int
    days: int
    total_plays: int
    cpm_price: float
    total_usdc: float
    protocol_fee_pct: float
    protocol_fee_usdc: float
    total_to_escrow_usdc: float


class CalcError(ValueError):
    pass


def compute_quote(
    target_dmas: list[str],
    start_date: date,
    end_date: date,
) -> Quote:
    """Derive the campaign's escrow breakdown.

    Raises CalcError on inputs the calculator can't handle (no DMAs supplied,
    DMAs that resolve to zero screens, end before start). Validation of DMA
    label membership happens upstream in the Pydantic schema — by the time we
    reach this function the labels are already in the canonical set.
    """
    if not target_dmas:
        raise CalcError("target_dmas must contain at least one DMA")
    if end_date < start_date:
        raise CalcError("end_date must be >= start_date")

    settings = get_settings()
    index = get_venues_index()

    screens = sum(index.display_count_by_label(d) for d in target_dmas)
    if screens <= 0:
        raise CalcError(
            "selected DMAs have no screens in the venues index; refresh venues.json"
        )

    plays_per_screen_per_day = (
        settings.operating_hours_per_day * settings.plays_per_hour_per_screen
    )
    days = (end_date - start_date).days + 1  # inclusive

    total_plays = screens * plays_per_screen_per_day * days
    cpm = float(settings.demo_cpm)
    total = total_plays * cpm / 1000.0
    fee_pct = float(settings.protocol_fee_pct)
    fee = total * fee_pct
    escrow = total + fee

    # Round to 6 decimals (USDC native precision). Floats are still floats; the
    # mainnet rewrite in BUSINESS-CONSTRAINTS §7 / PLAN.md "must-fix" #3 moves
    # all money to integer microUSDC.
    return Quote(
        screens=screens,
        plays_per_screen_per_day=plays_per_screen_per_day,
        days=days,
        total_plays=total_plays,
        cpm_price=cpm,
        total_usdc=round(total, 6),
        protocol_fee_pct=fee_pct,
        protocol_fee_usdc=round(fee, 6),
        total_to_escrow_usdc=round(escrow, 6),
    )
