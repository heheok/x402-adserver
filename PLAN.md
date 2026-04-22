# x402 Ad Server — Build Plan

Living document. Updated at the end of every working session.

> **🚀 Resuming work from a cold start? Read this first.**
>
> 1. Read `BACKGROUND-INFORMATION.md` for the product spec (read-only reference). For commercial/stakeholder questions, see `BUSINESS-CONSTRAINTS.md`.
> 2. Scan this file's **Session roadmap** below — the first session without ✅ in its heading is where to pick up. Inside each session, the checked boxes tell you what's done.
> 3. Read `RUNBOOK.md` for every repeated ops task (start/stop, balance checks, funding, resets).
> 4. Confirm the user has `backend/.env` populated. The treasury vars (`TREASURY_WALLET_ID`, `TREASURY_WALLET_ADDRESS`) come from `scripts/bootstrap_treasury.py`. If they don't exist, bootstrap + fund per RUNBOOK.
> 5. Start containers: `docker compose up -d backend`. Smoke: `curl localhost:8000/health`.
> 6. The SQLite DB may be empty — that's expected. Seed with `scripts/seed_test_campaign.py` (future) or the one-liner in the work log if you need a live campaign for testing.
> 7. Architectural decisions are fixed (see **Protocol notes** below and `memory/project_x402_adserver.md`). Don't re-litigate.
> 8. Update this file and `RUNBOOK.md` at the end of every session.


**North star:** end-to-end demo loop on Solana devnet —
login → faucet → fund (x402) → bid → proof → settle → refund.

**Deadline:** 19 days to Solana Colosseum submission. Day 1 = 2026-04-21.

**Scope reminders**
- Backend: FastAPI + SQLite (Postgres later for prod).
- Frontend: React + Vite + Privy embedded wallets.
- Wallets: Privy server wallets (no Anchor, no Rust).
- Facilitator: `https://x402.org/facilitator` (no API key).
- Everything Dockerized; compose for local dev.
- Anything that does not serve the demo loop is deferred.

---

## Session roadmap

Each session is ~1 working block. Order is the dependency chain — later sessions need earlier ones.

### Session 1 — Scaffold + plumbing ✅
- [x] `PLAN.md` with full roadmap
- [x] `backend/` layout (app, routers, services, models)
- [x] FastAPI skeleton with health endpoint
- [x] SQLite + SQLAlchemy engine, session, `Base.metadata.create_all`
- [x] DB models: `campaigns`, `settlements`, `used_nonces`
- [x] Config via `pydantic-settings` + `.env.example`
- [x] Auth dependency stubs (`X-API-Key` for publisher, Privy-JWT placeholder)
- [x] Router stubs for `/bid`, `/proof`, `/api/campaigns`, `/api/wallet`, `/api/faucet`
- [x] `Dockerfile` for backend
- [x] `docker-compose.yml` (backend service only for now)
- [x] `.gitignore`, `README.md` run instructions

**Exit criteria:** `docker compose up backend` serves `GET /health` → 200, `GET /docs` lists all stub endpoints returning 501.

### Session 2 — Privy + wallet endpoints ✅
- [x] Add `solana==0.36.6`, `solders==0.23.0` to `requirements.txt`
- [x] Privy REST client (`services/privy.PrivyClient`) — create, list, get, signAndSend, get_user, fetch_jwks
- [x] Solana helpers (`services/solana`) — USDC balance, USDC transfer tx builder, devnet SOL airdrop
- [x] Treasury bootstrap script (`scripts/bootstrap_treasury.py`) — idempotent, prints env vars + Circle faucet instructions
- [x] Privy JWT verification against JWKS (`dependencies._verify_privy_jwt`, ES256)
- [x] `GET /api/wallet` — resolves advertiser's Solana wallet via Privy, reads USDC balance from RPC
- [x] `POST /api/faucet` — treasury → advertiser (100 USDC) via signAndSendTransaction
- [ ] **User action**: rebuild image, run `bootstrap_treasury.py`, paste vars into `.env`, fund treasury via Circle faucet

**Exit criteria:** Log in via Privy on the React dashboard (or any JWT source), hit `/api/faucet`, see USDC arrive in the user's wallet on Solscan devnet.

**Privy API validated (2026-04-21):** creation, listing, and `signAndSendTransaction` all documented and exercised. Probe script confirmed full access. Devnet caip2 = `solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1`. Campaign-wallet reuse helper lives in `PrivyClient.create_solana_wallet()` — Session 3 calls it per campaign.

