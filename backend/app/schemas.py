from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .services.venues import DMA_LABELS


CANONICAL_DMA_LABELS: set[str] = set(DMA_LABELS.values())


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str


class WalletInfo(BaseModel):
    wallet_address: str
    usdc_balance: float


class FaucetResponse(BaseModel):
    amount: float
    tx_hash: str


class CreateCampaignRequest(BaseModel):
    """Session 15: body shrinks to creative + targeting + schedule. CPM,
    budget, duration are server-derived (DEMO_CPM, compute_quote, default
    spot length) — clients don't get to negotiate them.
    """

    name: str
    creative_url: str
    creative_id: str
    target_dmas: list[str] = Field(min_length=1)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _validate_targeting_and_schedule(self):
        unknown = [d for d in self.target_dmas if d not in CANONICAL_DMA_LABELS]
        if unknown:
            raise ValueError(
                f"unknown DMAs: {unknown!r} — expected one of {sorted(CANONICAL_DMA_LABELS)}"
            )
        if len(set(self.target_dmas)) != len(self.target_dmas):
            raise ValueError("target_dmas contains duplicates")
        today = datetime.now(timezone.utc).date()
        if self.start_date < today:
            raise ValueError(f"start_date {self.start_date} is in the past (today: {today})")
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        return self


class CampaignSummary(BaseModel):
    id: str
    name: str
    status: str
    budget: float
    spent: float
    remaining: float
    wallet_address: str
    target_dmas: list[str] | None = None
    start_date: date | None = None
    end_date: date | None = None
    protocol_fee_amount: float | None = None
    protocol_fee_tx_hash: str | None = None
    protocol_fee_solscan_url: str | None = None


class SettlementSummary(BaseModel):
    id: str
    nonce: str
    publisher_wallet: str
    amount_usdc: float
    tx_hash: str | None
    solscan_url: str | None
    status: str
    created_at: str
    # DMA the bid was issued for (resolved server-side from device_id via the
    # venues index). None for legacy rows that predate the device_id column,
    # or rows whose device is no longer in the inventory file. Venue name
    # stays internal (publisher-private — see Session 14 findings).
    dma: str | None = None


class CampaignStats(BaseModel):
    campaign_id: str
    status: str
    budget: float
    spent: float
    remaining_budget: float
    total_plays: int
    last_24h_plays: int = 0
    total_confirmed_usdc: float
    cpm_price: float
    target_dmas: list[str] | None = None
    start_date: date | None = None
    end_date: date | None = None
    protocol_fee_amount: float | None = None
    protocol_fee_tx_hash: str | None = None
    protocol_fee_solscan_url: str | None = None
    recent_settlements: list[SettlementSummary]


class RefundResponse(BaseModel):
    refund_amount: float
    tx_hash: str | None
    solscan_url: str | None


class DashboardActivityRow(BaseModel):
    """A settlement row joined with its campaign name, for the Overview feed."""

    id: str
    nonce: str
    campaign_id: str
    campaign_name: str
    publisher_wallet: str
    amount_usdc: float
    tx_hash: str | None
    solscan_url: str | None
    status: str
    created_at: str
    dma: str | None = None


class DashboardSummary(BaseModel):
    """Aggregate counts across the advertiser's campaigns. The campaigns list
    itself stays on /api/campaigns — this endpoint only returns what can't be
    derived from that list (server-counted plays + cross-campaign feed)."""

    total_plays: int
    last_24h_plays: int
    recent_activity: list[DashboardActivityRow]


class SimulatePlayResponse(BaseModel):
    amount_usdc: float
    tx_hash: str
    solscan_url: str
    publisher_wallet: str
    # DMA-only on purpose: venue name identifies a specific publisher partner
    # and isn't something we want to leak to advertisers via the API. Server-
    # side logs (auto-play) still include the venue for ops debugging.
    dma: str | None = None


class MarketInfo(BaseModel):
    dma: str
    display_count: int


class QuoteRequest(BaseModel):
    target_dmas: list[str] = Field(min_length=1)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _validate(self):
        unknown = [d for d in self.target_dmas if d not in CANONICAL_DMA_LABELS]
        if unknown:
            raise ValueError(
                f"unknown DMAs: {unknown!r} — expected one of {sorted(CANONICAL_DMA_LABELS)}"
            )
        if len(set(self.target_dmas)) != len(self.target_dmas):
            raise ValueError("target_dmas contains duplicates")
        today = datetime.now(timezone.utc).date()
        if self.start_date < today:
            raise ValueError(f"start_date {self.start_date} is in the past (today: {today})")
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        return self


class QuoteResponse(BaseModel):
    screens: int
    plays_per_screen_per_day: int
    days: int
    total_plays: int
    cpm_price: float
    total_usdc: float
    protocol_fee_pct: float
    protocol_fee_usdc: float
    total_to_escrow_usdc: float


class BidRequest(BaseModel):
    id: str
    imp: list[dict[str, Any]]
    device: dict[str, Any] | None = None
    site: dict[str, Any] | None = None
    at: int | None = None
    cur: list[str] | None = None


class BidResponse(BaseModel):
    id: str
    seatbid: list[dict[str, Any]]
    cur: str = "USD"


class ProofRequest(BaseModel):
    proof_context: str
    start_time: int
    duration: int


class ProofResponse(BaseModel):
    status: str
    tx_hash: str | None = None
