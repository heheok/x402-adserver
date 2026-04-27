"""End-to-end integration test — real devnet, full happy-path + edge cases.

Runs inside the backend container so it shares the SQLite DB and .env with the
live server. HTTP calls go through an in-process ASGI transport against the
same FastAPI app the container serves, which sidesteps Docker's service-name
DNS load balancing (a `compose run` container shadows the live one for the
`backend` service name).

    docker compose stop backend
    docker compose run --rm backend python scripts/e2e_demo.py
    docker compose start backend

The `stop` is important: when AUTO_PLAY_ENABLED=true in .env (the demo
default), the long-running backend container has its own auto-play loop
that writes to the same SQLite DB via the bind mount. While the e2e runs,
the long-running container's auto-play can pick up the test campaign and
add a phantom play, breaking the spent-equals-one-play assertion. Stopping
the long-running container makes the run deterministic; the e2e's own
lifespan force-disables auto-play via os.environ further down.

What it does:

  0. Pre-flight: checks treasury config and backend health.
  1. Seeds a fresh campaign end-to-end:
      - creates a new Privy server wallet (stands in for the /api/campaigns
        x402 handshake, which needs a browser Privy JWT we don't have yet),
      - airdrops a little SOL for tx fees,
      - sends USDC from the treasury to the campaign wallet,
      - writes a `campaigns` row with status=active.
  2. Happy path: calls POST /bid, then POST /proof with the returned
     proof_context. Asserts the on-chain tx hash came back and that the
     settlement/campaign rows moved the way we expect.
  3. Edge cases (independent, non-fatal — each reports pass/fail):
      a. replay: re-send the same proof_context, expect 409 nonce-already-used.
      b. expired: mint a proof_context with a backdated `created_at`, expect 400.
      c. paused: flip the campaign to `paused` in DB, bid → expect empty seatbid.
      d. budget exhausted: seed a tiny-budget campaign, play until spent,
         next bid → expect empty seatbid.
      e. double refund: run the campaign-wallet drain-to-advertiser path twice,
         expect second attempt to be a no-op (already refunded).

At the end it prints a table of step results and exits 0 iff every step passed.

Every call is idempotent at the Privy layer via `reference_id`, but fresh
campaign IDs per run make the script safe to re-run without DB cleanup.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx

# Force-disable the demo auto-play loop for this run. Without this the lifespan
# task picks up our test campaign during /bid + /proof's retry windows and
# adds a phantom play, making spent=2*cost_per_play instead of 1*. Pydantic-
# settings reads process env over .env, so this lands before get_settings().
os.environ["AUTO_PLAY_ENABLED"] = "false"

sys.path.insert(0, "/app")

from solana.rpc.async_api import AsyncClient  # noqa: E402
from solders.signature import Signature  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models import Campaign, CampaignStatus, Settlement, SettlementStatus  # noqa: E402
from app.services.privy import PrivyClient, PrivyError  # noqa: E402
from app.services.solana import build_sol_transfer_tx, build_usdc_transfer_tx, get_usdc_balance  # noqa: E402
from app.services.tokens import ProofContextClaims, encode_proof_context  # noqa: E402
from app.services.venues import DMA_LABELS, get_venues_index  # noqa: E402

# Target DMA + a representative device id for /bid. The venues index is the
# single source of truth — we pick the first device in the chosen DMA so the
# script doesn't hard-code one that might be removed from a future export.
E2E_TARGET_DMA_LABEL = DMA_LABELS["sf"]
_index = get_venues_index()
_sf_devices = _index.dma_to_devices.get("sf", [])
if not _sf_devices:
    raise RuntimeError(
        "venues.json missing SF devices — refresh backend/data/venues.json"
    )
E2E_DEVICE_ID = _sf_devices[0]

# ASGI in-process transport — base URL is cosmetic; httpx rewrites it onto the app
BACKEND_URL = "http://testserver"
PUBLISHER_WALLET = os.getenv(
    "E2E_PUBLISHER_WALLET",
    "3pMCrwRq5tNy1GdonrPivP389eYjeeoGTiMZDtQmV8W9",  # from Session 5 smoke
)
CAMPAIGN_BUDGET_USDC = 0.02   # cpm 1.0 -> 0.001/play -> 20 plays
TINY_BUDGET_USDC = 0.002      # cpm 1.0 -> 0.001/play -> 2 plays exactly
CPM_USDC = 1.0
CONFIRM_TIMEOUT_SECONDS = 60  # devnet usually confirms inside 5s, but we've seen >15s outliers
PRIVY_RPC_LAG_GRACE_SECONDS = 5  # small cushion between Privy-signed txs; most lag we saw earlier
#                                  turned out to be a missing SOL balance, not RPC staleness
QUARANTINE_PREFIX = "e2e_quarantine_"


# ---------------------------------------------------------------------------
# Result collection
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    name: str
    passed: bool
    note: str = ""


@dataclass
class Report:
    steps: list[StepResult] = field(default_factory=list)

    def record(self, name: str, passed: bool, note: str = "") -> None:
        status = "✓" if passed else "✗"
        print(f"  {status} {name}: {note or ('pass' if passed else 'FAIL')}")
        self.steps.append(StepResult(name, passed, note))

    @property
    def all_passed(self) -> bool:
        return all(s.passed for s in self.steps)


report = Report()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _header(title: str) -> None:
    print()
    print(f"── {title} " + "─" * max(0, 60 - len(title)))


def _publisher_headers() -> dict[str, str]:
    return {"X-API-Key": get_settings().publisher_api_key}


async def _confirm_tx(signature: str, timeout: int = CONFIRM_TIMEOUT_SECONDS) -> bool:
    """Poll getSignatureStatuses until the tx hits `confirmed` or `finalized`.

    Privy's signAndSendTransaction returns after broadcast, not after finality.
    Downstream transfers that spend the same funds fail with
    "no record of prior credit" if we don't wait.
    """
    settings = get_settings()
    sig = Signature.from_string(signature)
    deadline = time.time() + timeout
    async with AsyncClient(settings.solana_rpc_url) as c:
        while time.time() < deadline:
            # searchTransactionHistory=True — finalized txs fall out of the
            # default recent-slot window quickly on devnet, and without it
            # get_signature_statuses returns [None] even for confirmed txs.
            resp = await c.get_signature_statuses([sig], search_transaction_history=True)
            value = getattr(resp, "value", None) or []
            status = value[0] if value else None
            if status is not None and status.confirmation_status is not None:
                name = str(status.confirmation_status).lower()
                if "confirmed" in name or "finalized" in name:
                    if status.err is not None:
                        raise RuntimeError(f"tx {signature} failed on-chain: {status.err}")
                    return True
            await asyncio.sleep(1)
    return False


async def _send_sol(
    privy: PrivyClient,
    from_wallet_id: str,
    from_address: str,
    to_address: str,
    lamports: int,
) -> str:
    """Send native SOL via Privy-signed tx, waiting for confirmation + RPC grace."""
    tx_b64 = await build_sol_transfer_tx(
        from_address=from_address,
        to_address=to_address,
        lamports=lamports,
    )
    tx_hash = await privy.sign_and_send_solana(
        wallet_id=from_wallet_id,
        transaction_base64=tx_b64,
        reference_id=f"e2e-sol-{uuid4().hex[:8]}",
    )
    if not await _confirm_tx(tx_hash):
        raise RuntimeError(f"SOL transfer {tx_hash} did not confirm")
    return tx_hash


async def _fund_campaign_wallet(
    privy: PrivyClient,
    treasury_wallet_id: str,
    treasury_address: str,
    campaign_wallet_address: str,
    amount_usdc: float,
) -> str:
    """Treasury -> campaign wallet USDC transfer. Returns tx hash; raises if not confirmed."""
    tx_b64 = await build_usdc_transfer_tx(
        from_address=treasury_address,
        to_address=campaign_wallet_address,
        amount_usdc=amount_usdc,
    )
    tx_hash = await privy.sign_and_send_solana(
        wallet_id=treasury_wallet_id,
        transaction_base64=tx_b64,
        reference_id=f"e2e-fund-{uuid4().hex[:8]}",
    )
    if not await _confirm_tx(tx_hash):
        raise RuntimeError(f"funding tx {tx_hash} did not confirm within {CONFIRM_TIMEOUT_SECONDS}s")
    await asyncio.sleep(PRIVY_RPC_LAG_GRACE_SECONDS)
    return tx_hash


async def _seed_campaign(
    privy: PrivyClient,
    treasury_wallet_id: str,
    treasury_address: str,
    advertiser_id: str,
    advertiser_wallet: str,
    budget: float,
    cpm: float,
    name: str,
) -> Campaign:
    """Stand-in for the x402 handshake: creates a wallet, funds it, writes the row."""
    wallet = await privy.create_solana_wallet(
        idempotency_key=f"e2e-{uuid4().hex[:8]}"
    )
    # RPC airdrops are rate-limited on devnet; when they fail, the campaign
    # wallet ends up with 0 SOL and Privy rejects every tx it tries to pay
    # fees for. We SOL-fund from treasury via a tiny lamport transfer.
    sol_tx = await _send_sol(
        privy,
        from_wallet_id=treasury_wallet_id,
        from_address=treasury_address,
        to_address=wallet["address"],
        lamports=10_000_000,  # 0.01 SOL — enough for ~100 txs at 5000 lamports each
    )
    print(f"    seeded wallet with 0.01 SOL (tx {sol_tx[:16]}…)")

    fund_tx = await _fund_campaign_wallet(
        privy=privy,
        treasury_wallet_id=treasury_wallet_id,
        treasury_address=treasury_address,
        campaign_wallet_address=wallet["address"],
        amount_usdc=budget,
    )
    print(f"    funded + confirmed campaign wallet: {wallet['address']} (tx {fund_tx[:16]}…)")

    from datetime import date, timedelta

    today = date.today()
    campaign = Campaign(
        id=f"e2e-{uuid4().hex[:12]}",
        advertiser_id=advertiser_id,
        advertiser_wallet=advertiser_wallet,
        name=name,
        creative_url="https://example.com/creative.mp4",
        creative_id=f"creative-{uuid4().hex[:8]}",
        cpm_price=cpm,
        budget=budget,
        spent=0.0,
        status=CampaignStatus.ACTIVE.value,
        wallet_id=wallet["id"],
        wallet_address=wallet["address"],
        duration=15,
        target_dmas=[E2E_TARGET_DMA_LABEL],
        start_date=today,
        end_date=today + timedelta(days=30),
    )
    db = SessionLocal()
    try:
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
    finally:
        db.close()
    return campaign


def _quarantine_active_except(keep_id: str | None) -> int:
    """Stash every other ACTIVE campaign's status so FIFO only sees ours. Returns count."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Campaign)
            .filter(Campaign.status == CampaignStatus.ACTIVE.value)
            .all()
        )
        rows = [r for r in rows if r.id != keep_id]
        for r in rows:
            r.status = QUARANTINE_PREFIX + r.status
        db.commit()
        return len(rows)
    finally:
        db.close()


