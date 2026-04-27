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

### Session 9 — Dashboard flows (fund) ✅
- [x] Login screen (Privy email) — done in Session 8 (auth gate routes to `<Login>` when unauthenticated)
- [x] Wallet panel (address + balance + "Get test USDC" button)
- [x] Create campaign form
- [x] Fund campaign via `x402-solana/client` (auto 402 handshake)

**Verified end-to-end on devnet (2026-04-22):** login → faucet → create-campaign form → click submit → Privy signing popup → `X-PAYMENT` retry → facilitator `/verify` + `/settle` → 200 + `X-PAYMENT-RESPONSE` → Solscan tx link in the success box. Wallet balance debits within 2–4s of success via shared `walletTrack` Zustand store.

**Key integration findings (all earned the hard way — keep for the next session):**
- **Library choice:** PayAI's `x402-solana@^2.0.4` is the right npm pick for Privy-based apps. Coinbase's `@x402/svm` wants `@solana/kit` `TransactionSigner` and has no documented Privy adapter. PayAI's client works with `wallets[0]` from `useSolanaWallets()` directly — no shim needed in our Privy SDK version.
- **Client hard-requires destination USDC ATA to exist before it builds the transfer tx** (`dist/index.js:167`). Since each campaign creates a fresh Privy server wallet with no ATA, the backend must pre-create it. We bundle SOL-seed + `create_idempotent_associated_token_account` into a single treasury-signed tx and wait for confirmation before returning 402 (`services/solana.build_campaign_bootstrap_tx` + `wait_for_tx_confirmation`).
- **x402.org facilitator's v1 Solana entry is registered under short name `"solana-devnet"`, NOT CAIP-2** `solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1`. CAIP-2 is only registered under v2. Mismatch → `No facilitator registered for scheme: exact and network: …`. The `x402-solana` client accepts either form interchangeably — we emit the short name from `services/x402.DEVNET_NETWORK`.
- **`https://x402.org/facilitator` 308-redirects to `www.x402.org`.** Default config URL is now the www form; httpx clients also have `follow_redirects=True` as belt-and-braces.
- **`extra.feePayer` in PaymentRequirements MUST be the facilitator's own address** — not the advertiser, not the campaign wallet. The `x402-solana` client unconditionally builds the tx with `payerKey = extra.feePayer` (`dist/index.js:189`) and expects the facilitator to co-sign during `/settle`. Any other value → `fee_payer_not_managed_by_facilitator` on verify. Upshot: the old "advertiser pays gas" plan (Config 3) is impossible with x402-solana + x402.org; Config 2 (facilitator pays) is the only working option. The facilitator publishes its fee-payer address at `/supported` — fetched lazily + cached by `services/x402.get_facilitator_fee_payer()`.
- **Wallet balance polling:** devnet RPC lags 2–5s behind finality, so a single `invalidateQueries` after a money-moving mutation reads stale. `lib/walletTrack.ts` is a small shared Zustand store — any component calls `startPolling(ms)` and `WalletPanel` refetches `/api/wallet` every 2s until the window closes. Reused by faucet + fund today, reuse in refund/settle tomorrow.

**Gotchas (also in code comments) still relevant for Session 10+:**
- Privy `reference_id` is NOT strict pre-broadcast idempotency (`BUSINESS-CONSTRAINTS.md §3`). Use unique suffixes per-call on faucet/settlement/fund flows.
- Fresh Privy users only get a Solana embedded wallet if `embeddedWallets.solana.createOnLogin` is set (nested config, not top-level). Existing EVM-wallet users need a manual "Create Solana wallet" button via `useSolanaWallets().createWallet()` — already handled in WalletPanel.
- Docker + Windows: edits hot-reload only because `vite.config.ts` has `server.watch.usePolling: true`. Don't remove it.
- Dep bumps need `--renew-anon-volumes` to actually land in the container (documented in `frontend/README.md`).

### Session 10 — Dashboard flows (play + refund) ✅
- [x] "Simulate ad play" button → hits a dev-only endpoint that fires mock `/bid` + `/proof`
- [x] Campaign detail page: stats, settlements table, Solscan tx links
- [x] Refund button