### Session 3 — x402 campaign creation ✅
- [x] `services/x402.py` — `build_payment_requirements`, `build_402_body`, `decode_payment_header`, `verify`, `settle`
- [x] `POST /api/campaigns` step 1 (no X-PAYMENT): create draft + Privy wallet + airdrop SOL, return 402 with PaymentRequirements body
- [x] `POST /api/campaigns` step 2 (with X-PAYMENT): decode, look up latest draft, facilitator `/verify` + `/settle`, flip status → `active`
- [x] Campaign row populated with all creative/budget/wallet fields on draft creation
- [x] `X-PAYMENT-RESPONSE` header returned on the success path (echoes the settled tx hash)

**Deferred to Session 9 (needs dashboard to issue real Privy JWTs):** true end-to-end verification (402 → sign → retry → 200). Session 3 verification today is limited to:
- Backend starts clean with new code
- `/docs` lists POST /api/campaigns with updated shape
- Unauthenticated call returns 401

**Protocol reference used:** `https://github.com/coinbase/x402/blob/main/specs/x402-specification-v1.md` and `.../schemes/exact/scheme_exact_svm.md`. Devnet network id: `solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1`.

**Retry matching:** "latest DRAFT campaign for this advertiser." Good enough for demo. Flagged as `FIXME` candidate for production (use client-supplied idempotency key).

### Session 4 — Bid matching ✅
- [x] `services/tokens.encode_proof_context` / `decode_proof_context` (HS256, self-contained claims)
- [x] `POST /bid` — OpenRTB-lite parsing, FIFO campaign pick, minted `proof_context` JWT
- [x] No-bid paths: missing impression, missing publisher wallet, no active campaigns, budget exhausted
- [x] Pure in-process: one DB query, no external calls — fits the <500ms budget

**Exit criteria met:** Verified via 4 curl smokes (no-key 401, no-match no-bid, positive bid with decoded JWT, exhausted no-bid). Signed `proof_context` decoded cleanly to the expected claims (campaign_id, bid_id, publisher wallet, fresh nonce, timestamp, amount = cpm/1000).

### Session 5 — Proof of play + settlement ✅
- [x] `POST /proof` — JWT signature verify via `services/tokens.decode_proof_context`
- [x] TTL check (1 hour from `created_at`, small skew tolerance)
- [x] Nonce dedup via atomic insert into `used_nonces` (`IntegrityError` → 409)
- [x] Duration min = 1 second
- [x] Budget check + spent decrement before settling; auto-flip to `completed` when drained
- [x] Privy `signAndSendTransaction` → publisher wallet, `reference_id=settlement-<nonce>` for Privy-side idempotency
- [x] Settlement rows recorded for both success (`confirmed` + tx_hash) and failure (`failed`, tx_hash null) paths