def _restore_quarantined() -> int:
    """Undo every `e2e_quarantine_*` status prefix. Returns count."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Campaign)
            .filter(Campaign.status.like(QUARANTINE_PREFIX + "%"))
            .all()
        )
        for r in rows:
            r.status = r.status.removeprefix(QUARANTINE_PREFIX)
        db.commit()
        return len(rows)
    finally:
        db.close()


def _bid_payload(publisher_wallet: str) -> dict[str, Any]:
    return {
        "id": f"req-{uuid4().hex[:8]}",
        "imp": [
            {
                "id": "1",
                "video": {"w": 1920, "h": 1080},
                "ext": {
                    "wallet_id": publisher_wallet,
                    "device_id": E2E_DEVICE_ID,
                },
            }
        ],
    }


async def _post(
    client: httpx.AsyncClient, path: str, json: dict[str, Any]
) -> httpx.Response:
    return await client.post(path, json=json, headers=_publisher_headers())


def _extract_proof_context(bid_response: dict[str, Any]) -> str | None:
    seatbid = bid_response.get("seatbid") or []
    if not seatbid:
        return None
    bids = seatbid[0].get("bid") or []
    if not bids:
        return None
    return (bids[0].get("ext") or {}).get("proof_context")


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fastapi_app),
        base_url=BACKEND_URL,
        timeout=60.0,
    )


async def step_preflight() -> tuple[str, str]:
    _header("0. Pre-flight")
    settings = get_settings()
    if not settings.treasury_wallet_id or not settings.treasury_wallet_address:
        raise RuntimeError("TREASURY_WALLET_ID / TREASURY_WALLET_ADDRESS missing from .env")
    if not settings.privy_app_id or not settings.privy_app_secret:
        raise RuntimeError("PRIVY_APP_ID / PRIVY_APP_SECRET missing from .env")

    async with _new_client() as c:
        r = await c.get("/health")
        if r.status_code != 200:
            raise RuntimeError(f"backend /health returned {r.status_code}")

    # One retry: devnet RPC occasionally 429s and our balance helper falls
    # through to 0.0 on error. One retry is enough to distinguish.
    treasury_usdc = await get_usdc_balance(settings.treasury_wallet_address)
    if treasury_usdc == 0.0:
        await asyncio.sleep(2)
        treasury_usdc = await get_usdc_balance(settings.treasury_wallet_address)
    if treasury_usdc < CAMPAIGN_BUDGET_USDC + TINY_BUDGET_USDC + 0.01:
        raise RuntimeError(
            f"treasury has only {treasury_usdc} USDC — top up via Circle faucet first"
        )
    report.record(
        "backend + treasury healthy",
        True,
        f"treasury={treasury_usdc:.4f} USDC",
    )
    return settings.treasury_wallet_id, settings.treasury_wallet_address


async def step_happy_path(
    client: httpx.AsyncClient, campaign: Campaign
) -> str | None:
    _header("2. Happy path: bid -> proof")
    r = await _post(client, "/bid", _bid_payload(PUBLISHER_WALLET))
    if r.status_code != 200:
        report.record("bid returns 200", False, f"status={r.status_code}")
        return None
    proof_context = _extract_proof_context(r.json())
    if not proof_context:
        report.record("bid returns proof_context", False, "empty seatbid")
        return None
    report.record("bid returns proof_context", True)

    proof_body = {
        "proof_context": proof_context,
        "start_time": int(time.time()) - 16,
        "duration": 15,
    }
    r = await _post(client, "/proof", proof_body)
    if r.status_code != 200:
        report.record("proof returns 200", False, f"status={r.status_code} body={r.text[:200]}")
        return proof_context
    body = r.json()
    tx = body.get("tx_hash")
    if not tx:
        report.record("proof returns tx_hash", False, f"body={body}")
        return proof_context
    report.record(
        "proof settles on devnet",
        True,
        f"tx https://solscan.io/tx/{tx}?cluster=devnet",
    )

    # DB spent bumped by one play
    db = SessionLocal()
    try:
        fresh = db.query(Campaign).filter(Campaign.id == campaign.id).first()
        expected = CPM_USDC / 1000.0
        ok = fresh is not None and abs(float(fresh.spent) - expected) < 1e-9
        report.record(
            "campaign.spent incremented",
            ok,
            f"spent={fresh.spent if fresh else 'missing'}",
        )
    finally:
        db.close()

    return proof_context


async def step_replay_rejects(client: httpx.AsyncClient, proof_context: str) -> None:
    _header("3a. Edge: replay same proof_context -> 409")
    r = await _post(
        client,
        "/proof",
        {
            "proof_context": proof_context,
            "start_time": int(time.time()) - 16,
            "duration": 15,
        },
    )
    report.record(
        "replay rejected with 409",
        r.status_code == 409,
        f"got {r.status_code}: {r.text[:120]}",
    )


async def step_expired_proof(
    client: httpx.AsyncClient, campaign: Campaign
) -> None:
    _header("3b. Edge: expired proof_context -> 400")
    settings = get_settings()
    claims = ProofContextClaims(
        campaign_id=campaign.id,
        bid_id=f"expired-{uuid4().hex[:8]}",
        wallet_id=PUBLISHER_WALLET,
        nonce=f"expired-nonce-{uuid4().hex[:8]}",
        created_at=int(time.time()) - settings.proof_context_ttl_seconds - 60,
        amount_usdc=CPM_USDC / 1000.0,
    )
    token = encode_proof_context(claims, settings.jwt_server_secret, settings.jwt_algorithm)
    r = await _post(
        client,
        "/proof",
        {"proof_context": token, "start_time": int(time.time()) - 16, "duration": 15},
    )
    ok = r.status_code == 400 and "expired" in r.text.lower()
    report.record(
        "expired proof rejected with 400",
        ok,
        f"got {r.status_code}: {r.text[:120]}",
    )


async def step_paused_no_bid(
    client: httpx.AsyncClient, campaign: Campaign
) -> None:
    _header("3c. Edge: paused campaign -> no-bid")
    # Flip directly in DB (endpoint is JWT-gated). Everything else was already
    # quarantined in step 0, so once we pause this one there's nothing for FIFO.
    db = SessionLocal()
    try:
        target = db.query(Campaign).filter(Campaign.id == campaign.id).first()
        assert target is not None
        target.status = CampaignStatus.PAUSED.value
        db.commit()
    finally:
        db.close()

    try:
        r = await _post(client, "/bid", _bid_payload(PUBLISHER_WALLET))
        empty = r.status_code == 200 and not (r.json().get("seatbid") or [])
        report.record(
            "bid returns empty seatbid while paused",
            empty,
            f"status={r.status_code} seatbid_len={len(r.json().get('seatbid') or [])}",
        )
    finally:
        db = SessionLocal()
        try:
            target = db.query(Campaign).filter(Campaign.id == campaign.id).first()
            if target is not None:
                target.status = CampaignStatus.ACTIVE.value
            db.commit()
        finally:
            db.close()


async def step_budget_exhausted(
    client: httpx.AsyncClient,
    privy: PrivyClient,
    treasury_wallet_id: str,
    treasury_address: str,
    advertiser_id: str,
    advertiser_wallet: str,
) -> Campaign | None:
    _header("3d. Edge: budget exhausted -> no-bid")
    # Seed a second campaign so we don't collide with the one we've already
    # used for other tests, and quarantine the big one so FIFO hits this.
    try:
        tiny = await _seed_campaign(
            privy=privy,
            treasury_wallet_id=treasury_wallet_id,
            treasury_address=treasury_address,
            advertiser_id=advertiser_id,
            advertiser_wallet=advertiser_wallet,
            budget=TINY_BUDGET_USDC,
            cpm=CPM_USDC,
            name="e2e-tiny",
        )
    except PrivyError as e:
        report.record("seed tiny campaign", False, f"privy: {e}")
        return None
    except RuntimeError as e:
        report.record("seed tiny campaign", False, str(e))
        return None

    # Keep only the tiny campaign ACTIVE so FIFO hits it; restore in finally.
    _quarantine_active_except(tiny.id)

    try:
        expected_plays = int(round(TINY_BUDGET_USDC / (CPM_USDC / 1000.0)))
        # Drain the budget.
        for i in range(expected_plays):
            r = await _post(client, "/bid", _bid_payload(PUBLISHER_WALLET))
            pc = _extract_proof_context(r.json())
            if not pc:
                report.record(
                    f"bid #{i + 1} of {expected_plays}", False, "no proof_context"
                )
                return tiny
            r = await _post(
                client,
                "/proof",
                {"proof_context": pc, "start_time": int(time.time()) - 16, "duration": 15},
            )
            if r.status_code != 200:
                report.record(
                    f"proof #{i + 1}",
                    False,
                    f"status={r.status_code} body={r.text[:160]}",
                )
                return tiny
        report.record(
            f"drained tiny campaign in {expected_plays} plays", True
        )

        # One more bid — budget is 0, FIFO should pass on us.
        r = await _post(client, "/bid", _bid_payload(PUBLISHER_WALLET))
        empty = r.status_code == 200 and not (r.json().get("seatbid") or [])
        report.record("bid empty after budget drained", empty)

        db = SessionLocal()
        try:
            fresh = db.query(Campaign).filter(Campaign.id == tiny.id).first()
            ok = fresh is not None and fresh.status == CampaignStatus.COMPLETED.value
            report.record(
                "tiny campaign auto-flipped to completed",
                ok,
                f"status={fresh.status if fresh else 'missing'}",
            )
        finally:
            db.close()
        return tiny
    finally:
        _restore_quarantined()


async def step_double_refund(
    privy: PrivyClient, campaign: Campaign, advertiser_wallet: str
) -> None:
    """Exercises the same code paths the refund endpoint would, without a JWT.

    First attempt: drain the campaign wallet back to the advertiser, flip status.
    Second attempt: should refuse because status is already REFUNDED.
    """
    _header("3e. Edge: double refund")
    # Attempt 1
    db = SessionLocal()
    try:
        fresh = db.query(Campaign).filter(Campaign.id == campaign.id).first()
        assert fresh is not None
        remaining = float(fresh.budget) - float(fresh.spent)
        if remaining <= 0:
            fresh.status = CampaignStatus.REFUNDED.value
            db.commit()
            report.record("refund #1 (zero remaining -> no transfer)", True)
        else:
            try:
                tx_b64 = await build_usdc_transfer_tx(
                    from_address=fresh.wallet_address,
                    to_address=advertiser_wallet,
                    amount_usdc=remaining,
                )
                tx_hash = await privy.sign_and_send_solana(
                    wallet_id=fresh.wallet_id,
                    transaction_base64=tx_b64,
                    reference_id=f"refund-{fresh.id}",
                )
            except PrivyError as e:
                report.record("refund #1", False, f"privy: {e}")
                return
            fresh.status = CampaignStatus.REFUNDED.value
            fresh.refund_tx_hash = tx_hash
            db.commit()
            report.record(
                "refund #1 sent",
                True,
                f"amount={remaining:.6f} tx {tx_hash[:16]}…",
            )
    finally:
        db.close()

    # Attempt 2 — mirrors the endpoint's guard
    db = SessionLocal()
    try:
        fresh = db.query(Campaign).filter(Campaign.id == campaign.id).first()
        if fresh is None:
            report.record("refund #2 rejected", False, "campaign missing")
            return
        already = fresh.status == CampaignStatus.REFUNDED.value
        report.record(
            "refund #2 rejected because already refunded",
            already,
            f"status={fresh.status}",
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def main() -> int:
    print("=== x402 Ad Server — E2E demo (in-process ASGI against app.main:app) ===")
    try:
        treasury_wallet_id, treasury_address = await step_preflight()
    except Exception as e:  # noqa: BLE001
        print(f"pre-flight failed: {e}")
        return 1

    privy = PrivyClient()

    advertiser_id = f"did:privy:e2e-{uuid4().hex[:10]}"
    advertiser_wallet = treasury_address  # reuse treasury address as the "advertiser wallet" for refund tests

    # Clean slate for FIFO: hide every pre-existing ACTIVE campaign (e.g. Session 5's
    # test-camp-s5). Restored in the `finally` below.
    quarantined_count = _quarantine_active_except(keep_id=None)
    print(f"\n(quarantined {quarantined_count} pre-existing active campaign(s) for the run)")

    _header("1. Seed fresh campaign end-to-end")
    try:
        main_campaign = await _seed_campaign(
            privy=privy,
            treasury_wallet_id=treasury_wallet_id,
            treasury_address=treasury_address,
            advertiser_id=advertiser_id,
            advertiser_wallet=advertiser_wallet,
            budget=CAMPAIGN_BUDGET_USDC,
            cpm=CPM_USDC,
            name="e2e-main",
        )
    except (PrivyError, RuntimeError) as e:
        report.record("seed main campaign", False, str(e))
        _restore_quarantined()
        return 1
    report.record(
        "seed main campaign",
        True,
        f"id={main_campaign.id} wallet={main_campaign.wallet_address[:12]}…",
    )

    try:
        async with _new_client() as client:
            proof_context = await step_happy_path(client, main_campaign)

            if proof_context:
                await step_replay_rejects(client, proof_context)

            await step_expired_proof(client, main_campaign)
            await step_paused_no_bid(client, main_campaign)
            await step_budget_exhausted(
                client=client,
                privy=privy,
                treasury_wallet_id=treasury_wallet_id,
                treasury_address=treasury_address,
                advertiser_id=advertiser_id,
                advertiser_wallet=advertiser_wallet,
            )
            await step_double_refund(privy, main_campaign, advertiser_wallet)
    finally:
        restored = _restore_quarantined()
        if restored:
            print(f"\n(restored {restored} quarantined campaign(s))")

    # Summary
    _header("Summary")
    passed = sum(1 for s in report.steps if s.passed)
    total = len(report.steps)
    print(f"  {passed}/{total} steps passed")
    for s in report.steps:
        marker = "✓" if s.passed else "✗"
        print(f"    {marker} {s.name}")

    # Dangling failed settlements?
    db = SessionLocal()
    try:
        failed = (
            db.query(Settlement)
            .filter(Settlement.status == SettlementStatus.FAILED.value)
            .count()
        )
    finally:
        db.close()
    if failed:
        print(f"\n  note: {failed} failed settlement(s) in DB — run scripts/retry_settlements.py")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
