# Backend Pre-Prod Review

Findings from a full backend pass on 2026-04-28 (Session 16 frontend just landed,
Session 17 GCP-deploy-prep is up next). Each item is a thing that must be
**checked, fixed, or consciously deferred** before the backend serves real-money
traffic.

This file pairs with:
- `PLAN.md` — engineering roadmap and the "Must-fix before mainnet" list
- `BUSINESS-CONSTRAINTS.md` §7 — the broader mainnet-blocker list (auth, audit,
  custody, content moderation, etc.)
- `RUNBOOK.md → Audit reconciliation / Hygiene reset` — operational procedures
  (`scripts/audit_ledger.py`, `scripts/sweep_to_treasury.py`) for surfacing
  drift and resetting to a clean baseline.

When an item here overlaps an existing entry there, the cross-ref is noted and
this file does not duplicate the engineering detail — that's tracked there.

Items are checked off when the underlying code change ships, not when the
investigation completes. Items moved to `PLAN.md` get a strikethrough here with
a pointer.

---

## 1. Real bugs / data-integrity issues

### 1.1 Refund leaks USDC when the protocol-fee transfer failed
- [ ] Fix or document.
- **Where:** `backend/app/routers/campaigns.py:347-371` (post-settle fee
  transfer is best-effort + comment claims the fee will be refunded if the
  transfer fails) vs `campaigns.py:553` (refund computes
  `remaining = budget - spent`, which excludes the orphaned fee).
- **Symptom:** if the protocol-fee transfer fails after x402 settle, the 2.5 %
  fee sits in the campaign wallet. On refund, only `budget - spent` is sent
  back to the advertiser. The fee USDC stays in the campaign wallet permanently
  (Privy does not support wallet deletion — see `BUSINESS-CONSTRAINTS.md §3`).
- **Options:**
  - (a) Refund the actual on-chain USDC balance of the campaign wallet (read
    via `services/solana.get_usdc_balance`, transfer that exact amount).
  - (b) When `protocol_fee_tx_hash IS NULL`, include `protocol_fee_amount`
    in `remaining` and let the existing transfer carry it back.
  - Either way, fix the code or correct the comment — they currently disagree.
- **Detection:** `scripts/audit_ledger.py` flags this leak — refunded
  campaigns with non-zero on-chain USDC are reported as DRIFT, with the
  orphaned-fee subtotal called out separately (`Of that, declared orphaned
  fee`). See RUNBOOK → Audit reconciliation.
- **Validated 2026-04-28:** leak path does NOT trigger when fee tx succeeds.
  Confirmed by post-reset refund of campaign `a8960943` (17.0525 USDC
  remaining, fee already paid at activation): on-chain ended at exactly
  0.0000, audit clean. The leak is real only on the fee-tx-failure path,
  which we have not artificially triggered.

### 1.2 Nonce committed before atomic budget UPDATE — failed UPDATEs orphan nonces
- [ ] Fix or document.
- **Where:** `backend/app/routers/proof.py:67-114`.
- **Symptom:** `UsedNonce` is committed in its own transaction, then the
  atomic budget UPDATE runs. The compensating refund on the *Privy-failure*
  path (line 172) is correct — nonce stays consumed for replay protection.
  But the *rowcount=0* path (campaign no longer ACTIVE, drained, missing) also
  leaves the nonce row, with **no settlement row anywhere**. Silent garbage.
