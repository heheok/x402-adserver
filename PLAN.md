# x402 Ad Server — Build Plan

Living document. Updated at the end of every working session.

> **🚀 Resuming work from a cold start? Read this first.**
>
> 1. Read `BACKGROUND-INFORMATION.md` for the product spec (read-only reference). For commercial/stakeholder questions, see `BUSINESS-CONSTRAINTS.md`.
> 2. Scan the **Session roadmap** below — the first session without ✅ is where to pick up. Each session links to its detail file in `worklog/`; open it for the checklist, exit criteria, and findings.
> 3. Read `RUNBOOK.md` for every repeated ops task (start/stop, balance checks, funding, resets).
> 4. Confirm the user has `backend/.env` populated. The treasury vars (`TREASURY_WALLET_ID`, `TREASURY_WALLET_ADDRESS`) come from `scripts/bootstrap_treasury.py`. If they don't exist, bootstrap + fund per RUNBOOK.
> 5. Start containers: `docker compose up -d backend`. Smoke: `curl localhost:8000/health`.
> 6. The SQLite DB may be empty — that's expected. Seed with `scripts/seed_test_campaign.py` (future) or the one-liner in the relevant worklog file if you need a live campaign for testing.
> 7. Architectural decisions are fixed (see **Protocol notes** below and `memory/project_x402_adserver.md`). Don't re-litigate.
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

**UI polish backlog (logged 2026-04-30, post Session 16.9 browser walk):**

- **Faucet button is not disabled while a faucet tx is in-flight** — `WalletChip.tsx`
  renders the "Get test USDC" button as `disabled={faucet.isPending}` only for
  the immediate POST round-trip; once the response lands, `isPending` is false
  but the on-chain transfer can still take seconds to confirm. User can spam
  the button → multiple Privy txs queue up. Fix: keep the button disabled
  through the `pendingAmount` window (i.e. `disabled={faucet.isPending || pendingAmount !== null}`)
  so it stays locked until the wallet poll observes the new balance.

- **Total plays + per-DMA map markers flicker during pending→flushing→confirmed**
  on `CampaignCard`. Symptom: a play arrives, count goes from N to N+1, then
  briefly drops back to N for ~5s, then jumps back to N+1. Root cause:
  `routers/campaigns.campaign_stats` counts settlements with status in
  `(PENDING, CONFIRMED)` for `total_plays` and `plays_by_dma` — but the batch
  settler atomically flips PENDING → FLUSHING when it claims a row, and FLUSHING
  is NOT in the counted set, so the row is invisible to the count for the
  duration of the on-chain wait. Fix: add `SettlementStatus.FLUSHING.value` to
  `counted_statuses` in `campaign_stats` and the equivalent filter in
  `routers/dashboard.dashboard_summary` (`base_q` and the `recent_activity`
  query). Same idea: a FLUSHING row represents "play happened, money is on
  the way" — it should count exactly like PENDING does. The brief mention in
  Session 16.8 worklog of "pending + confirmed counts" predates the FLUSHING
  state being introduced; the count filter just didn't get updated.

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
