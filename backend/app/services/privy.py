"""Privy REST client — server wallets + user lookup + JWKS.

No official Python SDK exists; Privy's REST API uses Basic auth
(`app_id` : `app_secret`) plus the `privy-app-id` header.
"""
from __future__ import annotations

import base64
from typing import Any

import httpx

from ..config import Settings, get_settings

PRIVY_BASE_URL = "https://api.privy.io"
SOLANA_DEVNET_CAIP2 = "solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1"


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
        """Sign + broadcast a pre-built Solana transaction. Returns the tx signature (hash)."""
        body: dict[str, Any] = {
            "method": "signAndSendTransaction",
            "caip2": SOLANA_DEVNET_CAIP2,
            "params": {"transaction": transaction_base64, "encoding": "base64"},
        }
        if sponsor:
            body["sponsor"] = True
        if reference_id:
            body["reference_id"] = reference_id

        async with self._client() as c:
            r = await c.post(f"/v1/wallets/{wallet_id}/rpc", json=body)
            data = self._check(r)

        tx_hash = data.get("hash") or data.get("data", {}).get("hash")
        if not tx_hash:
            raise PrivyError(r.status_code, f"no tx hash in response: {data}")
        return tx_hash

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
