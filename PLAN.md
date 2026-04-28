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
- [x] Service account JSON in `backend/.secrets/gcs-creatives-sa.json` (gitignored), mounted into the container at `/app/.secrets/` read-only via `docker-compose.yml`. Workload Identity deferred to Session 18 deploy.
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

### Session 14 — DMA targeting + scheduling (Features 2 + 3 + 4) ✅

- [x] Mongo export → `backend/data/venues.json` (gitignored; user supplies on each dev environment. 622 rows, 612 with valid DMAs across the 6 target markets)
- [x] DMA name canonicalization: lowercase Mongo codes → display labels (`ny`/`la`/`sf`/`mia`/`bos`/`aus` → `New York`/`Los Angeles`/`San Francisco`/`Miami`/`Boston`/`Austin`)
- [x] `Campaign.target_dmas` JSON column (nullable on the column for the dev-SQLite ALTER, mandatory ≥1 in `CreateCampaignRequest`)
- [x] `Campaign.start_date`, `Campaign.end_date` Date columns (UTC midnight, day-only)
- [x] In-memory venues index (`services/venues.VenuesIndex`) — `dma → device_id[]`, `device_id → dma`, `display_counts`, `pick_random_device(labels)`
- [x] `GET /api/markets` (Privy-authed) → `[{dma, display_count}, …]`
- [x] `/bid` filter: requires `imp.ext.device_id`; resolves to DMA via index; FIFO gains target_dmas membership + schedule window check; lazy-flips `active`→`expired` when `end_date < today`
- [x] Auto-play + simulate-play pick a campaign first, then a random device whose DMA matches; both also enforce the schedule window
- [x] `CampaignStatus.EXPIRED` added; refund button accepts it; double-refund guard already covers it
- [x] Wizard Step 2 — Targeting (DMA cards w/ live REACH + hardcoded frequency line)
- [x] Wizard Step 3 — Schedule (native date pickers, today-min, end ≥ start)

**Exit criteria met (2026-04-27):** E2E (`scripts/e2e_demo.py`) → 13/13 on real devnet with the new bid contract (campaigns target `San Francisco`, bid payload carries `imp.ext.device_id` from venues.json). OpenAPI shows `target_dmas`/`start_date`/`end_date` on `CreateCampaignRequest` + `CampaignSummary` and `MarketInfo` on `/api/markets`. Frontend `tsc --noEmit` clean. `expired` flip + refund verified by inspection of the `_pick_campaign` sweep path.

**Findings worth keeping:**

- **Mongo type mismatch on the join.** `screens.companyId` is a string, `companies._id` is an ObjectId. Compass `$lookup` with plain `localField`/`foreignField` returned zero matches. Fix: rewrite as `let` + `pipeline` with `$expr: { $eq: [ { $toString: "$_id" }, "$$cid" ] }`. The aggregation lives in PLAN session prompt history — re-derive from there if a future export needs to be refreshed.
- **DMA codes are Mongo lowercase short forms** (`ny`, `mia`, `aus`), not full names. `services/venues.DMA_LABELS` is the single canonicalization map; the wizard, `/api/markets`, `Campaign.target_dmas`, and the `/bid` filter all use the display labels (`"New York"`, …) so the user never sees the raw codes. 10 admin/test rows have empty `dma` (e.g. venue_name `"root"`, `"shaw"`) and are dropped at load time with an info log.
- **Docker volume swap.** The dev SQLite DB used to live in a named `backend_data` volume. Bind-mounted `./backend/data:/app/data` so the user-supplied `venues.json` is visible inside the container alongside the dev DB. The whole `backend/data/` dir stays gitignored — `venues.json` is publisher-private inventory data (specific venue names + addresses), not safe to commit. Existing DB was preserved via `docker cp` before the swap; no data loss. **For deployments + onboarding new dev environments**, the venues file must be re-provisioned per Compass-export instructions captured in this session's prompt history (Mongo `$lookup` with `let` + `pipeline` to handle the string/ObjectId join).
- **Dev-only column add for SQLite.** `create_all` is no-op on existing tables. Added `_dev_alter_table_for_existing_sqlite()` in `database.py` that runs after `create_all`, reads `PRAGMA table_info(campaigns)`, and `ALTER TABLE` for any missing columns. SQLite-only, idempotent, drop-able when we move to Postgres + Alembic in Session 17. Without this, every column-adding session would force a volume reset.
- **Auto-play vs E2E timing.** The lifespan launches the auto-play loop unconditionally (gated on `AUTO_PLAY_ENABLED` inside the loop). When the user has the flag enabled in `.env`, `docker compose run` for the e2e starts a fresh container whose lifespan also runs the loop; if it ticks during the e2e's bid → proof retry window (~7s of Privy backoff for a fresh ATA), the test campaign gets a phantom play and `spent` doubles. Fix: `os.environ["AUTO_PLAY_ENABLED"] = "false"` at the top of `scripts/e2e_demo.py` — pydantic-settings precedence is process-env over `.env` file, so this lands before `get_settings()` is called.
- **Venue name is publisher-private.** `pick_random_device` returns `{device_id, venue_name, dma}` for server-side logging (auto-play prints which venue settled), but `SimulatePlayResponse` only exposes `dma` to the dashboard. `venue_name` identifies a specific publisher partner ("2211 Club, LLC") and isn't safe to surface to advertisers — comment in `schemas.SimulatePlayResponse` calls this out so a future change doesn't accidentally leak it.
- **`/bid` lazy expired flip.** Rather than a periodic sweep job, `_pick_campaign` walks active campaigns once per bid; any with `end_date < today` get flipped to `EXPIRED` in the same pass. Cheap because the candidate list is small (single-digit campaigns at demo scale) and avoids a separate cron. If the campaign list grows, a daily background sweep is the obvious next step.
- **Refund now accepts `expired`.** The existing refund flow already declined `active` (must pause first) and `refunded` (already done). Added `EXPIRED` to the allowed-source set; `canRefund` on `CampaignCard` mirrors it. Same on-chain path as completed/paused refunds — campaign-wallet→advertiser-wallet USDC transfer signed by the campaign's Privy server wallet.

