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
# x402.org facilitator registers the v1 Solana entry under the short name
# "solana-devnet" (CAIP-2 `solana:EtWTRAB…` is registered only under v2). The
# x402-solana client accepts either form interchangeably — see its
# isSolanaNetwork() — so we use the short name so /verify + /settle work.
DEVNET_NETWORK = "solana-devnet"


class X402Error(RuntimeError):
    pass


def build_payment_requirements(
    amount_micro: int,
    pay_to_address: str,
    resource_url: str,
    description: str,
    fee_payer: str | None = None,
) -> dict[str, Any]:
    """Build a PaymentRequirements object for inclusion in the 402 response body.

    `amount_micro` is integer microUSDC (1 USDC = 1e6 micro). Goes on the wire
    as `maxAmountRequired` in atomic-units string form, matching the x402 spec.
    """
    settings = get_settings()
    return {
        "scheme": "exact",
        "network": DEVNET_NETWORK,
        "maxAmountRequired": str(int(amount_micro)),
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


_facilitator_fee_payer_cache: str | None = None


async def get_facilitator_fee_payer() -> str:
    """Fetch (and cache) the facilitator's Solana fee-payer address.

    The x402-solana client builds its transfer tx with `payerKey = extra.feePayer`
    and expects the facilitator to co-sign as fee payer during /settle — so the
    value we put in PaymentRequirements.extra.feePayer must be the facilitator's
    own address. Putting anything else yields `fee_payer_not_managed_by_facilitator`.

    The /supported endpoint publishes one entry per (version, scheme, network);
    we pick v1/exact/solana-devnet and return its `extra.feePayer`.
    """
    global _facilitator_fee_payer_cache
    if _facilitator_fee_payer_cache:
        return _facilitator_fee_payer_cache

    settings = get_settings()
    url = f"{settings.x402_facilitator_url.rstrip('/')}/supported"
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as c:
        r = await c.get(url)
    if r.status_code >= 300:
        raise X402Error(f"facilitator /supported {r.status_code}: {r.text[:300]}")
    data = r.json()
    kinds = data.get("kinds") or []
    for k in kinds:
        if (
            k.get("x402Version") == X402_VERSION
            and k.get("scheme") == "exact"
            and k.get("network") == DEVNET_NETWORK
        ):
            fp = (k.get("extra") or {}).get("feePayer")
            if fp:
                _facilitator_fee_payer_cache = fp
                return fp
    raise X402Error(
        f"facilitator does not advertise a v{X402_VERSION} exact entry for "
        f"{DEVNET_NETWORK} with a feePayer"
    )


async def verify(payment_payload: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    url = f"{settings.x402_facilitator_url.rstrip('/')}/verify"
    body = {
        "x402Version": X402_VERSION,
        "paymentPayload": payment_payload,
        "paymentRequirements": requirements,
    }
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
        r = await c.post(url, json=body)
        if r.status_code >= 300:
            logger.warning("x402 verify -> %d: %s", r.status_code, r.text[:500])
            raise X402Error(f"verify {r.status_code}: {r.text[:500]}")
        return r.json()


async def settle(payment_payload: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    url = f"{settings.x402_facilitator_url.rstrip('/')}/settle"
    body = {
        "x402Version": X402_VERSION,
        "paymentPayload": payment_payload,
        "paymentRequirements": requirements,
    }
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as c:
        r = await c.post(url, json=body)
        if r.status_code >= 300:
            logger.warning("x402 settle -> %d: %s", r.status_code, r.text[:500])
            raise X402Error(f"settle {r.status_code}: {r.text[:500]}")
        return r.json()
