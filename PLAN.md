# Solboards — Build Plan

Living document. Updated at the end of every working session.

> **🚀 Resuming work from a cold start? Read this first.**
>
> 1. Read `BACKGROUND-INFORMATION.md` for the product spec (read-only reference). For commercial/stakeholder questions, see `BUSINESS-CONSTRAINTS.md`.
> 2. Scan the **Session roadmap** below — the first session without ✅ is where to pick up. Each session links to its detail file in `worklog/`; open it for the checklist, exit criteria, and findings.
> 3. Read `RUNBOOK.md` for every repeated ops task (start/stop, balance checks, funding, resets).
> 4. Confirm the user has `backend/.env` populated. The treasury vars (`TREASURY_WALLET_ID`, `TREASURY_WALLET_ADDRESS`) come from `scripts/bootstrap_treasury.py`. If they don't exist, bootstrap + fund per RUNBOOK.
> 5. Start containers: `docker compose up -d backend`. Smoke: `curl localhost:8000/health`.
> 6. The SQLite DB may be empty — that's expected. Seed with `scripts/seed_test_campaign.py` (future) or the one-liner in the relevant worklog file if you need a live campaign for testing.
> 7. Architectural decisions are fixed (see **Protocol notes** below). Don't re-litigate.
> 8. Update this file (and the matching `worklog/session-NN.md`) plus `RUNBOOK.md` at the end of every session.

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

Each session is ~1 working block. Order is the dependency chain — later sessions need earlier ones. Per-session detail (checklist, findings, work-log entry) lives in `worklog/`.

- [Session 1 — Scaffold + plumbing](worklog/session-01.md) ✅
- [Session 2 — Privy + wallet endpoints](worklog/session-02.md) ✅
- [Session 3 — x402 campaign creation](worklog/session-03.md) ✅
- [Session 4 — Bid matching](worklog/session-04.md) ✅
- [Session 5 — Proof of play + settlement](worklog/session-05.md) ✅
- [Session 6 — Campaign management](worklog/session-06.md) ✅
- [Session 7 — Backend integration + hardening](worklog/session-07.md) ✅
- [Session 8 — React dashboard scaffold](worklog/session-08.md) ✅
- [Session 9 — Dashboard flows (fund)](worklog/session-09.md) ✅
- [Session 10 — Dashboard flows (play + refund)](worklog/session-10.md) ✅
- [Session 11 — Integration polish](worklog/session-11.md) ✅
- [Pre-deploy feature scoping (2026-04-24, design + planning)](worklog/planning-2026-04-24.md) ✅
- [Session 12 — Treasury topup helpers (multi-wallet workaround)](worklog/session-12.md) ✅
- [Session 13 — Wizard shell + creative image upload (Feature 1)](worklog/session-13.md) ✅
- [Session 14 — DMA targeting + scheduling (Features 2 + 3 + 4)](worklog/session-14.md) ✅
- [Session 15 — Campaign calculator + protocol fee (Feature 5)](worklog/session-15.md) ✅
- [Session 16 — Frontend facelift (design implementation)](worklog/session-16.md) ✅
- [Session 16.5 — Performance + correctness pass](worklog/session-16.5.md) ✅
- [Session 16.6 — SOL exhaustion + RPC-rate-limit drift (resolved by 16.8)](worklog/session-16.6.md) ✅
- [Session 16.7 — Per-campaign live activity map (demo polish)](worklog/session-16.7.md) ✅
- [Validation pass (2026-04-28) — hygiene reset + clean simulation](worklog/validation-pass-2026-04-28.md) ✅
- [Session 16.8 — Batch settlements](worklog/session-16.8.md) ✅
- [Session 16.9 — Money refactor: float → integer microUSDC](worklog/session-16.9.md) ✅
- [Session 17 — Local prod-shape compose (Caddy + multi-stage SPA build)](worklog/session-17.md) ✅
- [Rebrand to Solboards (2026-05-03) — domain locked, x402-Ad-Server → Solboards across UI/configs/containers/docs/memory; Privy modal themed](worklog/rebrand-2026-05-03.md) ✅
- [Session 18 — Deploy to GCE VM (solboards.xyz) — Cloudflare orange-cloud + Origin Cert, nightly SQLite → GCS backup](worklog/session-18.md) ✅
- [Session 18.7 — Responsive design pass + creative auto-resize + active-campaign shine](worklog/session-18.7.md) ✅
- [Session 19.5 — Automated content moderation (Vertex AI + Gemini 2.5 Flash)](worklog/session-19.5.md) ✅

### Session 19 — Pre-demo polish + submission