**Demo publisher inventory** (`backend/data/venues.json`, exported 2026-04-27):

| DMA           | Code | Screens |
| ------------- | ---- | ------- |
| New York      | ny   | 198     |
| Los Angeles   | la   | 160     |
| San Francisco | sf   | 115     |
| Miami         | mia  | 51      |
| Boston        | bos  | 48      |
| Austin        | aus  | 40      |
| **Total**     |      | **612** |

10 rows skipped at load (admin/test entries with empty `market`).

### Session 15 — Campaign calculator + protocol fee (Feature 5) ✅

- [x] `services/calc.compute_quote()` — single source of truth for the budget breakdown (`screens`, `plays_per_screen_per_day`, `days`, `total_plays`, `cpm_price`, `total_usdc`, `protocol_fee_pct`, `protocol_fee_usdc`, `total_to_escrow_usdc`). Reads screen counts from the venues index, CPM from `DEMO_CPM`, frequency from `OPERATING_HOURS_PER_DAY * PLAYS_PER_HOUR_PER_SCREEN`.
- [x] `POST /api/campaigns/quote` (Privy-authed) — wizard hits this on Step 4 and renders whatever it returns. `POST /api/campaigns` runs the same `compute_quote` server-side to derive the actual escrow amount, so the dashboard preview always matches what gets charged.
- [x] CPM locked via `DEMO_CPM` (default 0.5 USD → $0.0005/play). Operating hours + plays/hour as separate settings (`OPERATING_HOURS_PER_DAY=12`, `PLAYS_PER_HOUR_PER_SCREEN=12` → 144 plays/screen/day, one every 5 min).
- [x] `CreateCampaignRequest` shrunk to `{name, creative_url, creative_id, target_dmas, start_date, end_date}`. Server populates `cpm_price = DEMO_CPM`, `budget = quote.total_usdc`, `duration = 15` (default spot length), `protocol_fee_amount = quote.protocol_fee_usdc` on the campaign row.
- [x] `Campaign.protocol_fee_amount` (Numeric) + `Campaign.protocol_fee_tx_hash` (String) added; dev SQLite ALTER carries them on existing tables.
- [x] Protocol fee collected upfront: x402 settle pulls full `total + fee` into the campaign wallet; immediately after settle confirms, a Privy `signAndSendTransaction` moves the 2.5% to `PROTOCOL_REVENUE_WALLET_ADDRESS`. Best-effort — failure logs at exception level + leaves `protocol_fee_tx_hash=null` but the campaign still flips ACTIVE (fee stays in the campaign wallet, refunded with the rest if the campaign is refunded).
- [x] `scripts/bootstrap_protocol_revenue.py` — mirrors `bootstrap_treasury.py`. Idempotent via `PROTOCOL_REVENUE_WALLET_ID` env check.
- [x] Wizard now 5 steps: Image → Targeting → Schedule → Budget (calculator, server-derived) → Review & Fund. `StepCalculator` calls `/quote`; `StepReview` takes the quote object as a prop, shows the same numbers read-only with a Confirm & Fund button. No budget/CPM/duration inputs anywhere in the form.
- [x] `CampaignCard` surfaces `Protocol fee` line in the kv block + Solscan link to the fee tx.

**Exit criteria met (2026-04-27):** OpenAPI shows `CreateCampaignRequest` without budget/cpm*price/duration, `QuoteRequest`/`QuoteResponse` registered, `CampaignSummary` carries `protocol_fee*\*` fields. Calc verified in-container: SF (115) + BOS (48) = 163 screens × 144 × 4 days × $0.0005 = $46.944 total, $1.1736 fee, $48.1176 escrow. E2E (`scripts/e2e_demo.py`) → 13/13 on real devnet (must `docker compose stop backend`first or the long-running container's auto-play double-counts spent — documented inline + in this session's log entry). Frontend`tsc --noEmit` clean. **Browser walkthrough still pending — user is verifying in the dashboard now.**

**User action required before testing the new fund flow end-to-end:**

1. `docker compose run --rm backend python scripts/bootstrap_protocol_revenue.py` — creates the wallet, prints env vars
2. Paste `PROTOCOL_REVENUE_WALLET_ID=…` and `PROTOCOL_REVENUE_WALLET_ADDRESS=…` into `backend/.env`
3. `docker compose restart backend`
4. Run through the wizard: pick a creative, 1–2 DMAs, ~3-day window. Step 4 should show the live calculator. Step 5 confirm should fire two on-chain transactions visible from the campaign card: (a) advertiser → campaign wallet funding tx, (b) campaign wallet → protocol-revenue fee tx.

**Findings worth keeping:**

