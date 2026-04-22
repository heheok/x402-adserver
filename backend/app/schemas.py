from typing import Any

from pydantic import BaseModel, Field


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
    name: str
    creative_url: str
    creative_id: str
    cpm_price: float = Field(gt=0)
    budget: float = Field(gt=0)
    duration: int = Field(ge=1, le=30, default=15)


class CampaignSummary(BaseModel):
    id: str
    name: str
    status: str
    budget: float
    spent: float
    remaining: float
    wallet_address: str


class SettlementSummary(BaseModel):
    id: str
    nonce: str
    publisher_wallet: str
    amount_usdc: float
    tx_hash: str | None
    solscan_url: str | None
    status: str
    created_at: str


class CampaignStats(BaseModel):
    campaign_id: str
    status: str
    budget: float
    spent: float
    remaining_budget: float
    total_plays: int
    total_confirmed_usdc: float
    cpm_price: float
    recent_settlements: list[SettlementSummary]


class RefundResponse(BaseModel):
    refund_amount: float
    tx_hash: str | None
    solscan_url: str | None


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