- [x] **Faucet rate-limit / cap per advertiser** ✅ (2026-05-03). New `faucet_claims` table (id, advertiser_id, advertiser_wallet, amount_usdc, tx_hash, status, created_at). `POST /api/faucet` sums non-failed/non-returned claims for the requesting Privy DID and rejects with 429 if `sum + new_amount > FAUCET_LIFETIME_CAP_USDC` micro (env-tunable, default 100 USDC). Pending counts toward the cap (closes the spam-click window during broadcast). At the demo's `FAUCET_AMOUNT_USDC=20`, that's 5 shots per advertiser before 429. `POST /api/faucet/reset` releases the cap on drain-to-treasury. Auto-creates via `create_all`, no migration. Manual override on the VM: `DELETE FROM faucet_claims WHERE advertiser_id='did:privy:...';`. See `BUSINESS-CONSTRAINTS.md §6` for the full decision record.
- [x] **Pre-demo polish bundle** ✅ (2026-05-03). Bundled UX work shipped under the same Session 19 banner:
  - Removed the "Simulate play" button from the campaign card. Backend `/api/campaigns/:id/simulate-play` route stays in place (still flagged as demo-only in `BUSINESS-CONSTRAINTS.md §5`); auto-play drives the demo.
  - "New campaign" button colorscheme swap (blue → gradient) across TabRow + Overview-empty + Campaigns-empty for visual consistency with the "Get test USDC" CTA.
  - Pre-wizard balance guard: clicking "New campaign" with `usdc_balance == 0` shows a styled toast ("Get test USDC from your wallet first") instead of opening the wizard. Fail-open if the wallet query hasn't loaded yet — StepCalculator's existing insufficient-funds guard catches anything downstream.
  - Faucet "Confirming…" stuck-button fix: relaxed the post-faucet clearing condition (any visible balance bump clears, not exact-match) and added a hard 25s timeout fallback.
  - Wizard modal body-scroll lock: html + body get `overflow:hidden` + `overscroll-behavior:contain` while open. Kills the bleed-through scroll and mobile pull-to-refresh.
  - Empty-state copy fix: step 02 dropped the misleading "Sign one x402 transfer" — the Privy embedded wallet auto-signs without a user prompt.
- [x] **Settlement batch grouping** ✅ (2026-05-03). Replaced client-side row collapsing with backend-side aggregation. New `services/batches.py` groups raw `Settlement` rows by `tx_hash` (confirmed batches) or `(status, campaign_id, publisher_wallet)` (queued). `PENDING + FLUSHING` normalize to a single "pending" status so they don't visually split during the brief flush window; `FAILED` and `NEEDS_REVIEW` keep their own buckets. `/api/campaigns/{id}/stats.recent_settlements` and `/api/dashboard-summary.recent_activity` now overfetch 300 rows and return ≤10 batched rows. Schemas reshaped: dropped `nonce` + single `dma`, added `play_count` + `dmas:list[str]`. The `id` field is synthetic so the React key is stable across the pending → confirmed flip (intentional brief flash signals the batch landed). Frontend `groupByBatch` helper deleted; `formatDmas` retained for rendering. Performance follow-up: Python grouping is sub-millisecond at demo scale; SQL `GROUP BY` migration is a Buffer item if production multi-tenant scale demands it.
- [ ] Judge demo script (2-3 min)
- [ ] Record demo video
- [ ] Submission README + Devpost writeup

### Buffer (sessions 19+)

- Blockers, polish, stretch items (batch settlement toggle, better fraud checks).
- **Workload Identity for the GCS creatives bucket** (deferred from Session 18) — replace the JSON SA key in `backend/.secrets/` with Workload Identity Federation. Acceptable for the demo as-is.
- **Treasury topup cron migration** (deferred from Session 18) — if/when the Circle devnet faucet is upgraded out of the 20 USDC / 2h cap, move the topup cron from local Windows Task Scheduler to Cloud Scheduler + Cloud Function so it survives the operator's laptop being off.
- **SQL-side settlement batch grouping** (deferred from Session 19) — current implementation groups in Python over a 300-row fetch per polled endpoint. Sub-ms at demo scale and equal to a `GROUP BY` in practice; revisit if production multi-tenant load (100+ advertisers polling simultaneously) makes the per-poll cost meaningful. Sketch in `services/batches.py` docstring.

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

### 3. Money is stored as `float`, not integer microUSDC ✅ FIXED (Session 16.9)

**Symptom (historical):** `campaigns.budget`, `campaigns.spent`, and the Python
math throughout `/bid` `/proof` and `auto_play` all used `float`. Summing
`0.001` many times drifted ~1e-16 per step, so the "final play" guard could
reject a semantically-valid play and leave unplayable dust ACTIVE. Demo-time
band-aid was `+ 1e-9` epsilon tolerance on every budget guard AND flipping
COMPLETED when `remaining < cost_per_play` (not `spent >= budget`). Drift was
visibly present in the wild — the pre-refactor DB had rows like
`spent=0.6139999999999878` for a campaign that ran exactly 614 plays at
$0.001/play.

