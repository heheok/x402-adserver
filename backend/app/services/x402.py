"""x402 facilitator client + payment-requirements helpers.

Protocol reference: https://github.com/coinbase/x402/blob/main/specs/x402-specification-v1.md
Solana scheme:      https://github.com/coinbase/x402/blob/main/specs/schemes/exact/scheme_exact_svm.md

For devnet, the network identifier is `solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1`
(matches Privy's caip2 format).
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

USDC_DECIMALS = 6
X402_VERSION = 1
DEVNET_NETWORK = "solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1"


class X402Error(RuntimeError):
    pass


def build_payment_requirements(
    amount_usdc: float,
    pay_to_address: str,
    resource_url: str,
    description: str,
    fee_payer: str | None = None,
) -> dict[str, Any]:
    """Build a PaymentRequirements object for inclusion in the 402 response body."""
    settings = get_settings()
    amount_raw = int(round(amount_usdc * (10 ** USDC_DECIMALS)))
    return {
        "scheme": "exact",
        "network": DEVNET_NETWORK,
        "maxAmountRequired": str(amount_raw),
        "asset": settings.usdc_mint_devnet,
        "payTo": pay_to_address,
        "resource": resource_url,
        "description": description,
        "mimeType": "application/json",
        "maxTimeoutSeconds": 60,
        "extra": {"feePayer": fee_payer or pay_to_address},
    }


def build_402_body(requirements_list: list[dict[str, Any]]) -> dict[str, Any]:
    """The body we return alongside HTTP 402."""
    return {"x402Version": X402_VERSION, "accepts": requirements_list}


def decode_payment_header(x_payment: str) -> dict[str, Any]:
    """X-PAYMENT is base64(PaymentPayload JSON)."""
    try:
        raw = base64.b64decode(x_payment)
        return json.loads(raw.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise X402Error(f"invalid X-PAYMENT header: {e}") from e


async def verify(payment_payload: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    url = f"{settings.x402_facilitator_url.rstrip('/')}/verify"
    body = {
        "x402Version": X402_VERSION,
        "paymentPayload": payment_payload,
        "paymentRequirements": requirements,
    }
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(url, json=body)
        if r.status_code >= 400:
            logger.warning("x402 verify -> %d: %s", r.status_code, r.text[:500])
            raise X402Error(f"verify {r.status_code}: {r.text}")
        return r.json()


async def settle(payment_payload: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    url = f"{settings.x402_facilitator_url.rstrip('/')}/settle"
    body = {
        "x402Version": X402_VERSION,
        "paymentPayload": payment_payload,
        "paymentRequirements": requirements,
    }
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(url, json=body)
        if r.status_code >= 400:
            logger.warning("x402 settle -> %d: %s", r.status_code, r.text[:500])
            raise X402Error(f"settle {r.status_code}: {r.text}")
        return r.json()
