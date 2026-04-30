# Session 6 — Campaign management ✅

**Date:** 2026-04-21

## Checklist

- [x] `GET /api/campaigns` — list for authenticated advertiser, ordered newest-first
- [x] `GET /api/campaigns/:id` — single campaign summary (owner-gated)
- [x] `GET /api/campaigns/:id/stats` — budget / spent / remaining + total confirmed plays + last 10 settlements
- [x] `GET /api/campaigns/:id/settlements` — full settlement history with Solscan URLs
- [x] `POST /api/campaigns/:id/pause` — `active` → `paused`
- [x] `POST /api/campaigns/:id/resume` — `paused` → `active` (rejected if no remaining budget)
- [x] `POST /api/campaigns/:id/refund` — builds USDC transfer from campaign wallet → advertiser wallet, Privy `signAndSend`, sets status → `refunded`, saves `refund_tx_hash`
- [x] Ownership check on every endpoint (`advertiser_id` on campaign must match JWT `sub`)
- [x] `schemas.CampaignStats`, `SettlementSummary`, `RefundResponse` added
- [x] Solscan URL helper shared across stats/settlements/refund responses

**Exit criteria partial:** OpenAPI registers all 7 endpoints, auth gates fire (401 unauth, JWKS-backed 401 on bogus bearer), DB stats query returns expected shape for the Session 5 test campaign (1 play, 0.0125 spent, 0.9875 remaining). **Full lifecycle curl walk (create → fund → play → pause → refund) blocked on a real Privy JWT and deferred to Session 9.**

## Work log entry

- **2026-04-21 (Session 6):** Campaign management — list, detail, stats, settlements, pause, resume, refund. 7 endpoints registered, ownership guards active, Solscan URLs populated. Direct DB stats-query simulation against test-camp-s5 confirms correct shape. Full HTTP lifecycle test deferred to Session 9 (needs Privy JWT).