**Exit criteria met — verified on real devnet 2026-04-21:**
- Campaign seeded (treasury reused as campaign wallet for the smoke)
- `/bid` → minted `proof_context` JWT for publisher `3pMCrwRq…V8W9`
- `/proof` → HTTP 200 with tx hash `3i5y7hga…xQ9h` ([Solscan](https://solscan.io/tx/3i5y7hgaJVoXtvQUc343MPfCP6PCxPdBsygBUgd6RjckgP865BGDoLBLBSQQUczgWsr1vVksvd4yLiDC3MQFxQ9h?cluster=devnet))
- 0.0125 USDC moved treasury → publisher on-chain, confirmed via `check_balance.py`
- Replay same proof_context → 409 `nonce already used`
- DB state matches: `campaigns.spent=0.0125`, one `used_nonces` row, one `settlements` row

Leftover state: test campaign `test-camp-s5` and its settlement remain in DB — useful for Session 6's list/stats/settlements endpoints. Reset via `docker volume rm x402_backend_data` if needed (see RUNBOOK).

### Session 6 — Campaign management ✅
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

### Session 7 — Backend integration + hardening ✅
- [x] End-to-end integration test script (`scripts/e2e_demo.py`) — in-process ASGI, 13 steps
- [x] Edge cases: expired proof, duplicate nonce, insufficient budget, paused campaign, double refund
- [x] Error logging for Privy/facilitator failures (module loggers + `logger.exception` at every boundary)
- [x] Pending-settlement retry queue stub (`app/services/retry.py` + `scripts/retry_settlements.py`)

**Exit criteria met (2026-04-22):** `docker compose run --rm backend python scripts/e2e_demo.py` → 13/13 steps pass on real devnet.

**Hardening picked up while writing the E2E:**
- `get_usdc_balance` no longer crashes on solana-py error-response objects (e.g. `InvalidParamsMessage` when the ATA doesn't exist yet).
- Added retry-with-backoff (2/4/8/16s) to `PrivyClient.sign_and_send_solana` for the `transaction_broadcast_failure` code. Privy's simulation RPC trails devnet by tens of seconds for fresh ATAs; the retry makes /proof robust to that. `reference_id` gives Privy-side idempotency so retries never double-spend.
- New `services/solana.build_sol_transfer_tx` helper, used in `create_campaign` to seed each fresh campaign wallet with 0.01 SOL from the treasury (RPC airdrops on devnet are rate-limited; the old `airdrop_sol` was best-effort and silently failed, leaving campaign wallets unable to pay their own fees).
- RUNBOOK typo fix: `FINCH_API_KEY` → `PUBLISHER_API_KEY`. New RUNBOOK sections for the E2E smoke and the retry script.

### Session 8 — React dashboard scaffold ✅
- [x] `frontend/` with Vite + React + TS (+ React Query + Zustand as deps)
- [x] Privy React SDK + provider config (Solana devnet cluster, email login, embedded wallet on login)
- [x] API client wrapper (`lib/api.ts` — public `api` singleton + `useApi()` hook that injects Privy JWT)
- [x] Dockerfile for dashboard, compose wiring (anonymous `node_modules` volume so host mount doesn't shadow image deps)
- [x] Basic layout: `<Login>` ↔ `<Home>`, gated by Privy `authenticated` state; Home smoke-tests backend `/health` via React Query
- [x] Backend CORS middleware (`cors_allow_origins` in settings, default `localhost:5173` + `127.0.0.1:5173`); exposes `X-PAYMENT-RESPONSE` for Session 9's x402 flow

**Verified in browser (2026-04-22):**
- `docker compose up -d` brings both services healthy (backend 8000, frontend 5173)
- CORS preflight from `http://localhost:5173` origin → 200 with matching allow-origin header
- Login flow: email OTP via Privy → Home renders with user email + live `/health` response
- Logout returns to Login; no console errors

**Late-cycle fix-ups (also landed in Session 8):** Privy + Solana in Vite needed the `vite-plugin-node-polyfills` plugin (for `Buffer`/`process`/`global`) plus the `@solana/kit` + `@solana-program/{memo,system,token}` peer-dep stack per Privy's Vite troubleshooting docs. Manual `globalThis.Buffer = Buffer` polyfill in main.tsx didn't work because ES-module hoisting runs Privy imports before the polyfill line. Also: rebuilding the frontend image without `--renew-anon-volumes` preserved the old `node_modules` and silently no-op'd dep updates — documented in frontend README for future dep bumps.

### Session 9 — Dashboard flows (fund)  ← NEXT
- [ ] Login screen (Privy email)
- [ ] Wallet panel (address + balance + "Get test USDC" button)
- [ ] Create campaign form
- [ ] Fund campaign via `x402-solana/client` (auto 402 handshake)

### Session 10 — Dashboard flows (play + refund)
- [ ] "Simulate ad play" button → hits a dev-only endpoint that fires mock `/bid` + `/proof`
- [ ] Campaign detail page: stats, settlements table, Solscan tx links
- [ ] Refund button

### Session 11 — Integration polish
- [ ] Real devnet end-to-end with judge-like flow
- [ ] Treasury pre-funded from Circle faucet
- [ ] Loading states, error toasts, optimistic UI
- [ ] Balance polling (2s interval during settlement)

### Session 12 — GCP deployment prep
- [ ] Cloud Run configs (backend)
- [ ] Cloud SQL Postgres migration from SQLite
- [ ] Secret Manager for Privy secret, JWT server secret
- [ ] Cloud Storage + CDN for dashboard build

### Session 13 — Deploy to GCP
- [ ] Deploy backend to Cloud Run
- [ ] Deploy dashboard
- [ ] CORS, custom domain if time permits
- [ ] Smoke test on live devnet

### Session 14 — Demo rehearsal + submission
- [ ] Judge demo script (2-3 min)
- [ ] Record demo video
- [ ] Submission README + Devpost writeup

### Buffer (sessions 15+)
- Blockers, polish, stretch items (batch settlement toggle, better fraud checks).

---

## Protocol notes (research findings, keep handy)

### x402 `upto` scheme — NOT usable on Solana today (verified 2026-04-21)

**Evidence (all direct file listings, not summaries):**
- Coinbase reference repo `github.com/coinbase/x402`: every `upto` path is under `evm/`:
  `contracts/evm/src/x402UptoPermit2Proxy.sol`, `go/mechanisms/evm/upto/…`,
  `typescript/packages/mechanisms/evm/src/upto/…`,
  `specs/schemes/upto/scheme_upto_evm.md`. No `upto_svm` or `svm/upto` anywhere.
- `typescript/packages/mechanisms/svm/src/` has an `exact/` folder and no `upto/`.
- npm `@x402/svm@2.10.0` README line 1: *"SVM implementation of the x402 payment protocol using the **Exact** payment scheme with SPL Token transfers."* Only `ExactSvmClient`, `ExactSvmFacilitator` are exported.
- Technical reason: `upto` on EVM uses Permit2; Solana has no Permit2 equivalent yet.

**When Solana `upto` ships, what changes in our codebase:**

Untouched (~75%): `/bid`, `/proof`, FIFO matching, OpenRTB contract, React dashboard shell, Privy auth, `used_nonces`, `settlements`, `proof_context` JWT design.

Changes (~25%, additive — our service split was built for this swap):
| Piece               | Today (`exact`)                           | Future (`upto`)                                       |
| ------------------- | ----------------------------------------- | ----------------------------------------------------- |
| Campaign wallet     | Privy server wallet per campaign          | Not needed — funds stay in advertiser wallet          |
| Funding request     | 402 → full-budget USDC transfer           | 402 → signed authorization (cap + expiry + nonce)     |
| Per-play settlement | Privy `signAndSend` from campaign wallet  | Facilitator `draw` against authorization              |
| Refund endpoint     | Transfer remainder back to advertiser     | Delete — authorization just expires                   |
| `services/x402.py`  | `exact` builder only                      | Add `upto` builder + `draw` helper                    |
| `models.Campaign`   | `wallet_id`/`wallet_address`              | Swap for `authorization_token`/`authorized_until`     |

**Estimated effort when the spec+SDK are ready:** 2–3 sessions.

**Re-check trigger:** watch `github.com/coinbase/x402/tree/main/specs/schemes/upto/` for a `scheme_upto_svm.md` file. When it appears, re-evaluate.

---

## Resolved decisions (post-hackathon scope)
- **Production advertiser auth = API key (decided 2026-04-22).** Third-party ad-tech platforms cannot be forced to adopt Privy. Production `/api/campaigns*` and `/api/wallet` routes will authenticate via `X-API-Key` against a new `advertisers` table. `require_advertiser` (Privy JWT) remains for dev/demo only. Build work is tracked as mainnet blocker §7.2 in `BUSINESS-CONSTRAINTS.md`. `BACKGROUND-INFORMATION.md §Auth` says "Privy or API key" — that ambiguity is now resolved.

## Open decisions still to resolve
- Alembic migrations vs `create_all` — skipping Alembic until Postgres in Session 12.
- Dashboard host port — pinning to 5173 locally; revisit for deploy.
- Rate limiting on `/api/faucet` — one shot per user per hour? Decide in Session 2.
- **Decoupling campaign-api from ad-server** (raised 2026-04-21, deferred). Three options sized: Option A = shared DB + two FastAPI apps (~1 session), Option B = independent DBs + internal HTTP (~2–3 sessions, adds network hop to bid path — risky for <500ms target), Option C = event-driven (~3–5 sessions, production-grade). Leaning Option A if we decide to do it; slot between Session 7 and Session 8.
- **SOL gas subsidy model — MUST resolve before mainnet** (raised 2026-04-22 in Session 7). Today the treasury seeds every new campaign wallet with 0.01 SOL (~$2 on mainnet) so the wallet can pay its own tx fees for `/proof` settlements and refunds. After refund, any unused SOL is stranded forever (Privy has no wallet-delete). Per-play fees are ~5000 lamports. Options: **(A)** Privy fee sponsorship via `sponsor: true` on `sign_and_send_solana` — cleanest, zero SOL seeding, no stranded dust, pricing depends on Privy plan; **(B)** keep subsidy + price it into CPM, accept abandoned-draft loss of $0.40 ATA rent each; **(C)** charge advertiser SOL via a second x402 challenge — blocked by the recursive gas problem (their embedded wallet also starts at 0 SOL, so we'd have to seed theirs too). **Recommendation:** investigate (A) first — it's a one-line flag flip. Whole category evaporates once Solana `upto` ships (see Protocol notes) because campaign wallets go away entirely. Decide before Session 13 (GCP deploy) at latest.

## Environment / secrets checklist
- [ ] `PRIVY_APP_ID` (supplied by user)
- [ ] `PRIVY_APP_SECRET` (supplied by user)
- [ ] `JWT_SERVER_SECRET` (we generate)
- [ ] `PUBLISHER_API_KEY` (we generate; the publisher network will be given one)
- [ ] `SOLANA_RPC_URL` — default devnet `https://api.devnet.solana.com`
- [ ] `X402_FACILITATOR_URL` — `https://x402.org/facilitator`
- [ ] `USDC_MINT_DEVNET` — `4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU`
- [ ] `TREASURY_WALLET_ID` — generated via bootstrap script in Session 2

## Work log
- **2026-04-21 (Session 1):** scaffold committed. Backend boots in Docker, all stub endpoints return 501. SQLite tables auto-created. See `backend/README.md`.
- **2026-04-21 (Session 1 close-out):** Privy REST API validated against current docs (create, list, signAndSendTransaction all confirmed). User populated `backend/.env` with `PRIVY_APP_ID` / `PRIVY_APP_SECRET`, verified `/health` and `/docs` live. Cleared to start Session 2.
- **2026-04-21 (Session 1 probe):** `scripts/probe_privy.py` succeeded — listed 0 wallets, created test Solana wallet `joitr710uuxa942x6kjr4x2g` / `3pMCrwRq5tNy1GdonrPivP389eYjeeoGTiMZDtQmV8W9`. Server wallets are fully accessible on this Privy app. Fixed: added `./backend/scripts` volume mount to compose + `COPY scripts ./scripts` to Dockerfile so dev scripts ship with the container.
- **2026-04-21 (Session 2):** Privy client, Solana helpers (balance + USDC transfer builder + airdrop), real JWKS JWT verification, `bootstrap_treasury.py`, `check_balance.py`, `/api/wallet`, `/api/faucet`. Treasury wallet `dh52nvrial6szf2bupq4dcar` / `D4atNw3qRuXUkcKVuzGgosJemP3bboT1B7FSNjHdpjUJ` created and funded by user (SOL + ~20 USDC). Published `RUNBOOK.md` at repo root for ops.
- **2026-04-21 (Session 3):** x402 facilitator client (`services/x402.py`) and 402 handshake on `POST /api/campaigns`. Smoke verified: 401 on unauth, JWKS-backed 401 on bogus bearer, `/health` still 200. Real E2E (sign → retry → 200) deferred to Session 9 because a browser Privy wallet is the only thing that can mint the payment payload.
- **2026-04-21 (Protocol research):** Verified x402 `upto` is EVM-only today (no `scheme_upto_svm.md`, no `svm/src/upto/` in Coinbase reference repo, `@x402/svm@2.10.0` README states exact-only). Findings + migration plan captured in PLAN.md → "Protocol notes".
- **2026-04-21 (Session 4):** `POST /bid` implemented with FIFO matching + signed `proof_context`. Four curl smokes pass (no-key 401, no-match no-bid, positive bid, budget-exhausted no-bid). `services/tokens` now has working HS256 encode/decode ready for Session 5 proof verification.
- **2026-04-21 (Session 5):** `POST /proof` implemented end-to-end. First true on-chain test of the pipeline: bid → proof → real USDC transfer on devnet. Tx hash `3i5y7hga…xQ9h` settles 0.0125 USDC treasury → publisher. Replay protection verified (409 on duplicate nonce). DB state consistent across campaigns/used_nonces/settlements.
- **2026-04-21 (Session 6):** Campaign management — list, detail, stats, settlements, pause, resume, refund. 7 endpoints registered, ownership guards active, Solscan URLs populated. Direct DB stats-query simulation against test-camp-s5 confirms correct shape. Full HTTP lifecycle test deferred to Session 9 (needs Privy JWT).
- **2026-04-22 (Session 7):** Integration + hardening. `scripts/e2e_demo.py` exercises the full loop against real devnet via in-process ASGI (13/13 steps pass); covers happy path, replay 409, expired 400, paused no-bid, budget-exhaust auto-complete, double-refund guard. Retry stub (`services/retry.py` + `scripts/retry_settlements.py`) drains failed `settlements` rows. Discovered and fixed: (a) `get_usdc_balance` crashed on solana-py's `InvalidParamsMessage` error responses, (b) fresh Privy campaign wallets ended up with 0 SOL (devnet airdrop unreliable) so /proof + refund couldn't pay fees — now SOL-seeded from treasury via `build_sol_transfer_tx`, (c) Privy's simulation RPC lags devnet by 10–60s for new ATAs — added exponential-backoff retry keyed on `transaction_broadcast_failure` inside `sign_and_send_solana`. Structured logging (`logger.exception`) added at every Privy/facilitator boundary.
