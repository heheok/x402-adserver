"""Single source of truth for USDC ↔ microUSDC conversion.

USDC is stored on-chain (SPL token decimals=6), in our DB, and on the wire as
integer microUSDC. 1 USDC = 1_000_000 microUSDC. Float USDC must NEVER appear
in money math — only at the UI display boundary on the client.

This module exists so there's exactly one place to convert. Internal arithmetic
on money should already be `int` micro and never need `to_micro` — the helper
is for trust boundaries (config parsing, legacy float ingestion in tests).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

MICRO = 1_000_000
DECIMALS = 6


def to_micro(usdc: int | float | str | Decimal) -> int:
    """Convert a USDC value (Decimal/str/float/int) to integer microUSDC.

    Rounds HALF_UP at 6 decimals via Decimal so we never accumulate float
    drift through the conversion. Used at trust boundaries — config parsing,
    legacy fixtures. Internal math should already be int micro and skip this.
    """
    return int(
        Decimal(str(usdc)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        * MICRO
    )


def micro_str(micro: int) -> str:
    """Render integer microUSDC as the on-wire string form ('422000').

    Use in every Pydantic response model that exposes a money field. The wire
    convention is 'this string is atomic units of USDC' — same shape as x402's
    `amount_usdc` and Solana SPL token amounts.
    """
    return str(int(micro))