- **Compounds with:** `used_nonces grows forever` (PLAN.md must-fix #4) — same
  table, two leaks.
- **Fix:** either claim the nonce in the same SQL statement as the budget
  UPDATE (subquery / CTE), or roll back the nonce on rowcount=0. The
  replay-protection invariant should still hold for any path where the
  publisher has reason to believe the on-chain transfer might have happened.

### 1.3 JWKS cache never invalidates
- [ ] Fix.
- **Where:** `backend/app/dependencies.py:34-44`.
- **Symptom:** `_jwks_cache` is populated on first fetch and never refreshed
  for the life of the process. If Privy rotates a signing key, every token
  signed by the new key is rejected until backend restart.
- **Fix:** add a TTL (5–15 min suggested) and refetch on `KeyError` during
  decode. Optionally cache by `kid` so a partial rotation doesn't invalidate
  good tokens.

### 1.4 Publisher API-key check is not constant-time
- [ ] Fix (one-liner).
- **Where:** `backend/app/dependencies.py:17`.
- **Symptom:** `x_api_key != settings.publisher_api_key` is timing-attackable.
- **Fix:** `secrets.compare_digest(x_api_key, settings.publisher_api_key)`.
- **Risk:** very low in practice (single secret, no per-target oracle), but
  the fix is free.

### 1.5 `/bid` writes (lazy-expire commits) on the read hot path
- [ ] Decide before mainnet.
- **Where:** `backend/app/routers/bid.py:71`.
- **Symptom:** `_pick_campaign` walks active campaigns and `db.commit()`s any
  expired flips inside `/bid`, which is supposed to fit a <500 ms latency
  budget. Bounded today by single-digit campaign counts; at scale this puts
  write contention on the read path.
- **Options:**
  - (a) Periodic sweep job runs the expire pass; `/bid` only reads.
  - (b) Cap the in-bid sweep to one row per call.
  - (c) Index on `(status, end_date)` and skip expired rows in the WHERE
    instead of post-fetch filtering.

### 1.6 `campaign_stats` does N-row in-Python aggregates ✅ FIXED (Session 16.7)
- **Where:** `backend/app/routers/campaigns.py:420-426` (now SQL aggregates)
  and `:448-465` (sibling `plays_by_dma` aggregate landed in the same
  session).
- **Fix shipped:** `func.count()` + `func.coalesce(func.sum(amount_usdc), 0)`
  for `total_plays` + `total_confirmed_usdc`; sibling `GROUP BY device_id`
  for `plays_by_dma`. E2E 13/13 both pre- and post-rewrite, response shape
  unchanged. See PLAN.md → Session 16.7 for findings.

### 1.7 HTTPX client created per-call inside `PrivyClient`
- [ ] Fix.
- **Where:** `backend/app/services/privy.py:62-63, 134`.
- **Symptom:** `def _client(self)` returns a fresh `httpx.AsyncClient` on
  every method call — no connection pooling. The retry loop in
  `sign_and_send_solana` opens a new client on each retry attempt, so each
  retry pays a full TLS handshake. Auto-play firing 10–20 plays/tick = 10–20
  fresh handshakes to api.privy.io every 15 s.
- **Fix:** one long-lived `AsyncClient` per `PrivyClient` instance, opened
  in `__init__`, closed on shutdown.

### 1.8 Missing index on `Settlement.created_at`
- [ ] Fix (cheap).
- **Where:** `backend/app/models.py:87`; queries at
  `backend/app/routers/dashboard.py:49`,
  `backend/app/routers/campaigns.py:441`,
  `backend/app/routers/proof.py` (settlement reads).
- **Symptom:** the column is the `ORDER BY DESC` and 24h-cutoff key for
  almost every settlement read, but has no index. SQLite scans.
- **Fix:** add `index=True` to the `created_at` column on `Settlement` and
  let `create_all` build it. Same for `Settlement.status` if we ever filter
  on `failed` rows at scale (retry queue).

---

## 2. Demo-only code that ships unguarded

These four are explicitly listed in `PLAN.md → "Resolved decisions" →
"Demo-only endpoints/flags that must NOT ship to production"`. Currently
nothing prevents them from going live in deployed builds.

- [ ] **`POST /api/campaigns/:id/simulate-play`** — `campaigns.py:591`.
  Registered unconditionally.
- [ ] **`POST /api/faucet`** — `wallet.py:42`. Registered unconditionally.
  Treasury-drain risk because there is **no per-user rate limit** (see §3.1).
- [ ] **`run_auto_play_loop`** — `auto_play.py:163`. Lifespan task wired in
  unconditionally; behavior gated only on the `AUTO_PLAY_ENABLED` env flag.
- [ ] **`GET /api/auto-play-status`** — `health.py:24`. Public, exposed even
  when auto-play is disabled.

**Suggested fix:** wrap router-include in `main.py` with
`if settings.environment in {"dev", "staging"}:` and drop the simulate +
faucet + auto-play-status routes from production builds entirely. Keep
`auto_play_enabled` defaulting to false but also gate the lifespan task on
the same environment check so misconfigured envs don't accidentally enable.

---

## 3. Security observations

### 3.1 No rate limiting anywhere
- [ ] Faucet rate limit (Session 2 leftover, tracked in PLAN.md
  "Open decisions still to resolve").
- **Where:** `backend/app/routers/wallet.py:42`.
- **Symptom:** one user can drain the treasury on fast clicks. Especially
  acute with the Circle multi-helper setup currently providing only
  ~60–120 USDC/day of treasury runway.
- **Fix:** in-process per-user-per-hour cap is enough for the hackathon
  demo; production wants `slowapi` + Redis or proxy-layer limits.

### 3.2 Per-publisher rate limiting absent on `/bid` and `/proof`
- Tracked in `PLAN.md → Must-fix before mainnet → §4`. No action this file.

### 3.3 `proof_context` JWT has no `iss`/`aud`
- [ ] Add (defence-in-depth, cheap).
- **Where:** `backend/app/services/tokens.py:35`.
- **Symptom:** if `JWT_SERVER_SECRET` ever leaks into another HS256 system
  (e.g. a dev's other project), tokens cross-validate.
- **Fix:** add `iss="solboards"`, verify on decode. Same change to
  `dependencies._verify_privy_jwt` already enforces `iss="privy.io"` —
  good model to copy.

### 3.4 Publisher API key is single shared secret
- Tracked as production blocker (`BUSINESS-CONSTRAINTS.md §7.2` — advertiser
  side; publisher side is the same shape). No action this file.

### 3.5 Refund-address trust
- Tracked in `BUSINESS-CONSTRAINTS.md §5 "Refund-address trust"`. The
  property currently holds because `Campaign.advertiser_wallet` is captured
  at create time from the Privy-derived identity, not advertiser input.

### 3.6 GCS bucket is public-read
- Tracked in `BUSINESS-CONSTRAINTS.md §5 "Creative hosting"` and §7.16
  (content moderation). No action this file.

---

## 4. Smaller bugs / inconsistencies

- [ ] **`epsilon = 1e-9` duplicated** as a magic literal across
  `bid.py:68`, `proof.py:93,184`, `auto_play.py:116`, `campaigns.py:613`.
  Hoist a single `BUDGET_EPSILON` constant (probably to `services/calc.py`).
- [ ] **`_solscan_tx_url` duplicated** in `routers/campaigns.py:50` and
  `routers/dashboard.py:19`. Move to `services/solana.py` (or a tiny
  `solana_links.py`).
- [ ] **`_resolve_advertiser_wallet` duplicated** in `routers/wallet.py:17`
  and `routers/campaigns.py:111`. Same body, different file. Extract.
- [ ] **`except (PrivyError, Exception)`** in `proof.py:156` and
  `retry.py:74` is redundant — `Exception` subsumes `PrivyError`. Drop.
- [ ] **Naive datetime cutoffs** in `dashboard.py:35-37` and
  `campaigns.py:434` use `.replace(tzinfo=None)` to match SQLite's naive
  storage. Will silently break the moment Postgres lands in Session 17
  (Postgres preserves tz, comparing aware-to-naive raises). Convert to
  aware-aware comparison everywhere now to land smoothly.
- [ ] **`get_facilitator_fee_payer` cache never expires** —
  `services/x402.py:73`. Process-lifetime cache. If the facilitator rotates
  its fee-payer address, we stick to the old one until restart. Add a
  24h TTL.
- [ ] **`Privy.get_user_solana_wallet` returns the first match** —
  `services/privy.py:165-171`. Fine today (single embedded wallet) but
  worth a comment noting the assumption.
- [ ] **`solana.airdrop_sol` is dead code** — `services/solana.py:263-277`.
  Superseded by `build_sol_transfer_tx` per Session 7. Delete.
- [ ] **Float math everywhere for money.** Tracked as
  `PLAN.md → Must-fix before mainnet → §3`. Storing as integer microUSDC is
  the cleaner fix; the `+ 1e-9` epsilons disappear with it. This file
  inherits the entry by reference; no separate action here.

---

## 5. What's load-bearing and must NOT be regressed

Stuff that earned its complexity. If a future change touches these files,
the reviewer should explicitly check that the property still holds.

- **Atomic SQL UPDATE for budget reservation** — `proof.py:96-114`. Closes
  PLAN.md must-fix #2. Concurrent `/proof` calls cannot both pass. Any
  refactor that splits the read and write back into Python-side reopens the
  race.
- **Compensating refund on Privy failure** — `proof.py:172-205`. Forward
  UPDATE reserves budget, failure decrements + un-completes status. Nonce
  stays consumed (replay protection). Don't simplify away the un-complete
  case — it's the un-COMPLETED-on-false-final-play half.
- **SPL Memo on every USDC transfer** — `solana.py:34-43, 132-133`. Defeats
  Solana's network-level tx-bytes dedup that would otherwise collapse N
  concurrent identical (from, to, amount) settlements to 1 on-chain
  transfer. Without the memo, 10 budget rows burn for 1 actual payout.
- **Privy retry scoped to `transaction_broadcast_failure` only** —
  `privy.py:25-38, 146-149`. The comment explicitly warns against widening
  this without a Solana pre-flight check. Read it before you add codes.
- **Eager `PrivyClient.__init__` validation** — `privy.py:51-52`. Fails at
  boot if env is missing rather than mysteriously at first call.
- **`mode="json"` on JSONResponse** — `campaigns.py:378`. Required so date
  fields serialize through plain `json.dumps` (the Pydantic encoder hook
  doesn't run on plain JSONResponse).
- **Dev-only ALTER TABLE shim** — `database.py:75-88`. Clearly marked for
  removal at the Postgres+Alembic migration. Don't leave it on once
  Alembic owns schema changes.
- **`auto_play._settle_one` opens its own DB session** — `auto_play.py:56`.
  Required for safe concurrent writes from the burst-fire loop. Don't
  share sessions across tasks here.

---

## 6. Suggested order of fixes before Session 17 deploy

If we touch any of this, this is the order that gets the most production
risk reduction per session of work:

1. **§1.1** — protocol-fee refund leak. Real money lost on a real failure
   path. The fix is small (read on-chain balance, refund that).
2. **§2** — gate demo endpoints behind `environment in {"dev","staging"}`.
   One change in `main.py`, prevents the worst deploy mistakes.
3. **§3.1** — per-user faucet rate limit. Single biggest threat to demo
   stability if the URL leaks.
4. **§1.3** — JWKS cache TTL. One-day Privy key rotation = silent total
   outage otherwise.
5. **§1.7** — long-lived `httpx.AsyncClient` in `PrivyClient`. Free perf
   win, ships with the deploy.

Everything else is real but won't bite the hackathon submission and can be
slotted into Session 16.6 / Session 17 polish as time permits.

---

## 7. Cross-references — DO NOT duplicate engineering detail

The following items live in canonical docs and are NOT re-tracked here:

- **Budget overcommit at `/bid`** (mints unbounded `proof_context` JWTs) —
  `PLAN.md → Must-fix before mainnet → §1`.
- **Money as integer microUSDC** — `PLAN.md → Must-fix before mainnet → §3`.
- **Per-publisher rate limiting / multi-worker / `used_nonces` retention** —
  `PLAN.md → Must-fix before mainnet → §4`.
- **Advertiser API-key auth (production)** — `BUSINESS-CONSTRAINTS.md §7.2`.
- **Anchor PDA trustless custody upgrade** — `BUSINESS-CONSTRAINTS.md §7.3`.
- **Backend security review** — `BUSINESS-CONSTRAINTS.md §7.4`.
- **Refund-address ownership verification** — `BUSINESS-CONSTRAINTS.md §7.6`.
- **Dispute resolution / hardware attestation / multisig oracle** —
  `BUSINESS-CONSTRAINTS.md §7.8-§7.10`.
- **Privy `reference_id` retry-safety story** —
  `BUSINESS-CONSTRAINTS.md §3, §7.14`.
- **Creative content moderation** — `BUSINESS-CONSTRAINTS.md §7.16`.
- **SOL gas subsidy decision** — `PLAN.md → Open decisions still to resolve`.
