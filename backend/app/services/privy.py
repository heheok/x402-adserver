"""Privy REST client — server wallets + user lookup + JWKS.

No official Python SDK exists; Privy's REST API uses Basic auth
(`app_id` : `app_secret`) plus the `privy-app-id` header.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import httpx

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)

PRIVY_BASE_URL = "https://api.privy.io"
SOLANA_DEVNET_CAIP2 = "solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1"

# Privy's simulation RPC can trail devnet for tens of seconds after a funding
# transfer, returning `transaction_broadcast_failure` with a simulation error
# even though the on-chain state is fine. We retry that specific code with
# backoff. Other errors (bad tx, auth, etc.) fail immediately.
#
# RETRY SAFETY — read before widening this list. `reference_id` is NOT a
# strict pre-broadcast idempotency key: passing the same reference_id twice
# does not prevent Privy from broadcasting a second on-chain tx (observed
# 2026-04-22, see BUSINESS-CONSTRAINTS.md §3 + §7). We retry *only* on
# `transaction_broadcast_failure` because Privy returns that code when the
# broadcast explicitly did not happen (simulation failed before send), so
# the retry is the first on-chain attempt — not a duplicate. Do not add
# retry codes that cover the "we don't know if it went through" case
# (timeouts, connection resets, HTTP 502 from Privy's gateway) without
# first adding a pre-flight check against Solana for the tx.
_BROADCAST_RETRY_CODE = "transaction_broadcast_failure"
_BROADCAST_RETRY_DELAYS = (2, 4, 8, 16)  # total ~30s worst case


class PrivyError(RuntimeError):
    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"privy error {status_code}: {body}")
        self.status_code = status_code
        self.body = body


class PrivyClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        if not self._settings.privy_app_id or not self._settings.privy_app_secret:
            raise RuntimeError("PRIVY_APP_ID and PRIVY_APP_SECRET must be set")
        token = base64.b64encode(
            f"{self._settings.privy_app_id}:{self._settings.privy_app_secret}".encode()
        ).decode()
        self._headers = {
            "Authorization": f"Basic {token}",
            "privy-app-id": self._settings.privy_app_id,
            "Content-Type": "application/json",
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=PRIVY_BASE_URL, headers=self._headers, timeout=20.0)

    @staticmethod
    def _check(r: httpx.Response) -> dict[str, Any]:
        if r.status_code >= 400:
            logger.warning(
                "privy %s %s -> %d: %s",
                r.request.method,
                r.request.url.path,
                r.status_code,
                r.text[:500],
            )
            raise PrivyError(r.status_code, r.text)
        return r.json()

    async def create_solana_wallet(self, idempotency_key: str | None = None) -> dict[str, Any]:
        """Create a fresh Solana server wallet. Returns full wallet object (id, address, ...)."""
        headers = {"privy-idempotency-key": idempotency_key} if idempotency_key else {}
        async with self._client() as c:
            r = await c.post("/v1/wallets", json={"chain_type": "solana"}, headers=headers)
            return self._check(r)

    async def get_wallet(self, wallet_id: str) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.get(f"/v1/wallets/{wallet_id}")
            return self._check(r)

    async def list_wallets(self, cursor: str | None = None) -> dict[str, Any]:
        params = {"cursor": cursor} if cursor else {}
        async with self._client() as c:
            r = await c.get("/v1/wallets", params=params)
            return self._check(r)

    async def sign_and_send_solana(
        self,
        wallet_id: str,
        transaction_base64: str,
        reference_id: str | None = None,
        sponsor: bool = False,
    ) -> str:
        """Sign + broadcast a pre-built Solana transaction. Returns the tx signature (hash).

        Retries `transaction_broadcast_failure` responses with exponential
        backoff — Privy's simulation read-replica sometimes lags the
        funding transfer by >30s on fresh wallets. `reference_id`
        gives us Privy-side idempotency so retries are safe.
        """
        body: dict[str, Any] = {
            "method": "signAndSendTransaction",
            "caip2": SOLANA_DEVNET_CAIP2,
            "params": {"transaction": transaction_base64, "encoding": "base64"},
        }
        if sponsor:
            body["sponsor"] = True
        if reference_id:
            body["reference_id"] = reference_id

        attempts = [0, *_BROADCAST_RETRY_DELAYS]
        last_error: PrivyError | None = None
        for attempt, delay in enumerate(attempts):
            if delay:
                logger.info(
                    "privy sign_and_send retry %d/%d after %ds (wallet=%s ref=%s)",
                    attempt,
                    len(attempts) - 1,
                    delay,
                    wallet_id,
                    reference_id,
                )
                await asyncio.sleep(delay)

            async with self._client() as c:
                r = await c.post(f"/v1/wallets/{wallet_id}/rpc", json=body)
                if r.status_code >= 400:
                    logger.warning(
                        "privy POST %s -> %d: %s",
                        r.request.url.path,
                        r.status_code,
                        r.text[:500],
                    )
                    err = PrivyError(r.status_code, r.text)
                    # Only retry the specific simulation-lag code; everything
                    # else (auth, malformed tx, rate limit) bails immediately.
                    if _BROADCAST_RETRY_CODE in (r.text or ""):
                        last_error = err
                        continue
                    raise err
                data = r.json()

            tx_hash = data.get("hash") or data.get("data", {}).get("hash")
            if not tx_hash:
                raise PrivyError(r.status_code, f"no tx hash in response: {data}")
            return tx_hash

        assert last_error is not None
        raise last_error

    async def get_user(self, user_id: str) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.get(f"/v1/users/{user_id}")
            return self._check(r)

    async def get_user_solana_wallet(self, user_id: str) -> str | None:
        """Extract the user's Solana embedded-wallet address from their linked accounts."""
        user = await self.get_user(user_id)
        for account in user.get("linked_accounts", []):
            if account.get("type") == "wallet" and account.get("chain_type") == "solana":
                return account.get("address")
        return None

    async def fetch_jwks(self) -> dict[str, Any]:
        url = self._settings.privy_jwks_url.replace("{app_id}", self._settings.privy_app_id)
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url)
            return self._check(r)


_client: PrivyClient | None = None


def get_privy_client() -> PrivyClient:
    global _client
    if _client is None:
        _client = PrivyClient()
    return _client