**Shape that shipped:**
- Campaigns are now displayed as an expandable list (`<CampaignsPanel>` + `<CampaignCard>`) rather than a separate detail page. Each card shows name + status badge + spent/budget progress bar; clicking expands into stats, wallet address, last-10 settlements (with Solscan links), and action buttons whose set depends on status (active → simulate + pause; paused → resume + refund; completed → refund; refunded → read-only).
- Simulate-play endpoint: `POST /api/campaigns/:id/simulate-play` (advertiser-authed) mints a `ProofContextClaims` server-side using `demo_publisher_wallet` from settings and reuses the settlement pipeline via a new `execute_settlement()` helper factored out of `/proof`. In production, real publishers still call `/bid` + `/proof` with the publisher API key — this endpoint exists so the dashboard can drive the demo without exposing the publisher key in the browser.
- Refund onSuccess invalidates the wallet query and triggers `walletTrack.startPolling(20_000)` so the advertiser wallet balance visibly ticks back up as the refund tx confirms on devnet.

**Key code locations added in this session:**
- `backend/app/routers/proof.execute_settlement` — nonce-claim + budget decrement + Privy transfer + settlement row, shared between `/proof` and `/api/campaigns/:id/simulate-play`.
- `backend/app/routers/campaigns.simulate_play` — dashboard-only /proof driver, uses `settings.demo_publisher_wallet`.
- `frontend/src/components/CampaignsPanel.tsx` + `CampaignCard.tsx` — list + expandable detail.

### Session 11 — Integration polish ✅
- [x] `lib/errors.humanizeError()` — unwraps FastAPI `{detail}` + our manual x402 throws; applied across all error displays. No more "Request failed with status code 400".
- [x] Form balance guard — `CreateCampaignForm` reads the cached `["wallet"]` query and disables submit + shows a clear message if `budget > balance`, before the signing attempt.
- [x] Accurate 3-stage funding progress via instrumented `customFetch` on the x402 client (`preparing` / `signing` / `settling`).
- [x] Demo auto-play — server-side background loop (`services/auto_play.py`) that, when `AUTO_PLAY_ENABLED=true`, randomly picks one active + funded campaign every `AUTO_PLAY_INTERVAL_SECONDS` (default 15) and runs `execute_settlement` against `DEMO_PUBLISHER_WALLET`. Off by default. Dashboard polls `GET /api/auto-play-status` and shows a pulsing "Auto-simulating…" badge when enabled, plus refetches the campaign list + expanded stats on the same cadence so settlements tick in live. **This is a demo aid only — production publishers drive `/bid` + `/proof` themselves. `AUTO_PLAY_ENABLED` MUST be false in any deployed environment.**
- [x] Real devnet end-to-end judge walkthrough (user ran manually 2026-04-22)
- [x] Treasury pre-funded from Circle faucet (Session 2)
- [x] Balance polling during settlement — `lib/walletTrack.ts`, Session 9/10

### Session 12 — Treasury topup helpers (multi-wallet workaround) ✅
- [x] `scripts/bootstrap_helpers.py` (new, separate from `bootstrap_treasury.py`) — creates N helper Privy server wallets (default 3, `--count N`); prints `HELPER_WALLET_IDS` + `HELPER_WALLET_ADDRESSES` (comma-separated) for paste into `.env`. Settings fields added to `app/config.py`.
- [x] Each helper seeded with 0.01 SOL from the treasury via `build_sol_transfer_tx` + `wait_for_tx_confirmation`. RPC airdrop dropped — same lesson as the campaign-wallet seed flow (devnet airdrops silently fail).
- [x] `scripts/sweep_helpers.py` — default mode reads env, zips ids+addresses, sweeps any non-zero helper to `TREASURY_WALLET_ADDRESS`. Plus `--wallet-id` + `--wallet-address` rescue mode for one-off sweeps.
- [x] `RUNBOOK.md` "helper multiplex" section under Top up — bootstrap, paste, recreate, daily click+sweep routine, plus rescue command.
- [x] Circle account-upgrade probe — `/v1/faucet/drips` returns HTTP 403 for sandbox keys (verified 2026-04-24, KYC-gated). Manual web-faucet sweep is the only path until/unless Circle upgrade lands.

**Why this is first:** lead time matters. Every day we don't run the helper-claim routine is ~60 USDC of foregone treasury runway. Shipped before the wizard work so it accumulates in the background.