**Fix shipped:** money is integer microUSDC (1 USDC = 1_000_000 micro)
end-to-end:

- DB columns are `BigInteger` (`campaigns.cpm_price/budget/spent/protocol_fee_amount`,
  `settlements.amount_usdc`).
- Python internals are `int` micro everywhere; no float in any money path.
- Wire format is a string of integer micro (e.g. `"422000"` for $0.422),
  matching x402 + SPL token convention. Pydantic field type alias is
  `MicroStr = str`.
- Frontend `lib/money.ts` provides BigInt-native `formatUsdc / sumMicro /
  subMicro / cmpMicro` helpers; float USDC contained to one well-marked UI
  spot (WalletChip pending-amount delta) at the `/api/wallet` boundary.
- JWT `proof_context` claims carry `amount_micro: int` (v=2 schema; v=1 tokens
  fail to decode after deploy — TTL covers the window).
- `services/x402.build_payment_requirements(amount_micro)` and
  `services/solana.build_usdc_transfer_tx(amount_micro)` both take int micro
  directly; the `int(round(* 1e6))` conversions are gone.
- `audit_ledger.py` uses exact `==` instead of tolerance bands.

All `+ 1e-9`, `epsilon`, `< tolerance` comparisons in money paths are gone.

**Validated 2026-04-30:** `e2e_demo.py` passes 25/25 (including multi-campaign
batch isolation, refund-with-pending, drained-budget auto-completion).
`audit_ledger.py` returns zero DRIFT, zero SHORT, zero IN-FLIGHT.
`tsc --noEmit` clean on frontend. Browser walk-through ran 4 campaigns through
the wizard + funded + auto-play soak.

### 4. `post_broadcast_uncertain → mark_back_to_pending` actively drains campaign wallets (raised 2026-04-30)

**Symptom (verified live):** A batch settlement row that ends up in
`status='pending'` after a "reference_id already exists" error from Privy
is re-claimed every batch tick, re-broadcast, returns the same error, and
gets marked back to pending. Each cycle results in a *real* on-chain USDC
transfer of the batch amount (~$0.001 per batch tick) leaving the campaign
wallet, despite Privy's 400 response. We watched a paused campaign drain by
~$0.139 over 25 minutes from two stuck pending rows alone.

**Root cause hypothesis:** Privy's `reference_id` duplicate-check fires
after the inner broadcast attempt, not before. Each retry has a fresh
blockhash so the tx bytes differ from the original. Privy broadcasts the
new tx, then notices the reference_id collision, then returns 400. The
tx is already on-chain by then. The existing code path
(`batch_settler._flush_group` → `post_broadcast_uncertain → _mark_back_to_pending`)
sets us up to repeat this every 5s forever once a row enters the cycle.
Documented in `services/privy.py` comments that `reference_id` is "NOT a
strict pre-broadcast idempotency key" — this session is the live confirmation
that it's not even a strict broadcast-blocker, just a recorder.

**How rows enter the cycle (not exhaustive):** any time we re-broadcast a
batch whose reference_id Privy has already seen. Triggers seen this
session: (a) manual orphan-recovery (we flipped FLUSHING → PENDING and the
re-broadcast collided), (b) the `post_broadcast_uncertain` path itself
catching a 5xx after the original tx actually landed, then bouncing the
row back to pending so the next tick repeats.

**Real fix:** when Privy returns "already exists" on a sign_and_send_solana
call, look up the original tx hash via Privy's API (or via on-chain
inspection of the wallet's recent tx history filtered by reference_id /
memo prefix), verify it confirmed, and either mark the batch CONFIRMED with
that hash or compensate. Never re-broadcast a batch whose reference_id has
already been recorded. Until that's built, do not introduce any code path
that automatically re-broadcasts on collision. This blocks any production
deployment.

**Stop-gap shipped 2026-04-30:** the proposed `_recover_orphaned_flushing`
on startup recovery is explicitly NOT implemented (see batch_settler.py
docstring); FLUSHING rows must be manually triaged. The 2 stuck pending
rows from this session were SQL-flipped to `failed` (without compensation)
to break the cycle; ~$0.139 of unaccounted on-chain drift on campaign
`9a522194-8bf2-467e-9f59-cb9c0ef2e4a1` and similar amounts on its
siblings are accepted as devnet test losses (funds went to our own
demo publisher wallet, recoverable manually).

### 5. Smaller things (same review)

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

