"""Campaign budget calculator — single source of truth for the wizard quote
and the actual escrow amount on POST /api/campaigns.

Inputs the advertiser controls: target DMAs, start date, end date.
Inputs the server controls: CPM, frequency constants, screen counts, fee %.

The wizard hits POST /api/campaigns/quote during Step 4 and renders whatever
this returns. The same function runs server-side on POST /api/campaigns to
derive the actual escrow amount charged via x402 — clients don't get to
negotiate the number.

Session 16.9: every money field is integer microUSDC. 1 USDC = 1e6 micro.
cpm_price is microUSDC per 1000 plays (e.g. $0.50 CPM → 500_000). Per-play
cost is derived: cpm_price // 1000.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..config import get_settings
from .money import to_micro
from .venues import get_venues_index


@dataclass(frozen=True)
class Quote:
    screens: int
    plays_per_screen_per_day: int
    days: int
    total_plays: int
    # All money fields are integer microUSDC.
    cpm_price_micro: int  # micro per 1000 plays
    total_micro: int
    protocol_fee_pct: float  # display-only ratio (e.g. 0.025 for 2.5%)
    protocol_fee_micro: int
    total_to_escrow_micro: int


class CalcError(ValueError):
    pass


# Right-sized SOL seed for new campaign wallets. We know `total_plays` at
# creation time from compute_quote(), so seed exactly enough SOL for every
# settlement the campaign can fund + a small reserve for the refund tx +
# protocol fee tx + buffer. Eliminates the SOL-drain bug that bit
# campaigns provisioned before this change (see PLAN.md Session 16.6).
#
# Per-tx fee on Solana devnet is 5_000 lamports per signature. We add a
# 1_000-lamport buffer per play to absorb compute-budget overhead and any
# minor fee bumps. Reserve covers refund tx + protocol fee tx + dust.
SOL_PER_PLAY_LAMPORTS = 6_000
SOL_BASE_RESERVE_LAMPORTS = 50_000


def required_sol_seed_lamports(total_plays: int) -> int:
    """Lamports the campaign wallet needs to fund every settlement + admin tx
    over its lifetime. Treasury sends this amount during campaign bootstrap."""
    return total_plays * SOL_PER_PLAY_LAMPORTS + SOL_BASE_RESERVE_LAMPORTS


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

    All math is integer microUSDC. Floor division (`//`) on derived values so
    we never charge more than the sum.
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

    # Convert config float CPM → integer micro at the trust boundary. After
    # this, no float touches money math.
    cpm_micro = to_micro(settings.demo_cpm)  # e.g. 500_000 for $0.50 CPM
    cost_per_play_micro = cpm_micro // 1000  # e.g. 500 micro/play
    total_micro = cost_per_play_micro * total_plays

    # Protocol fee in basis points avoids float * int. 0.025 → 250 bps.
    fee_bps = int(round(settings.protocol_fee_pct * 10_000))
    protocol_fee_micro = (total_micro * fee_bps) // 10_000
    total_to_escrow_micro = total_micro + protocol_fee_micro

    return Quote(
        screens=screens,
        plays_per_screen_per_day=plays_per_screen_per_day,
        days=days,
        total_plays=total_plays,
        cpm_price_micro=cpm_micro,
        total_micro=total_micro,
        protocol_fee_pct=float(settings.protocol_fee_pct),
        protocol_fee_micro=protocol_fee_micro,
        total_to_escrow_micro=total_to_escrow_micro,
    )