- **Why server-side compute, not client-side.** Initial sketch had the wizard compute the budget in JS and send it to POST. We rejected that — `screens` come from the server-side venues index, `CPM` is locked server-side, and `protocol_fee_pct` is a server constant. The advertiser only owns three small inputs (target_dmas, start_date, end_date) — handing the budget number to the client adds a tampering surface for nothing. New `/quote` endpoint + same `compute_quote` running on POST keeps a single source of truth.
- **Quote signature reproducibility on the x402 retry.** The first POST returns 402 with a `PaymentRequirements` blob whose `amount_usdc` is the calculator's `total_to_escrow`. The client signs that blob; on the retry POST (with `X-PAYMENT`), the server has to reproduce the same `amount_usdc` so the facilitator's `/verify` matches. We persist `budget` (= total_usdc) and `protocol_fee_amount` separately; on retry, we sum them: `escrow_amount = float(campaign.budget) + float(campaign.protocol_fee_amount or 0)`. Float math is exact for the round-to-6-decimals values we store.
- **Best-effort fee transfer, not blocking.** The fee transfer happens AFTER `/settle` confirms — by then the campaign wallet already holds `budget + fee` and the advertiser has paid. If the fee transfer fails for any reason (Privy hiccup, RPC lag, etc.) we log + leave `protocol_fee_tx_hash=null` but still flip the campaign to ACTIVE. The fee just stays in the campaign wallet. Refund returns the full `budget - spent` plus any leftover fee — the advertiser doesn't lose anything; we lose 2.5% revenue we'd otherwise have collected. Acceptable for hackathon scope; production wants a retry queue keyed on `protocol_fee_tx_hash IS NULL`.
- **Why `budget` is the playable amount, not the total escrow.** `/bid` and `/proof` use `budget - spent` to gate plays. If we stored `budget = total_to_escrow` (i.e. including the fee), every play's budget check would be off by 2.5%. Storing `budget = total_usdc` (the playable amount) keeps the play-gating math unchanged from Session 14; the fee is just a separate transfer that happens at activation time and doesn't enter the play accounting.
- **`Campaign.duration` retained on the model.** The publisher contract embeds `ext.duration` on the bid response (the spot length in seconds). Dropped it from the wizard input since the user said it isn't user-configurable, but kept the column with a 15s default so the bid response shape is unchanged. Future product change: derive duration from creative metadata (Pillow already gets us the file's properties on upload).
- **5% slack on the x402 client `amount`.** Carried over from Session 9. The signed amount is the _cap_; the actual charge is whatever the server's PaymentRequirements specify. The slack covers tiny rounding/timing drift between the wizard's quote and the server-side recompute on the POST. In practice the two compute paths produce bit-identical numbers, but the slack costs nothing and means we'll never accidentally reject a valid signature.
- **E2E still 13/13, but `docker compose stop backend` is now mandatory before running it.** With AUTO_PLAY_ENABLED=true in the demo `.env`, the long-running container has its own auto-play loop hitting the same SQLite DB through the bind mount. The e2e's `os.environ["AUTO_PLAY_ENABLED"] = "false"` override only mutes the lifespan inside the e2e's own container — the long-running container is unaffected and can tick once during the e2e's bid → proof retry window, double-counting `spent`. Docstring + Run instructions updated in `scripts/e2e_demo.py`.
- **Frontend wizard wiring.** State management stays trivial — `CreateCampaignForm` holds five `useState` slots (creative, targeting, schedule, quote, step) and threads them into the appropriate child. No state machine library, no shared store; the wizard form is short-lived (mounted only when the panel is open), and closing the panel discards everything per the no-draft-persistence requirement from Session 13. `StepCalculator` keys its `useQuery` on a sorted-joined DMA string + dates so back-edits invalidate the cached quote correctly.

### Session 16 — Frontend facelift (design implementation) ✅