- ~~Alembic migrations vs `create_all`~~ — **resolved 2026-04-30**: SQLite stays in prod (Session 18 is single-VM with persistent disk, no Postgres migration), so `create_all` is sufficient for the lifetime of the hackathon. Reopen if/when we move to Postgres.
- ~~Dashboard host port~~ — **resolved 2026-04-30**: irrelevant in prod-shape. Caddy serves the SPA on 443; dev keeps 5173 for the Vite dev server.
- Rate limiting on `/api/faucet` — one shot per user per hour? Decide in Session 2.
- **Decoupling campaign-api from ad-server** (raised 2026-04-21, deferred). Three options sized: Option A = shared DB + two FastAPI apps (~1 session), Option B = independent DBs + internal HTTP (~2–3 sessions, adds network hop to bid path — risky for <500ms target), Option C = event-driven (~3–5 sessions, production-grade). Leaning Option A if we decide to do it; slot between Session 7 and Session 8.
- **SOL gas subsidy model — partially resolved by Session 9 findings, still open for production** (raised 2026-04-22 Session 7, updated 2026-04-22 Session 9, refund-leak fix 2026-05-10). **For the advertiser-funding tx specifically**: resolved — x402-solana + x402.org forces facilitator-as-fee-payer (Config 2), so the advertiser needs zero SOL. x402.org's devnet facilitator sponsors gas for free. **Still open for campaign wallet ops** (`/proof` settlements, refunds): today the treasury seeds every new campaign wallet with 0.01 SOL (~$2 on mainnet) so it can pay its own fees. Options unchanged: **(A)** Privy fee sponsorship via `sponsor: true` on `sign_and_send_solana`; **(B)** keep subsidy + price into CPM; **(C)** move `/proof` settlement to a facilitator-like pattern. **Also now open for production of the funding flow**: public facilitators may charge or go away, so production likely needs us to run our own facilitator (Coinbase open-sourced Go + TS impls) and pay our own gas there. Status quo (treasury seeds 0.01 SOL per wallet) works for the hackathon devnet demo; decide before any mainnet path.

  **Refund-time SOL leak — fixed 2026-05-10 (commit `a782f9b`).** Two bugs in `app/routers/campaigns.py::refund_campaign` left unburned seed SOL stranded on every terminated campaign wallet:
  - **(1) Early-return skipped sweep.** When `remaining_micro <= 0` (campaign drained to zero via settles), the handler flipped status to REFUNDED and returned before reaching the SOL-sweep block. Full seed leaked on every fully-played refund.
  - **(2) Buffer too tight for replica lag.** When the sweep did run, `sweep_lamports = sol_lamports - 10_000` failed `insufficient lamports` off-by-fee whenever `get_sol_lamports` hit a lagging devnet read-replica that returned a pre-tx balance. Caught silently by `except Exception`, so failures were invisible.

  Fix: USDC tx now conditional on `remaining_micro > 0`, status flip + sweep moved out of the conditional, `wait_for_tx_confirmation` gated on `if tx_hash:`, buffer 10k → 50k lamports (~$0.01 dust).

  **`scripts/recover_refunded_sol.py`** — janitor for already-stranded balances. Walks REFUNDED + COMPLETED campaigns and EXPIRED-with-zero-USDC. Active/paused/draft and EXPIRED-with-USDC are never touched. Dry-run by default; `--execute`, `--campaign-id`, `--status` flags. Validated 2026-05-10 against wallet `C74fQjQh…` — recovered 33.555M lamports cleanly, left exactly the 1M-lamport buffer behind.

  **Still deferred — ATA-close to recover ~2,039,280 lamports/wallet of locked rent.** The campaign wallet's USDC ATA is created at bootstrap (`build_campaign_bootstrap_tx`) and never closed; its rent stays locked even after a successful sweep. Adding `spl_token.close_account` to the sweep tx would recover ~$0.40/wallet at $200/SOL (~$80–100 across the current 200+ campaigns). Hard precondition: ATA balance must be exactly 0 (close fails otherwise) — REFUNDED and COMPLETED satisfy this by construction; EXPIRED needs an on-chain check. Estimated ~30 min implementation; not on the demo path.

## Environment / secrets checklist

- [ ] `PRIVY_APP_ID` (supplied by user)
- [ ] `PRIVY_APP_SECRET` (supplied by user)
- [ ] `JWT_SERVER_SECRET` (we generate)
- [ ] `PUBLISHER_API_KEY` (we generate; the publisher network will be given one)
- [ ] `SOLANA_RPC_URL` — default devnet `https://api.devnet.solana.com`
- [ ] `X402_FACILITATOR_URL` — `https://x402.org/facilitator`
- [ ] `USDC_MINT_DEVNET` — `4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU`
- [ ] `TREASURY_WALLET_ID` — generated via bootstrap script in Session 2
