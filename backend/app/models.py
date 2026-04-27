from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    REFUNDED = "refunded"
    # End_date passed before budget drained. /bid flips active→expired lazily;
    # refund button still applies (campaign wallet may hold remaining funds).
    EXPIRED = "expired"


class SettlementStatus(str, Enum):
    CONFIRMED = "confirmed"
    FAILED = "failed"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    advertiser_id: Mapped[str] = mapped_column(String, index=True)
    advertiser_wallet: Mapped[str] = mapped_column(String)

    name: Mapped[str] = mapped_column(String)
    creative_url: Mapped[str] = mapped_column(String)
    creative_id: Mapped[str] = mapped_column(String)
    cpm_price: Mapped[float] = mapped_column(Numeric(18, 6))
    budget: Mapped[float] = mapped_column(Numeric(18, 6))
    spent: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    status: Mapped[str] = mapped_column(String, default=CampaignStatus.DRAFT.value, index=True)

    wallet_id: Mapped[str] = mapped_column(String)
    wallet_address: Mapped[str] = mapped_column(String)

    duration: Mapped[int] = mapped_column(Integer, default=15)
    refund_tx_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    # Targeting (Session 14). target_dmas is a JSON list of canonical DMA labels
    # ("New York", "San Francisco", …). Mandatory ≥1 at create time but the
    # column is nullable so the dev SQLite ALTER doesn't reject existing rows.
    target_dmas: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Protocol fee (Session 15). 2.5% of budget, charged upfront alongside the
    # x402 funding tx; transferred from the campaign wallet to a dedicated
    # PROTOCOL_REVENUE_WALLET right after settle confirms. Non-refundable —
    # refund only returns budget - spent.
    protocol_fee_amount: Mapped[float | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    protocol_fee_tx_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    settlements: Mapped[list["Settlement"]] = relationship(back_populates="campaign")


class Settlement(Base):
    __tablename__ = "settlements"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    nonce: Mapped[str] = mapped_column(String, unique=True, index=True)
    publisher_wallet: Mapped[str] = mapped_column(String)
    amount_usdc: Mapped[float] = mapped_column(Numeric(18, 6))
    tx_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default=SettlementStatus.CONFIRMED.value)
    # device_id captures which screen the bid was issued for (from
    # imp.ext.device_id at /bid time, threaded through the proof_context JWT).
    # Nullable for backwards compatibility — pre-existing rows + JWTs minted
    # before this field landed have no device_id.
    device_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    campaign: Mapped[Campaign] = relationship(back_populates="settlements")


class UsedNonce(Base):
    __tablename__ = "used_nonces"

    nonce: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