- [x] `frontend/src/styles/tokens.css` dropped in + imported from `main.tsx` before legacy `styles.css`. Body root gets `data-theme="dark" data-type="geometric"`; Geist + Geist Mono loaded from Google Fonts. Legacy `styles.css` shrunk to a baseline (body bg, link, disabled-button) — every other class deleted.
- [x] Primitives ported to `frontend/src/components/ui/`: `Icon.tsx` (full path map + `chevronLeft` added later for the wizard back button — design's source had it pointing down), `StatusBadge.tsx`, `Sparkline.tsx` (per-mount unique gradient ids so multiple sparklines on a page don't collide), `Progress.tsx`, `StatCard.tsx`, `Solscan.tsx`, `X402Mark.tsx`, `CreativeThumb.tsx` (deterministic gradient seeded by `campaign.id` per locked decision #3).
- [x] App shell: `AppHeader.tsx` (logo + DOOH protocol subtitle + Solana·devnet pill + wallet chip), `TabRow.tsx`, `WalletChip.tsx` (collapsed pill + dropdown w/ copy address, faucet CTA, low-balance pulse, pending-faucet indicator, fallback "Create Solana wallet" button). `App.tsx` is now header + tabs + active-tab content + wizard portal.
- [x] `pages/Overview.tsx` — stat grid + status breakdown + activity feed + empty + loading skeletons.
- [x] `pages/Campaigns.tsx` + new `components/CampaignCard.tsx` — expandable list. Collapsed row shows thumb + name + status badge + targeting summary + spent/budget bar + plays count. Expanded shows 6-stat grid, target DMA chips, last-play indicator, recent settlements table, status-aware action buttons.
- [x] Wizard ported into a modal shell (`components/wizard/Modal.tsx` with `StepDots` + `Footer` + `Lbl` helpers). Each of the 5 steps (`StepImage`, `StepTargeting`, `StepSchedule`, `StepCalculator`, `StepReview`) restyled inside it; ESC + click-outside dismiss with a mid-flow confirm prompt; funding-progress sub-state and success state with both Solscan tx links + Done button.
- [x] Cleanup: `WalletPanel.tsx`, `CampaignsPanel.tsx`, pre-restyle `CampaignCard.tsx`, pre-restyle `CreateCampaignForm.tsx`, `pages/Home.tsx` all deleted. Login restyled in tokens. `subform`/`campaign-card`/`badge-*`/`pulse`/`bar`/etc legacy classes purged from `styles.css`.
- [x] `tsc --noEmit` clean.

**Mid-session expansions (not in the original Session 16 plan but bundled because they were either bugs surfaced by the new UI or natural follow-ons):**

- [x] **Session 16.5 — Performance + correctness pass.** Replaced Overview's N-fan-out per-campaign /stats polling with a single new `GET /api/dashboard-summary` endpoint (`backend/app/routers/dashboard.py`). Returns server-aggregated `total_plays` + `last_24h_plays` (one COUNT each) + cross-campaign top-10 settlements with `campaign_name` joined in. Cuts Overview's poll budget to 2 req/5s regardless of campaign count.
- [x] **Always-poll on Overview/Campaigns/expanded card.** Removed the `autoPlay.enabled` gate on `refetchInterval` — plays can come from auto-play, simulate-play, or real publisher /proof, and the gate caused the live counters to freeze when `AUTO_PLAY_ENABLED=false`. Fixed 5s tick on all three; tightens to the auto-play interval when shorter.
- [x] **`last_24h_plays` field on stats** (was previously derived from `recent_settlements` which is server-capped at 10/campaign — counter would plateau at ~30-40 once each campaign had 10+ plays in 24h). Server-side `COUNT(*)` is exact.
- [x] **UTC timezone fix on settlement `created_at`.** SQLite drops tzinfo on read even with `DateTime(timezone=True)`; naive ISO strings on the wire get parsed as local by the browser. `_to_settlement_summary` now stamps `tzinfo=timezone.utc` before `isoformat()` (matched in `dashboard.py`). Fixed "3h ago" appearing on fresh rows.
- [x] **Date picker fix.** Original styled box layered an `opacity:0` native `<input type="date">` over a div; modern Chrome only opens the picker on calendar-icon clicks, not arbitrary overlay clicks. `StepSchedule` now uses a real `<button>` for the styled box and triggers `inputRef.current.showPicker()` programmatically. Visually-hidden input retains form-state semantics.
- [x] **Row-flash animation for new activity.** `tokens.css` got an `.x-row-flash` keyframe (1.8s teal fade). New `useFlashOnArrival(ids)` hook in Overview tracks previously-seen IDs in a ref, skips the first non-empty render so existing rows don't all flash on mount, and clears the flash set after the animation duration so re-renders don't re-trigger.
- [x] **Wizard "Done" → Campaigns tab + auto-expand.** `StepReview` exposes `onDone(campaign)`; `App.tsx` sets `highlightId` and switches tab; `Campaigns.tsx` `useEffect` syncs `highlightId` into local `expanded` state.
- [x] **PLAN's must-fix #2 (race condition on `campaigns.spent`) closed.** `execute_settlement` now does a single atomic `UPDATE campaigns SET spent = spent + :amt, status = CASE WHEN ... THEN 'completed' ELSE status END WHERE id = :id AND status = 'active' AND budget - spent + 1e-9 >= :amt`. Two concurrent calls cannot both pass; rowcount=0 → disambiguate via follow-up read for proper 4xx error. Updated PLAN's must-fix list below to reflect resolution.
- [x] **Compensating refund on Privy failure.** Forward UPDATE reserves budget; on `PrivyError`/exception we run a compensating UPDATE that decrements `spent` back and flips `status` from COMPLETED→ACTIVE if the refund creates room for one more play. Nonce stays consumed (replay protection holds). Failed plays no longer burn budget.
- [x] **Memo on USDC transfers** (`backend/app/services/solana.py`). Concurrent settlements with identical (from, to, amount) within one blockhash window were producing identical tx bytes → Solana network dedup → 10 plays burning 10 budget rows but only 1 actual on-chain transfer. `build_usdc_transfer_tx` now accepts a `memo` arg; `execute_settlement` passes `memo=f"x402:{nonce}"` so each tx is bytes-unique. SPL Memo Program v2 ID is case-sensitive: `MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr` (uppercase X).
- [x] **Multi-play per tick + randomization.** `auto_play._tick` now fires `random.randint(min, max)` settlements concurrently per tick (`AUTO_PLAY_PLAYS_PER_TICK_MIN`/`_MAX` settings). Each task opens its own DB session for safe concurrent writes. Connection pool bumped to `pool_size=30, max_overflow=60, pool_timeout=60` — defaults (5+10) starved within one tick because every settlement holds a session through its ~5–10s Privy await.
- [x] **device_id end-to-end.** Added optional `device_id` to `ProofContextClaims`; `/bid` extracts from `imp.ext.device_id` and threads through the JWT; `/proof`, simulate-play, auto-play all persist on the new `Settlement.device_id` column (dev SQLite ALTER carries it). `SettlementSummary` and `DashboardActivityRow` resolve `device_id → dma` server-side via the venues index. Dashboard's "Last play" + Overview's activity feed now show DMA. Publisher integration unchanged — JWT is opaque to them, schema is identical.
- [x] **Decimal display.** Spent / budget / remaining bumped to 4dp on Overview totals and on the campaign card (collapsed + expanded + budget bar) — 2dp was hiding the per-play tick.

**Verified live (2026-04-27):** browser walk login → Overview shows live aggregates → wizard funds a real devnet campaign through 5 steps → success state surfaces both Solscan links → Done navigates to Campaigns with the new card auto-expanded → auto-play settles 10–20 plays/15s with distinct tx hashes and DMA labels populated. E2E (`scripts/e2e_demo.py`) → 13/13 with the standard `docker compose stop backend` ritual (auto-play burst is now even more disruptive — see RUNBOOK).

### Session 16.7 — Per-campaign live activity map (demo polish) ✅

Eye-candy addition for the demo. **Per-campaign**, lives inside the expanded
`CampaignCard` (between the stats grid and the recent settlements table), not
on Overview. Visualizes plays as they land on the DMAs the campaign targets,
with a count-up tween on each marker so the auto-play batch (10–20 plays/tick)
is visible as a synchronized number-tick across whichever cities got hit.

- [x] Frontend: `react-leaflet@^4.2.1` + `leaflet@^1.9.4`, Carto Dark Matter
      tiles (free, no API key, OSM + CARTO attribution kept on).
- [x] Map is fully non-interactive (`dragging`, `scrollWheelZoom`,
      `doubleClickZoom`, `touchZoom`, `boxZoom`, `keyboard`, `zoomControl` all
      off). `FitOnMount` child uses `useMap()` + `fitBounds(centers, padding)`
      on first render only; initial center is a continental-US default + zoom
      3, immediately overridden by `fitBounds`. View frozen thereafter.
- [x] Pins: `L.divIcon` per DMA in `campaign.target_dmas` (1–6). Hardcoded
      centroid lat/lon in `frontend/src/lib/dmaCentroids.ts`. Pin styling in
      `tokens.css` (`.x-map-pin*`) — teal-cyan gradient pill, anchored above
      the centroid via `translate(-50%, -100%)`.
- [x] Count-up tween: `frontend/src/lib/useCountUp.ts`, rAF + ease-out
      cubic. **1000 ms** (default 600 was too short — single-digit deltas
      blew through it before the eye caught the change).
- [x] Punch animation on real count change (added late-session): scale
      1 → 1.28 → 1 with `cubic-bezier(0.34, 1.56, 0.64, 1)` over 550 ms,
      triggered only when the _server_ count changes, not on every tween
      frame. See findings below for why this needed an architectural
      rethink.
- [x] Backend cleanup (folds in BACKEND-REVIEW.md §1.6):
  - SQL aggregates replace `.all()` + Python `len()/sum()` in
    `campaign_stats` — `func.count()` + `func.coalesce(func.sum(...), 0)`
    in one query.
  - `plays_by_dma: dict[str, int]` on `CampaignStats`. SQL `GROUP BY
device_id` (NULL excluded), resolved via
    `get_venues_index().label_for_device`; unmapped device_ids bucket
    under `"Unknown"`.
  - Lifetime totals, no time cutoff — confirmed monotonic-up across
    active/paused/completed/expired/refunded. `coalesce` handles
    zero-row sums.
  - **Sequencing followed:** SQL cleanup → e2e (13/13) → `plays_by_dma`
    layered → e2e (13/13 again) → frontend.

**Acceptance met (2026-04-28):** browser walk on a campaign targeting NY +
SF showed 2 markers; with `AUTO_PLAY_ENABLED=true` markers ticked up in
sync with the activity feed flash, each delta producing exactly one
punch per affected DMA. Backend e2e 13/13 on real devnet, both before
and after the schema add. tsc `--noEmit` clean.

**Findings worth keeping:**

- **divIcon HTML rebuild kills CSS animations.** First implementation
  rebuilt the divIcon on every `useCountUp` frame (`useMemo` keyed on
  `display`). Leaflet replaces the entire DOM node when the icon prop
  changes, so any `animation:` on the inner element resets ~60×/s — a
  CSS punch fired on count change would either retrigger every frame
  during the tween (nonsense) or never settle (also nonsense). Fix:
  build the divIcon once per DMA (keyed on `dma`, not `display`),
  then update the count text and trigger the punch class imperatively
  via `markerRef.current?.getElement().querySelector(...)`. Counter
  ticks update text content; punch toggles a class with a forced reflow
  (`void inner.offsetWidth`) so the animation restarts cleanly even if
  the previous one hasn't finished. Pattern reusable for any future
  leaflet divIcon work.
- **600 ms count-up tween is invisible on small deltas.** Tween length
  matters less than the pop. Visual evidence of "something changed"
  comes from the punch (scale + glow), not the number tick. With the
  punch in place 1000 ms reads naturally; without it, even 1500 ms
  felt anaemic.
- **Continuous-US default center prevents leaflet zero-area-bounds
  edge case.** First impl passed `bounds={L.latLngBounds(centers)}` to
  `<MapContainer>`; with a single targeted DMA the bounds collapsed to
  a zero-area box and leaflet either threw or zoomed to max. Switched
  to `center` + `zoom` initial props (continental US, zoom 3) and
  `FitOnMount` runs `setView(center, 5)` for 1-DMA campaigns,
  `fitBounds` for 2+. No flash on render; the default zoom is small
  enough that the snap-to-fit looks intentional.
- **Pre-existing dead import in `pages/Campaigns.tsx`** (`StatusBadge`)
  was failing tsc — Session 16's "tsc clean" check used a slightly
  different command. Dropped as part of this commit since it was
  blocking the typecheck for any frontend work.

**Why DMA-level not venue-precise:** venue identity is publisher-private
per Session 14 findings (`venue_name identifies a specific publisher
partner`). DMA-level pins reveal nothing the advertiser doesn't already see
on the targeting chips, so this stays inside the existing privacy
boundary. Venue-precise pins are an upgrade path that would also need a
re-export of `venues.json` with `lat/lon` from the publisher's Mongo —
deferred.

**Why before Session 17:** the map is a demo prop, not a deploy
prerequisite. But the deploy + smoke-test cadence in 17/18 wants stable
frontend, so adding visible features after deploy is more painful than
before. Cost ≈ half a session — the count-up hook + the new server field
are small.

### Session 16.6 IMPORTANT! DISCOVERED WHEN LETTING THE AUTOPLAY RUN FOR A LONG TIME

After letting the autoplay run for a long time one of the campaigns proof transactions started failing. with following error:
2026-04-28 21:02:37 2026-04-28 18:02:37,736 ERROR app.routers.proof :: settlement failed campaign=ac89a867-d1c6-4ba8-8b43-8b0ee001f2f7 nonce=auto-d7bd109cd3de4b14ac9d0e07c53a63ad publisher=3pMCrwRq5tNy1GdonrPivP389eYjeeoGTiMZDtQmV8W9 amount=0.0005
2026-04-28 21:02:37 Traceback (most recent call last):
2026-04-28 21:02:37 File "/app/app/routers/proof.py", line 151, in execute_settlement
2026-04-28 21:02:37 tx_hash = await privy.sign_and_send_solana(
2026-04-28 21:02:37 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
2026-04-28 21:02:37 File "/app/app/services/privy.py", line 158, in sign_and_send_solana
2026-04-28 21:02:37 raise last_error
2026-04-28 21:02:37 app.services.privy.PrivyError: privy error 400: {"error":"Error broadcasting transaction with message: Error: Transaction simulation failed: Transaction results in an account (0) with insufficient funds for rent","code":"transaction_broadcast_failure"}
2026-04-28 21:02:37 2026-04-28 18:02:37,745 INFO app.services.auto_play :: auto-play skipped campaign=ac89a867-d1c6-4ba8-8b43-8b0ee001f2f7 status=502 detail=settlement failed: privy error 400: {"error":"Error broadcasting transaction with message: Error: Transaction simulation failed: Transaction results in an account (0) with insufficient funds for rent","code":"transaction_broadcast_failure"}
2026-04-28 21:02:37 2026-04-28 18:02:37,776 INFO httpx :: HTTP Request: POST https://api.privy.io/v1/wallets/auomdybdb0uqanubb4f632xc/rpc "HTTP/1.1 400 Bad Request
I digged in and understand that this is because the campaign wallet SOL amount was almost at minimum (rent?) so privy didnt allow further transactions. This created a drift in the ledger checks.
We need to solve this before doing anything else.

- [ ] Discuss a solution
- [ ] Fix the issue.
- [ ] Fix the drift.

### Session 17 — GCP deployment prep

- [ ] Cloud Run configs (backend)
- [ ] Cloud SQL Postgres migration from SQLite
- [ ] Secret Manager for Privy secret, JWT server secret, GCS credentials, Circle API key (when/if account upgrade lands)
- [ ] Cloud Storage + CDN for dashboard build (separate bucket from creatives)
- [ ] Workload Identity for the GCS creatives bucket so we drop the JSON service account key from prod

### Session 18 — Deploy to GCP

- [ ] Deploy backend to Cloud Run
- [ ] Deploy dashboard
- [ ] CORS, custom domain if time permits
- [ ] Smoke test on live devnet
- [ ] Move treasury topup cron (if Circle upgrade landed) from local Windows Task Scheduler to Cloud Scheduler + Cloud Function

### Session 19 — Demo rehearsal + submission

- [ ] Judge demo script (2-3 min)
- [ ] Record demo video
- [ ] Submission README + Devpost writeup

### Buffer (sessions 19+)

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
- npm `@x402/svm@2.10.0` README line 1: _"SVM implementation of the x402 payment protocol using the **Exact** payment scheme with SPL Token transfers."_ Only `ExactSvmClient`, `ExactSvmFacilitator` are exported.
- Technical reason: `upto` on EVM uses Permit2; Solana has no Permit2 equivalent yet.

**When Solana `upto` ships, what changes in our codebase:**

Untouched (~75%): `/bid`, `/proof`, FIFO matching, OpenRTB contract, React dashboard shell, Privy auth, `used_nonces`, `settlements`, `proof_context` JWT design.

Changes (~25%, additive — our service split was built for this swap):
| Piece | Today (`exact`) | Future (`upto`) |
| ------------------- | ----------------------------------------- | ----------------------------------------------------- |
| Campaign wallet | Privy server wallet per campaign | Not needed — funds stay in advertiser wallet |
| Funding request | 402 → full-budget USDC transfer | 402 → signed authorization (cap + expiry + nonce) |
| Per-play settlement | Privy `signAndSend` from campaign wallet | Facilitator `draw` against authorization |
| Refund endpoint | Transfer remainder back to advertiser | Delete — authorization just expires |
| `services/x402.py` | `exact` builder only | Add `upto` builder + `draw` helper |
| `models.Campaign` | `wallet_id`/`wallet_address` | Swap for `authorization_token`/`authorized_until` |

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

### 2. Read-modify-write race on `campaigns.spent` in `execute_settlement` ✅ FIXED (Session 16.5)

**Symptom (historical):** the previous Python-side flow read `spent`, checked
the guard, mutated, committed — two concurrent `/proof` requests on the
same campaign could both pass and last-write-wins.

**Fix shipped:** atomic decrement with a guard clause, SQL-enforced. The
forward UPDATE in `app/routers/proof.execute_settlement` is now:

```sql
UPDATE campaigns
SET    spent = spent + :amount
WHERE  id = :id
  AND  budget - spent >= :amount
RETURNING spent, budget
```

Reject if `rowcount == 0`. Single statement, safe under any isolation level.
Do this BEFORE the Privy transfer, not after.

**Validated 2026-04-28:** post-reset controlled simulation ran 844 concurrent
plays distributed across 3 active campaigns with auto-play burst-firing
10–20 settlements/tick. `scripts/audit_ledger.py` returned zero DRIFT and
zero SHORT — every confirmed DB settlement matched a real on-chain transfer
to the microUSDC. Atomic UPDATE holds under burst-fire load.

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
- **2026-04-27 (Session 15):** Calculator + protocol fee shipped. Server-side `services/calc.compute_quote()` is the single source of truth for the budget breakdown; `POST /api/campaigns/quote` (Privy-authed) is what the wizard's Step 4 hits, and the same function runs server-side on POST `/api/campaigns` to determine the actual escrow amount. CPM locked at $0.50/1000 via `DEMO_CPM`; frequency = `OPERATING_HOURS_PER_DAY * PLAYS_PER_HOUR_PER_SCREEN` = 144 plays/screen/day. `CreateCampaignRequest` shrunk to creative + targeting + schedule only — no more user-supplied budget/CPM/duration. New columns `Campaign.protocol_fee_amount` + `protocol_fee_tx_hash` (dev SQLite ALTER carries them). After x402 settle confirms, the campaign wallet fires a Privy USDC tx for the 2.5% fee → `PROTOCOL_REVENUE_WALLET_ADDRESS`; best-effort, doesn't block activation. New `scripts/bootstrap_protocol_revenue.py` mirrors the treasury bootstrap. Wizard now 5 steps (Image → Targeting → Schedule → Budget → Review & Fund); StepCalculator + StepReview added, StepDetails renamed to StepReview and stripped of all numeric inputs. `CampaignCard` surfaces the protocol fee + fee tx Solscan link in the kv block. E2E still 13/13 on real devnet — but the long-running backend container now must be stopped first (`docker compose stop backend`) so its auto-play loop doesn't double-count `spent` via the shared SQLite. **User action remaining:** run `bootstrap_protocol_revenue.py`, paste env vars, restart backend, browser-walk the new wizard.
- **2026-04-27 (Session 14):** DMA targeting + scheduling shipped. Backend: `services/venues.py` loads `backend/data/venues.json` (gitignored, user-supplied) into an in-memory index — `dma → device_id[]`, `device_id → dma`, `display_counts`, `pick_random_device(labels)`. `DMA_LABELS` map canonicalizes Mongo codes (`ny`/`la`/`sf`/`mia`/`bos`/`aus`) to display labels. `Campaign.target_dmas` (JSON), `start_date`, `end_date` (Date) added; dev-only `_dev_alter_table_for_existing_sqlite()` in `database.py` ALTERs existing tables idempotently so column adds don't force a volume reset. New `routers/markets.py` exposes `GET /api/markets` (Privy-authed). `/bid` now requires `imp.ext.device_id`, resolves DMA via the index, filters FIFO candidates by `target_dmas` + schedule window, and lazy-flips `active`→`expired` for any campaign whose `end_date < today` while iterating. `CampaignStatus.EXPIRED` added; refund accepts it. Auto-play + `simulate-play` enforce the schedule window and pick a random device whose DMA matches the campaign's targeting; auto-play logs include venue name for ops debugging but `SimulatePlayResponse` exposes only `dma` to the dashboard (venue identifies a specific publisher partner — not safe to leak). Frontend: 4-step wizard now (`StepImage` → `StepTargeting` → `StepSchedule` → `StepDetails`); StepTargeting renders the 6 DMA cards with click-to-toggle, live REACH = sum of selected display counts, hardcoded "1 every 5 min" line; StepSchedule has native date inputs with today-min validation. `CampaignCard` shows targeting + schedule in the expanded detail and surfaces the DMA on the last-play indicator. `CreateCampaignRequest` validator rejects unknown DMAs, dups, past start dates, and end before start. Docker volume swap: bind-mount `./backend/data:/app/data` so the venues file is visible inside the container; existing DB preserved via `docker cp`. E2E (`scripts/e2e_demo.py`) updated to send `device_id` from the venues index and create campaigns targeting `San Francisco`; force-disables `AUTO_PLAY_ENABLED` at the top of the file because the lifespan loop ticks during the e2e's bid → proof retry window and double-counts `spent` otherwise. 13/13 on real devnet.
- **2026-04-27 (Session 12):** Treasury topup helpers shipped. Manual experiment confirmed Circle's per-address rate limit is real (claim into helper + immediate claim into treasury from same browser → both succeeded). New `scripts/bootstrap_helpers.py` creates N Privy server wallets and treasury-seeds each with 0.01 SOL via `build_sol_transfer_tx` + `wait_for_tx_confirmation` (the RPC-airdrop path silently fails the same way it does for campaign wallets, so we don't even try). New `scripts/sweep_helpers.py` reads zipped `HELPER_WALLET_IDS` / `HELPER_WALLET_ADDRESSES`, sweeps any non-zero helper to treasury, plus `--wallet-id` + `--wallet-address` rescue mode for one-offs. Used the rescue mode to recover 20 USDC from the throwaway helper created by `create_helper_wallet.py` during the manual probe. End-to-end verified: 4 helpers (3 bootstrap + 1 rescued) → 4 × Circle web-faucet claims → one `sweep_helpers.py` run consolidated 80 USDC to treasury with 4 Solscan tx hashes. **Reference-id length gotcha**: Privy's 64-char cap meant the first sweep failed with `invalid_data` — full uuid4 string suffix was 68 chars. Codebase convention is `uuid4().hex[:8]`, kept that in both new scripts. RUNBOOK has the daily-routine click sequence + rescue command.
- **2026-04-28 (validation pass):** Post-Session-16.7 hygiene reset + clean simulation. Wrote two new ops scripts: `scripts/audit_ledger.py` (read-only reconciliation, three sections — publisher / campaign-wallet / service-wallet — with SHORT/DRIFT/MORE/OK flags and a tolerance-aware comparison) and `scripts/sweep_to_treasury.py` (drains every owned Privy server wallet to treasury with a USDC-then-SOL ordering, gas-seed pre-pass for wallets that have USDC but zero SOL, dry-run by default). **Forensic finding:** the one DRIFT row in the initial audit (refunded campaign `2fc2e504` with 0.031 USDC stranded on-chain) was traced to pre-Session-16.5 settlement-tx-bytes dedup. Decoded the campaign's refund tx via `get_transaction(jsonParsed)` + pre/post token balance deltas: refund correctly sent `budget - spent = 2.8305` per the DB; campaign wallet held 2.8615 going in (because 62 of the 99 "confirmed" /proof settlements had been collapsed by Solana network dedup before the memo fix shipped at 18:16 the same day the campaign ran). Math reconciled exactly (62 × 0.0005 = 0.031). Same-shape leak as BACKEND-REVIEW.md §1.1, different root cause; current refund code has the §1.1 property but not the dedup property (memo fix landed 16.5). **Hygiene reset executed:** stopped backend → swept 12.82 USDC + 5.48 SOL across 51 campaign wallets + 4 helpers + protocol-revenue + demo-publisher → wiped `backend/data/adserver.db` → restart → audit returned empty (zero campaigns, zero settlements, treasury holds the consolidated funds). **Controlled simulation:** funded 3 campaigns through the wizard targeting different DMAs, paused after auto-play accumulated 844 plays / 0.4220 USDC across them. Audit returned **zero DRIFT, zero SHORT** on every reconciliation — publisher's 844 plays = 0.422000 USDC matched on-chain to the microUSDC, all 3 paused campaigns matched their `budget - spent` exactly, protocol revenue = 0.765000 USDC = 30.6 × 2.5% bit-perfect. **Refund flow validated:** refunded the meatiest paused campaign (`a8960943`, 17.0525 USDC remaining); on-chain ended at 0.0000, no leak, other 2 campaigns unaffected. Atomic UPDATE + memo fix from Session 16.5 confirmed correct under real concurrent load. Two new RUNBOOK sections document the audit + reset routines including a forensic recipe for tx-level investigation. Two small frontend polish bugs found and fixed during the session: leaflet z-index bleed above wizard modal (added `isolation: isolate` on `.x-map`, bumped Modal `zIndex` 100 → 1000), and the live activity map's integer-zoom-snap leaving big empty space around tight DMA bounds (`zoomSnap={0.25}` + tighter padding + `maxZoom={7}`). Also a UX nit: relocated the protocol-fee tx Solscan link from a standalone block under the map to a sub-link under the Protocol fee stat itself, and added a campaign-wallet Solscan link under the Remaining stat.
- **2026-04-28 (Session 16.7):** Per-campaign live activity map shipped. Backend: BACKEND-REVIEW.md §1.6 cleanup landed first — `routers/campaigns.campaign_stats` no longer fetches every confirmed settlement to compute `total_plays` + `total_confirmed_usdc`; one SQL `func.count` + `func.coalesce(func.sum(...), 0)` query replaces it. New `plays_by_dma: dict[str, int]` aggregate via SQL `GROUP BY device_id` resolved through the venues index — lifetime totals (no time cutoff so the count never tweens down), NULL device_ids excluded, unmapped device_ids bucket as `"Unknown"`. Schema field added to `CampaignStats`. E2E (`scripts/e2e_demo.py`) → 13/13 on real devnet both before and after the schema add (sequencing per PLAN: SQL cleanup → e2e → plays_by_dma → e2e → frontend). Frontend: `react-leaflet@^4.2.1` + `leaflet@^1.9.4` + `@types/leaflet@^1.9.12` (frontend image rebuilt with `--renew-anon-volumes` per the dep-bump ritual). New `lib/dmaCentroids.ts` (hardcoded city-level lat/lon for the 6 DMAs), `lib/useCountUp.ts` (rAF + ease-out cubic, 1000 ms default — 600 was too short), `components/LiveActivityMap.tsx` (Carto Dark Matter tiles, fully non-interactive, `FitOnMount` child uses `useMap()` + `fitBounds`), `tokens.css` `.x-map*` styles. Embedded inside the expanded `CampaignCard` between the targeting/last-play row and the recent settlements table. **Punch animation** (added late-session per user feedback that the count-up was "weak"): scale 1 → 1.28 → 1 with `cubic-bezier(0.34, 1.56, 0.64, 1)` over 550 ms + brief glow boost, triggered only when the _server_ count changes (not on every tween frame). Required architectural rethink: divIcon HTML rebuilds on every `useCountUp` frame would reset CSS animations ~60×/s; fixed by keying `useMemo` on `dma` only (not `display`), then updating count text and toggling the punch class imperatively on the marker's DOM via `markerRef.current?.getElement()` with a forced reflow (`void inner.offsetWidth`) so the animation restarts cleanly. Pattern reusable for any future leaflet divIcon work — captured in Session 16.7 findings. Pre-existing dead `StatusBadge` import in `pages/Campaigns.tsx` removed (was blocking `tsc -b --noEmit`). Browser walk on a real campaign confirmed pins render at city-level on targeted DMAs, auto-play deltas produce one punch per affected DMA in sync with the activity feed flash. tsc clean.
- **2026-04-27 (Session 16):** Frontend facelift + Session 16.5 perf/correctness pass. Design package in `/design/` ported into the live React app: `tokens.css` + `components/ui/` primitives + `AppHeader`/`TabRow`/`WalletChip` shell + `pages/Overview.tsx` + `pages/Campaigns.tsx` + `components/wizard/Modal.tsx` + 5 restyled steps + funding-progress + success state with two Solscan links + "Done → Campaigns auto-expand" navigation. Old `WalletPanel`/`CampaignsPanel`/`Home.tsx`/legacy `styles.css` classes deleted. `tsc --noEmit` clean. Mid-session expansions: (1) **`GET /api/dashboard-summary`** new aggregate endpoint replaced Overview's N-fan-out per-campaign /stats polling — 2 req/5s regardless of campaign count. (2) **PLAN must-fix #2 closed** — `execute_settlement` now does atomic `UPDATE ... SET spent=spent+:amt WHERE budget-spent+1e-9>=:amt`; concurrent calls cannot both pass. (3) **Compensating refund** on Privy failure decrements spent + un-completes status if our forward UPDATE flipped it. (4) **Memo on USDC transfers** — concurrent settlements with identical (from, to, amount) within one blockhash window were collapsed by Solana network dedup to a single on-chain tx. SPL Memo v2 program ID is case-sensitive (`MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr` — uppercase X), caught the typo against devnet. (5) **Multi-play auto-play** — `random.randint(min, max)` settlements concurrently per tick (`AUTO_PLAY_PLAYS_PER_TICK_MIN`/`_MAX` settings), each on its own DB session. SQLAlchemy connection pool bumped to size=30 / overflow=60 / timeout=60 since defaults (5+10) starved within one burst — every settlement holds a session through its ~5-10s Privy await. (6) **device_id end-to-end** — added optional field on `ProofContextClaims`; `/bid` extracts from `imp.ext.device_id` and threads through the JWT; `/proof` + simulate-play + auto-play persist on new nullable `Settlement.device_id` column (dev SQLite ALTER carries it); `SettlementSummary`/`DashboardActivityRow` resolve `device_id → dma` server-side via venues index. Dashboard's "Last play" + Overview's activity feed show DMA. Publisher integration unchanged — JWT is opaque, schema identical. (7) **`last_24h_plays` field** on `CampaignStats` — was previously derived from server-capped `recent_settlements` so the counter plateaued at ~30-40 once each campaign had ≥10 plays/24h. Now a real COUNT(\*). (8) **UTC timezone fix** — SQLite drops tzinfo on read; `_to_settlement_summary` now stamps `tzinfo=timezone.utc` before `isoformat()`, otherwise browser parses as local and rows look "3h ago" the moment they're created. (9) **Date-picker fix** in `StepSchedule` — the layered `opacity:0` native input pattern doesn't trigger Chrome's picker; replaced with `<button>` + `inputRef.current.showPicker()`. (10) **Row-flash animation** on Recent Activity (`.x-row-flash` keyframe + `useFlashOnArrival(ids)` hook). E2E (`scripts/e2e_demo.py`) → 13/13 with `docker compose stop backend` first (auto-play burst is now even more disruptive than before).