**Why multi-wallet manual:** Circle programmatic `/v1/faucet/drips` returns HTTP 403 for sandbox keys (verified 2026-04-24) — the docs' "requires upgrading to mainnet" line maps to a real account-level KYC gate. Public web faucet is captcha-gated so cannot be safely automated. Per-address rate limit (20 USDC / 2h) is the documented Circle policy, verified empirically on 2026-04-27 (one helper claim then immediately a treasury claim from the same browser session — both succeeded), so N independent addresses give N × 20 USDC per cycle.

**Exit criteria met (2026-04-27):** rescued the throwaway helper from `create_helper_wallet.py` (recovered 20 USDC into treasury), bootstrapped 3 fresh helpers, manually claimed Circle faucet into all 4 (4 × 20 = 80 USDC), `sweep_helpers.py` consolidated all of it to treasury in one run with 4 Solscan tx hashes. Treasury USDC visibly grew by ~80.

**Reference-id length gotcha:** Privy caps `reference_id` at 64 chars. Initial sweep used a full uuid4 string suffix → 68 chars → 400 `invalid_data`. Codebase convention is `uuid4().hex[:8]` (matches `routers/wallet.py` faucet, `routers/campaigns.py` campaign-bootstrap). Kept that pattern in both helper scripts.

### Session 13 — Wizard shell + creative image upload (Feature 1) ✅
- [x] Refactor `CreateCampaignForm.tsx` into a wizard shell with step indicator + back/next; closing the modal discards state (no draft persistence between steps)
- [x] **Step 1 — Image**: file picker (JPG/PNG only), client-side validation via `Image()` constructor (must be exactly 1920×1080), preview thumbnail, **auto-upload-on-pick** (improved over the original "upload-on-next" wording — see findings) with progress bar
- [x] Backend: `POST /api/creatives` (multipart, advertiser-authed). Re-validates with Pillow (don't trust browser). Uploads to `gs://x402-adserver-creatives/creatives/{uuid}.{ext}`. Returns `{creative_id, creative_url, width, height, format}`.
- [x] Bucket setup: uniform bucket-level access + `allUsers:objectViewer`
- [x] Service account JSON in `backend/.secrets/gcs-creatives-sa.json` (gitignored), mounted into the container at `/app/.secrets/` read-only via `docker-compose.yml`. Workload Identity deferred to Session 17 deploy.
- [x] Dropped `creative_url` and `creative_id` text inputs from the form — wizard threads them down to step 2 from upload state
- [x] No schema change to `models.Campaign` — existing `creative_url` + `creative_id` columns receive the upload result on submit

**Exit criteria met (2026-04-27):** uploaded a 1920×1080 JPG via the dashboard, wizard advanced to step 2 showing the thumbnail, returned URL opens publicly in a browser, campaign funded successfully through the full x402 flow with the GCS URL persisted on the row.

**Findings worth keeping:**
- **Auto-upload UX:** the original plan said "upload-on-next" — what shipped is "upload immediately on valid pick". The user already chose the file; a second confirmation click was friction. axios `onUploadProgress` gave a free progress bar (reuses the existing `.bar` class from CampaignCard). On localhost devnet uploads finish in one frame, so the bar usually flashes through to "Validating on server…" while Pillow + GCS finish.
- **Pillow `verify()` quirk:** `Image.verify()` invalidates the image instance, so we open the bytes twice — once for `verify()`, once for `.size`. Safe and cheap for 5MB max images. Documented inline in `routers/creatives.py`.
- **MIME spoofing:** browser-supplied `Content-Type` is not trusted on the server. Pillow's auto-detected `img.format` is the real check; the upload's MIME is only used to pick the URL extension. Both client and server enforce 1920×1080 + 5MB.
- **docker-compose mount:** `./backend/.secrets:/app/.secrets:ro` — `:ro` so a compromised app process can't overwrite credentials. Path inside the container is what `GCS_CREDENTIALS_JSON` points at.
- **Wizard structure:** `CreateCampaignForm.tsx` is now a thin shell that renders one of `wizard/Step{Image,Details}.tsx`. STEPS array drives the breadcrumb. Sessions 14 + 15 will add `StepTargeting`, `StepSchedule`, `StepCalculator`, and rename `StepDetails` → `StepReview`. Closing the New-campaign panel unmounts the wizard so all state (including in-flight upload) is discarded — matches the "no draft persistence" requirement.

**RUNBOOK additions:** new "Creative uploads (GCS)" section with the one-time provisioning CMD commands, `.env` lines, sanity-check curl, and SA-key rotation steps.

### Session 14 — DMA targeting + scheduling (Features 2 + 3 + 4)
- [ ] Mongo export: aggregation joining `screens` → `companies` (lookup by `companyId`), filter to the 6 target markets, project to flat `{device_id, venue_id, dma, venue_name}`. User runs the export and supplies the file as `backend/data/venues.json` (committed).
- [ ] DMA name canonicalization: confirm Mongo `market` codes (e.g. `"NY"` → `"New York"`); map to display labels at load time
- [ ] `Campaign.target_dmas` JSON column (NOT NULL — selection mandatory)
- [ ] `Campaign.start_date`, `Campaign.end_date` Date columns (UTC midnight resolution, day-only)
- [ ] In-memory venues index loaded at app startup: `dma → device_id[]` and `device_id → dma`
- [ ] `GET /api/markets` (Privy-JWT-authed) → `[{dma, display_count}, …]`
- [ ] `/bid` filter additions: bid request must carry `dma` (or `device_id` we resolve via the index); FIFO query gains `:dma = ANY(target_dmas) AND start_date <= today() <= end_date`
- [ ] Auto-play loop (`services/auto_play.py`) and `simulate_play` endpoint: pick a campaign first, then pick a random device whose DMA is in `target_dmas` so the demo always settles
- [ ] Status transition: `/bid` (or a periodic check) flips `active` campaigns whose `end_date < today` to `expired`. `expired` exposes the existing refund button.
- [ ] **Wizard Step 2 — Targeting**: 6 DMA cards (name + display count), click-to-toggle, live REACH = sum of selected, mandatory ≥1, hardcoded "Frequency per screen: 1 every 5 min" line below REACH
- [ ] **Wizard Step 3 — Schedule**: native `<input type="date">` for start + end; validation `start ≥ today`, `end ≥ start`

**Exit criteria:** advertiser selects 2 DMAs + a 3-day window, hits next, campaign creates with `target_dmas=[...]` + dates set; auto-play only fires for devices in those DMAs and only within the date window; a campaign whose `end_date` passed flips to `expired` on the next bid attempt and refund still works.

### Session 15 — Campaign calculator + protocol fee (Feature 5)
- [ ] **Wizard Step 4 — Calculator**: replaces budget+CPM free-text inputs with a derived summary (Screens, Frequency, Operating hours, Plays/day, Duration, Daily budget, Total campaign, Protocol fee 2.5%, **Total to escrow**)
- [ ] CPM locked via `DEMO_CPM` env (default `0.5` USD → $0.0005/play = 500 base units of USDC)
- [ ] Operating hours hardcoded constant (`12h` → 144 plays/screen/day at 5-min frequency)
- [ ] `Campaign.cpm` and `Campaign.budget` columns retained, populated with derived values on creation (no recompute in `/bid`)
- [ ] New `Campaign.protocol_fee_amount` column for accounting
- [ ] Protocol fee collected upfront: x402 settle pulls full `total + fee` into the campaign wallet, then a Privy `signAndSendTransaction` immediately moves the 2.5% to `PROTOCOL_REVENUE_WALLET_ADDRESS` (its own Privy server wallet, bootstrapped alongside treasury). Fee tx surfaces as its own Solscan link in the campaign detail panel.
- [ ] `FAUCET_AMOUNT_USDC` made tunable (default 10 dev, can crank to 30 for the recorded demo run)
- [ ] **Wizard Step 5 — Review & Fund**: shows calculator summary again with "Confirm and pay" — that's where the existing x402 settle lives; on success advances to a "campaign live" terminal step

**Exit criteria:** advertiser steps through the wizard, sees a non-zero `Protocol fee` line, hits Confirm, the x402 transfer pulls the full `total to escrow`, Solscan shows two txs from the campaign wallet (advertiser→campaign funding, then campaign→protocol-revenue fee).

### Session 16 — GCP deployment prep
- [ ] Cloud Run configs (backend)
- [ ] Cloud SQL Postgres migration from SQLite
- [ ] Secret Manager for Privy secret, JWT server secret, GCS credentials, Circle API key (when/if account upgrade lands)
- [ ] Cloud Storage + CDN for dashboard build (separate bucket from creatives)
- [ ] Workload Identity for the GCS creatives bucket so we drop the JSON service account key from prod

### Session 17 — Deploy to GCP
- [ ] Deploy backend to Cloud Run
- [ ] Deploy dashboard
- [ ] CORS, custom domain if time permits
- [ ] Smoke test on live devnet
- [ ] Move treasury topup cron (if Circle upgrade landed) from local Windows Task Scheduler to Cloud Scheduler + Cloud Function

### Session 18 — Demo rehearsal + submission
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
- **Demo-only endpoints/flags that must NOT ship to production (2026-04-22):**
  - `POST /api/campaigns/:id/simulate-play` — dashboard-only /proof driver (Session 10)
  - `AUTO_PLAY_ENABLED=true` — server-side auto-play loop (Session 11)
  - `/api/faucet` — treasury-funded USDC faucet for advertisers (Session 2)
  - `DEMO_PUBLISHER_WALLET` — hardcoded publisher address for the above
  All are currently conditionally enabled via settings but none is behind an `environment==dev` guard. **Before Session 12 deploy, wrap each in an `environment in {"dev","staging"}` check or drop from the prod router entirely.** Track as a pre-deploy checklist item.

## Must-fix before mainnet (known correctness issues accepted for the demo)

These are bugs we understand and are deferring with eyes open — at hackathon
scale (one concurrent user, few campaigns) they don't manifest. Before any
real-money deployment they MUST be fixed. Raised during a load-behavior
review 2026-04-22.

### 1. Budget overcommit at `/bid`
**Symptom:** `_pick_campaign` only requires `remaining >= cpm/1000` (budget
for one play). With a campaign whose budget covers 20 plays, N concurrent
`/bid` requests each get a valid `proof_context` JWT for the same campaign
regardless of N. We've minted N promises we can honor at most 20 of. If
publishers complete all N plays and call `/proof`, the extras get 400
`insufficient campaign budget` and write failed settlement rows. We've
effectively over-issued bid paperwork and dumped the problem on settle time.

**Fix:** reserve budget at `/bid`, release on `proof_context` TTL expiry.
Either (a) a `pending_bids` table with TTL + settlement cleanup, or
(b) a `reserved` column on `campaigns` that `/bid` atomically increments and
`/proof` decrements as it converts to `spent`. Option (b) is simpler if we
add a periodic sweep to un-reserve expired proof contexts.

### 2. Read-modify-write race on `campaigns.spent` in `execute_settlement`
**Symptom:** in `app/routers/proof.execute_settlement` we do:
```python
remaining = float(campaign.budget) - float(campaign.spent)
if remaining < claims.amount_usdc: raise 400
campaign.spent += claims.amount_usdc
db.commit()
```
Under real concurrency (multi-worker uvicorn, busy event loop) two `/proof`
requests on the same campaign can both read `spent=S`, both pass the guard,
both set `spent=S+Δ`, and last-write-wins — **one DB row, two on-chain
settlements**. Campaign wallet actually paid twice but we only charged it
once. Nonces are safe (unique-constraint insert) but the budget counter is
not.

**Fix:** atomic decrement with a guard clause, SQL-enforced:
```sql
UPDATE campaigns
SET    spent = spent + :amount
WHERE  id = :id
  AND  budget - spent >= :amount
RETURNING spent, budget
```
Reject if `rowcount == 0`. Single statement, safe under any isolation level.
Do this BEFORE the Privy transfer, not after.

### 3. Money is stored as `float`, not integer microUSDC
`campaigns.budget`, `campaigns.spent`, and the Python math throughout `/bid`
`/proof` and `auto_play` all use `float`. Summing `0.001` many times drifts
on the order of `1e-16` per step, so the "final play" guard can reject a
semantically-valid play and/or leave unplayable dust in a campaign. Current
fix (2026-04-22) is `+ 1e-9` epsilon tolerance on every budget guard AND
flipping `COMPLETED` when `remaining < cost_per_play` (not `spent >= budget`).
That works for demo scale but is band-aid on top of the real issue.

**Real fix:** store money as integer microUSDC (1 USDC = 1_000_000 units) in
both the DB (`Integer` columns) and Python. No floats anywhere in the money
path. Same 6-decimal precision the SPL token mint uses on-chain, and every
comparison becomes exact integer equality. Eliminates both the
precision-rejected play and the dust-limbo-ACTIVE states without needing
tolerance at all.

### 4. Smaller things (same review)
- **No per-publisher rate limiting** on `/bid` + `/proof`. One publisher can
  DoS the ad server; mitigate with `slowapi` + Redis or at the reverse-proxy
  layer.
- **No auction between campaigns.** FIFO means one campaign takes every bid
  until drained. Production wants weighted selection (CPM, pacing, targeting).
- **Single uvicorn worker in dev**. Deploy needs `--workers N` or gunicorn;
  fix #2 above is a prerequisite since multi-worker exposes the race.
- **`used_nonces` grows forever.** Fine at demo scale. Add retention (drop
  rows older than `proof_context_ttl_seconds + grace`) as part of the
  periodic sweep.

Filed for BUSINESS-CONSTRAINTS §7 (mainnet blockers) cross-reference.

---

## Open decisions still to resolve
- Alembic migrations vs `create_all` — skipping Alembic until Postgres in Session 12.
- Dashboard host port — pinning to 5173 locally; revisit for deploy.
- Rate limiting on `/api/faucet` — one shot per user per hour? Decide in Session 2.
- **Decoupling campaign-api from ad-server** (raised 2026-04-21, deferred). Three options sized: Option A = shared DB + two FastAPI apps (~1 session), Option B = independent DBs + internal HTTP (~2–3 sessions, adds network hop to bid path — risky for <500ms target), Option C = event-driven (~3–5 sessions, production-grade). Leaning Option A if we decide to do it; slot between Session 7 and Session 8.
- **SOL gas subsidy model — partially resolved by Session 9 findings, still open for production** (raised 2026-04-22 Session 7, updated 2026-04-22 Session 9). **For the advertiser-funding tx specifically**: resolved — x402-solana + x402.org forces facilitator-as-fee-payer (Config 2), so the advertiser needs zero SOL. x402.org's devnet facilitator sponsors gas for free. **Still open for campaign wallet ops** (`/proof` settlements, refunds): today the treasury seeds every new campaign wallet with 0.01 SOL (~$2 on mainnet) so it can pay its own fees. After refund, unused SOL is stranded. Options unchanged: **(A)** Privy fee sponsorship via `sponsor: true` on `sign_and_send_solana`; **(B)** keep subsidy + price into CPM; **(C)** move `/proof` settlement to a facilitator-like pattern. **Also now open for production of the funding flow**: public facilitators may charge or go away, so production likely needs us to run our own facilitator (Coinbase open-sourced Go + TS impls) and pay our own gas there. Decide before Session 13 (GCP deploy).

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
- **2026-04-22 (Session 8):** React dashboard scaffold — Vite + React 18 + TS under `frontend/`, Privy React SDK (Solana-only embedded wallets via nested `embeddedWallets.solana.createOnLogin` per Privy Vite docs), vite-plugin-node-polyfills for Buffer/process/global, React Query wired, Zustand installed (no stores yet). Backend CORSMiddleware added, exposes `X-PAYMENT-RESPONSE`. Auth gate → Login ↔ Home. Verified in browser: email OTP → Home with live `/health` response. Branding corrected to "Advertiser Dashboard" with "demo — third-party advertiser view" subtitle.
- **2026-04-22 (Session 9 start):** `WalletPanel` implemented — `/api/wallet` query with 400/404 retry for fresh-signup server-side link lag, pulsing "inbound +X USDC, confirming on devnet" indicator that clears when the new balance lands, fallback "Create Solana wallet" button via `useSolanaWallets().createWallet()` for users whose account predates the corrected Solana-only config. Bug fix: `/api/faucet` reference_id now has a uuid suffix — Privy's `reference_id` is validated post-broadcast (duplicate keys still broadcast the tx then error with `invalid_data` at record time), so without the suffix every click after the first returned 502 despite the transfer succeeding. Documented in `BUSINESS-CONSTRAINTS.md §3` and §7 blocker #14 ("Retry safety for non-idempotent on-chain operations"). Comment in `services/privy.py` clarifies why the existing retry loop is still safe (narrow to `transaction_broadcast_failure` which means broadcast did not happen).
- **2026-04-22 (Session 9 close):** Campaign funding flow shipped end-to-end. `<CreateCampaignForm>` + PayAI's `x402-solana@^2.0.4` auto-handshake against our existing backend. Path getting there cost four trips through the facilitator; each fix documented in Session 9 block above: (1) destination USDC ATA must be pre-created server-side → `build_campaign_bootstrap_tx` bundles SOL seed + ATA create, must confirm before returning 402; (2) x402.org v1 facilitator entry is `solana-devnet`, not CAIP-2; (3) `x402.org/facilitator` 308-redirects to `www.`; (4) `extra.feePayer` must be facilitator's address (Config 2 is the only working path on this stack) — fetched from `/supported` + cached in `get_facilitator_fee_payer()`. Advertiser-SOL-seed branch removed (facilitator pays gas). `lib/walletTrack.ts` shared Zustand store drives `WalletPanel` polling after any money-moving mutation so the debit lands visibly within 2–4s. E2E script (`scripts/e2e_demo.py`) unchanged — still 13/13 on the path that bypasses `/api/campaigns`.
- **2026-04-22 (Session 10):** Dashboard play + refund flows shipped. Refactored `/proof` to extract `execute_settlement()` as a shared helper; new `POST /api/campaigns/:id/simulate-play` endpoint (advertiser-authed) mints claims server-side and reuses the pipeline so the dashboard can drive the full loop without exposing the publisher API key. Frontend: campaigns now render as a list via new `<CampaignsPanel>` + expandable `<CampaignCard>` — status badges, spent/budget progress bar, per-status actions (simulate/pause/resume/refund), Solscan-linked settlements. `walletTrack.startPolling` is triggered on refund success alongside the existing fund flow. Verified in browser on devnet: create → simulate plays tick up spent + add settlement rows → pause → refund sends remaining USDC back, wallet balance ticks up within a few seconds.
- **2026-04-22 (Session 11):** Integration polish. `lib/errors.humanizeError()` extracts FastAPI `{detail}` payloads from axios errors and our manual x402 throws; now used across every error display. `CreateCampaignForm` reads the cached wallet query and guards against insufficient-balance submits before reaching the Privy signing popup. Funding progress moved from two stages (with one dead) to three accurate ones via `customFetch` instrumentation on the x402 client. **Demo auto-play**: `app/services/auto_play.py` runs in the FastAPI lifespan when `AUTO_PLAY_ENABLED=true`, ticking every `AUTO_PLAY_INTERVAL_SECONDS` to pick a random active + funded campaign and run `execute_settlement` against `DEMO_PUBLISHER_WALLET`. New public `GET /api/auto-play-status` endpoint drives a pulsing "Auto-simulating…" badge on the dashboard + conditional `refetchInterval` on the campaigns list + expanded stats. Added to .env.example (default off) and to the "demo-only flags MUST NOT ship to prod" list under Resolved decisions.
- **2026-04-24 (design + planning, no code):** Pre-deploy feature scope pinned. Five product features added to roadmap before GCP work: (1) creative image upload to public GCS bucket (`x402-adserver-creatives`), replacing free-text creative URL input; (2) campaign-create wizard refactor with DMA targeting cards (REACH = live sum of selected display counts), filtering bids on selected markets; (3) hardcoded "1 every 5 min" frequency line under REACH; (4) start/end date scheduling step with `expired` status auto-transition when `end_date < today`; (5) derived budget calculator replacing budget+CPM free-text inputs, locked CPM via `DEMO_CPM` env, 2.5% protocol fee charged upfront via separate Privy `PROTOCOL_REVENUE_WALLET`. Demo math constraint: total-to-escrow must fit Circle faucet rate (20 USDC / 2h per address), locking demo CPM at $0.50 and demo configs to 1–3 DMAs / 2–7 days (~$15–20 typical, ~$232 worst-case at 6 DMAs × 7 days). Treasury topup probe: `POST https://api.circle.com/v1/faucet/drips` returns HTTP 403 for sandbox keys (`{"code":3,"message":"Forbidden"}`), confirming the docs note about "upgrading to mainnet" is a real account-level gate. Decided fallback: 3 helper Privy server wallets, manual web-faucet claim per address, `scripts/sweep_helpers.py` consolidates to treasury. Sessions 12–15 inserted before existing GCP block; old 12/13/14 renumbered to 16/17/18. `BUSINESS-CONSTRAINTS.md` updated: Circle multi-wallet workaround in §3, demo-CPM lock + protocol fee model in §6, creative hosting + inventory transparency in §5, content moderation pre-mainnet blocker as §7.16.
- **2026-04-22 (Session 7):** Integration + hardening. `scripts/e2e_demo.py` exercises the full loop against real devnet via in-process ASGI (13/13 steps pass); covers happy path, replay 409, expired 400, paused no-bid, budget-exhaust auto-complete, double-refund guard. Retry stub (`services/retry.py` + `scripts/retry_settlements.py`) drains failed `settlements` rows. Discovered and fixed: (a) `get_usdc_balance` crashed on solana-py's `InvalidParamsMessage` error responses, (b) fresh Privy campaign wallets ended up with 0 SOL (devnet airdrop unreliable) so /proof + refund couldn't pay fees — now SOL-seeded from treasury via `build_sol_transfer_tx`, (c) Privy's simulation RPC lags devnet by 10–60s for new ATAs — added exponential-backoff retry keyed on `transaction_broadcast_failure` inside `sign_and_send_solana`. Structured logging (`logger.exception`) added at every Privy/facilitator boundary.
- **2026-04-27 (Session 13):** Wizard shell + creative upload (Feature 1) shipped. Backend: new `app/services/gcs.py` (lazy storage client; service-account creds loaded from `GCS_CREDENTIALS_JSON` path, cached via `functools.lru_cache`) + `app/routers/creatives.py` (`POST /api/creatives`, advertiser-authed multipart, re-validates dimensions + format with Pillow, rejects non-JPG/PNG and non-1920×1080, 5 MB ceiling — all via `creative_*` settings on the config). Wired into `app.main`. New deps: `Pillow`, `google-cloud-storage`, `python-multipart`. Frontend: `CreateCampaignForm.tsx` rebuilt as a thin wizard shell that delegates to `components/wizard/StepImage.tsx` + `StepDetails.tsx`; STEPS array drives the breadcrumb so future sessions just append. StepImage validates with the browser's `Image()` decoder before upload, then auto-uploads (no separate confirm-click) with an axios `onUploadProgress`-driven progress bar reusing the existing `.bar` styles. StepDetails is the previous fund flow with the creative thumbnail rendered above + a "Back" button. GCP setup: project `x402-494608`, bucket `gs://x402-adserver-creatives` (UBLA + `allUsers:objectViewer`), dedicated service account `x402-creatives-uploader` bound to `roles/storage.objectCreator` on the bucket only (least privilege). SA JSON lives at `backend/.secrets/gcs-creatives-sa.json` (gitignored), mounted into the container `:ro`. End-to-end: upload → preview → fund flow runs unchanged. **Skipped this session per business constraints §7.16:** content moderation — pre-mainnet blocker, out of scope for hackathon.
- **2026-04-27 (Session 12):** Treasury topup helpers shipped. Manual experiment confirmed Circle's per-address rate limit is real (claim into helper + immediate claim into treasury from same browser → both succeeded). New `scripts/bootstrap_helpers.py` creates N Privy server wallets and treasury-seeds each with 0.01 SOL via `build_sol_transfer_tx` + `wait_for_tx_confirmation` (the RPC-airdrop path silently fails the same way it does for campaign wallets, so we don't even try). New `scripts/sweep_helpers.py` reads zipped `HELPER_WALLET_IDS` / `HELPER_WALLET_ADDRESSES`, sweeps any non-zero helper to treasury, plus `--wallet-id` + `--wallet-address` rescue mode for one-offs. Used the rescue mode to recover 20 USDC from the throwaway helper created by `create_helper_wallet.py` during the manual probe. End-to-end verified: 4 helpers (3 bootstrap + 1 rescued) → 4 × Circle web-faucet claims → one `sweep_helpers.py` run consolidated 80 USDC to treasury with 4 Solscan tx hashes. **Reference-id length gotcha**: Privy's 64-char cap meant the first sweep failed with `invalid_data` — full uuid4 string suffix was 68 chars. Codebase convention is `uuid4().hex[:8]`, kept that in both new scripts. RUNBOOK has the daily-routine click sequence + rescue command.
