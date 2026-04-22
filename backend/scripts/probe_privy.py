"""One-off probe: confirms PRIVY_APP_ID / PRIVY_APP_SECRET can list + create server wallets.

Run inside the backend container:

    docker compose run --rm backend python scripts/probe_privy.py

Exit codes:
    0 = all good
    1 = auth failed
    2 = wallet creation failed (likely plan or permissions)
    3 = missing env vars
"""
from __future__ import annotations

import base64
import os
import sys

import httpx


PRIVY_BASE = "https://api.privy.io"


def _basic_auth(app_id: str, app_secret: str) -> str:
    token = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()
    return f"Basic {token}"


def main() -> int:
    app_id = os.getenv("PRIVY_APP_ID", "").strip()
    app_secret = os.getenv("PRIVY_APP_SECRET", "").strip()

    if not app_id or not app_secret:
        print("❌ PRIVY_APP_ID or PRIVY_APP_SECRET not set in env")
        return 3

    headers = {
        "Authorization": _basic_auth(app_id, app_secret),
        "privy-app-id": app_id,
        "Content-Type": "application/json",
    }

    with httpx.Client(base_url=PRIVY_BASE, headers=headers, timeout=10.0) as client:
        print("→ GET /v1/wallets (list existing)")
        r = client.get("/v1/wallets")
        if r.status_code == 401:
            print(f"❌ auth failed: {r.status_code} {r.text}")
            return 1
        if r.status_code >= 400:
            print(f"❌ list failed: {r.status_code} {r.text}")
            return 2
        existing = r.json()
        data = existing.get("data", existing) if isinstance(existing, dict) else existing
        print(f"   ✓ listed wallets — found {len(data) if isinstance(data, list) else 'n/a'}")

        print("→ POST /v1/wallets (create throwaway Solana wallet)")
        r = client.post(
            "/v1/wallets",
            json={"chain_type": "solana"},
            headers={"privy-idempotency-key": "probe-test-wallet-v1"},
        )
        if r.status_code >= 400:
            print(f"❌ create failed: {r.status_code} {r.text}")
            return 2
        wallet = r.json()
        print(f"   ✓ created wallet id={wallet.get('id')} address={wallet.get('address')}")
        print(f"   chain_type={wallet.get('chain_type')}")

    print()
    print("✅ Privy server wallets are fully accessible on this app.")
    print("   You can throw away the wallet above — it will just sit empty.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
