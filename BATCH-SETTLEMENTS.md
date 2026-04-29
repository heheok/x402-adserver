# Session 16.8 — Batch Settlements

> **STATUS: SHIPPED 2026-04-29.** Live in `app/services/batch_settler.py`.
> Validated against acceptance §10 (e2e 15/15, 3621-play soak with zero
> drift, refund-with-pending, restart resilience). See `PLAN.md → Session
> 16.8` for the close-out + work log. **Do not re-implement.** This brief
> is preserved for archaeology — read PLAN.md first if you're trying to
> understand the live system.
>
> **Notable deviations from the brief:**
> 1. Added a `flushing` intermediate `SettlementStatus` and an atomic
>    pre-process claim (UPDATE … SET status='flushing' WHERE status='pending'
>    AND id IN …). Closes a race the brief dismissed in §6.4 — refund's
>    `flush_campaign` and the loop's `flush_all` could pick overlapping
>    row sets and produce divergent ref_ids → double-broadcasts.
> 2. `reference_id` uses the full first_nonce, not `[:8]`. The brief's
>    truncation collided ~64 batches in (auto-play nonces only have 3 hex
>    chars of uniqueness in the first 8 chars). Collision → Privy 400
>    "already exists" → drift, per BUSINESS-CONSTRAINTS §3.
> 3. 5xx and 400 "already exists" treated as post-broadcast uncertain →
>    leave pending. The brief's §6 only handled RPC-blindness on the wait
>    side; Privy gateway errors were silently in the "definitive" bucket
>    and produced drift during validation.
>
> **Self-contained implementation brief below.** Written 2026-04-28 for a
> cold-start agent. Pre-shipping context.

This is the blocking item before Session 17 (GCP deploy). The current
per-play settlement model is correct in steady state but fragile under
real load — the demo run that surfaced this is documented in
`PLAN.md → Session 16.6` (search for "DISCOVERED WHEN LETTING THE AUTOPLAY").

---

## 0. How to use this doc

1. Read sections **1 (problem)** and **2 (target architecture)** end-to-end
   before any code. The shape change matters more than the line counts.
2. Section **3** lists existing committed work that this builds on — DON'T
   re-implement. Section **4** lists genuinely new code.
3. Sections **5 + 6** are the file-by-file change list and the gotchas.
   Both are load-bearing; missing a gotcha will cost you a debug cycle.
4. Section **9** (RPC switch) is a **prerequisite for testing** — without
   it the validation will look false-broken even with correct code.
5. Section **10** is the acceptance bar. Don't merge until those pass.

If anything in this doc disagrees with `PLAN.md` or `BACKEND-REVIEW.md`,
this doc is newer and wins; flag the disagreement in the work log when
closing the session.

---

## 1. The problem this solves

### Symptom
On 2026-04-28, after running auto-play for ~hours, an audit
(`scripts/audit_ledger.py`) showed two simultaneous drift signals:

```
Publisher  3pMCrwRq…V8W9    expected 1.9070 USDC  actual 1.9015  -0.0055 SHORT
Campaign   ac89a867…        expected 5.4205 USDC  actual 5.4260  +0.0055 DRIFT
```

11 plays' worth of USDC was stranded on the campaign wallet but the DB
said they'd been paid to the publisher. Initial diagnosis: pre-Session-16.5
network dedup damage (correct for that case).

A second drift event followed *after* the validation pass, with the
**opposite signature**: publisher had MORE on-chain than DB said, campaigns
had LESS. ~11 plays, exactly the inverse of the first.

### Why both drifts happen

Today's `execute_settlement` (in `backend/app/routers/proof.py`):

1. Atomic `UPDATE campaigns SET spent = spent + amount` (correct)
2. Privy `sign_and_send` — broadcasts tx
3. `wait_for_tx_confirmation(90s)` — polls Solana RPC every 1s
4. On wait timeout / exception: `get_signature_status` (γ_extra check)
5. If γ_extra returns `None` → compensate: roll back `spent`, write `failed` row

When auto-play burst-fires 10–20 settlements per tick, every settlement
runs step 3 concurrently → 10–20 RPC polls/sec → `api.devnet.solana.com`
returns 429s → wait sees only exceptions → step 4 hits the same RPC, also
gets 429 → returns `None` → step 5 compensates **even though the tx may
have actually landed on-chain**.

Result: tx lands, publisher gets paid, DB rolls back the spent. Drift in the
worst direction (publisher MORE, DB short).

### Why the per-play model is the wrong shape

- **RPC pressure scales with concurrency.** N concurrent settlements →
  N waits → N×poll_rate RPC calls. Public devnet RPC IP-rate-limits at
  unspecified-but-low thresholds.
- **Compensation defaults to "roll back on uncertainty."** That's the wrong
  default. Compensating creates the drift; doing nothing leaves the
  decision for later.
- **Per-tx fees** scale linearly with plays. On mainnet at $0.0001/tx and
  100k plays/day = $10/day in raw gas plus markup. The economic case for
  batching matches the correctness case.
- **Industry practice** (DOOH, RTB ad networks) accrues impressions and
  settles in batches. We were the outlier.

The fix is architectural, not a knob.

---

## 2. Target architecture

### Three settlement states

| Status | Meaning | tx_hash |
|---|---|---|
| `pending` | /proof accepted; queued for next batch flush | NULL |
| `confirmed` | Batch landed on-chain; this row is in that batch | Set to batch tx hash |
| `failed` | Batch definitively failed (Privy raised at simulation, or blockhash expired with no signature) | NULL |

### Hot path (`/proof`, `auto_play`, `simulate-play`)

1. Validate JWT, decode claims (unchanged)
2. Atomic `INSERT INTO used_nonces` (replay protection — unchanged)
3. **Atomic `UPDATE campaigns SET spent = spent + amount` with budget guard**
   — unchanged. Replay protection holds, budget overcommit prevented.
4. **NEW:** `INSERT INTO settlements (..., status='pending', tx_hash=NULL)`
5. **NEW:** Return immediately. No `build_usdc_transfer_tx`, no Privy call,
   no wait. Sub-100ms response.

### Background batcher (new — `services/batch_settler.py`)

Long-running task started in the FastAPI lifespan, similar to `auto_play.py`:

```
loop forever:
    sleep(BATCH_FLUSH_INTERVAL_SECONDS)        # default 10s
    rows = SELECT * FROM settlements WHERE status='pending' LIMIT BATCH_MAX
    groups = group_by(rows, key=(campaign_id, publisher_wallet))
    for group in groups:
        flush_group(group)
```

`flush_group(group)`:

1. Sum `amount_usdc` across the group (1 to N rows)
2. Build ONE `build_usdc_transfer_tx` from `campaign.wallet_address` →
   `publisher_wallet` for the summed amount, with memo
   `f"x402-batch:{first_nonce[:8]}-{count}"` (bytes-unique per batch)
3. Privy `sign_and_send_solana(reference_id=f"batch-{group_hash}")`
4. `wait_for_tx_confirmation(tx_hash, 90s)`
5. If confirmed: `UPDATE settlements SET status='confirmed', tx_hash=:tx WHERE id IN (group_ids)`
6. If wait fails:
   - Pre-compensation γ_extra check: `get_signature_status(tx_hash)`
   - If status in (processed, confirmed, finalized) → still mark all rows
     as `confirmed` (late-landed); skip compensation
   - Else if status is None (RPC blind): **leave rows as `pending`** for
     the next loop to retry. **DO NOT compensate.** This is the critical
     correctness rule.
   - Only compensate if Privy raised at simulation (definitive failure)
     or blockhash has demonstrably expired with no signature ever
     appearing.

### Refund flow (modified)

Today: `remaining = budget - spent` → send to advertiser → done.

In batch model, `spent` includes pending-but-not-yet-paid amounts. Two-step
refund:

1. **Drain pending settlements for this campaign first.** Call
   `batch_settler.flush_campaign(campaign_id)` synchronously — process all
   `pending` rows for this campaign through the batcher's flush logic.
2. **Then** compute `remaining = budget - spent` and send USDC refund.
3. Existing SOL sweep stays unchanged.

If pending flush fails for any reason (RPC down, etc.), refund must
**fail loudly**, not proceed. The advertiser can retry once batches
are caught up.

---

## 3. What stays from previous work (DO NOT re-implement)

These are committed in `26136a2` (Session 16.7) and the partially-committed
α + γ work from this morning. All still load-bearing:

| File / function | Why still relevant |
|---|---|
| `services/calc.required_sol_seed_lamports(total_plays)` | Campaign wallets still pay their own gas. Slightly over-provisions in batch model (way fewer txs); over-provision is safe; refund-time SOL sweep returns the unused. |
| `routers/campaigns.create_campaign` SOL seed wiring | Same. Don't touch. |
| `services/solana.wait_for_tx_confirmation` | Used by the batcher's flush per batch (was per-play, now per-batch). Same signature. |
| `services/solana.get_signature_status` | Used by batcher's γ_extra check. |
| `services/solana.get_sol_lamports` | Used by refund-time SOL sweep + audit. |
| `routers/campaigns.refund_campaign` SOL sweep block | Keep; runs after the new pending-flush + USDC refund. |
| `scripts/audit_ledger.py` | Needs minor extension (display pending count); core logic unchanged. |
| `scripts/sweep_to_treasury.py` | Unchanged. |
| `scripts/topup_campaigns.py` | Unchanged. |
| `scripts/cleanup_drift.py` | Useful one-shot for the existing drift (see §8). |
| Atomic budget UPDATE in `execute_settlement` (the SQL `UPDATE ... WHERE budget - spent >= amount` with compensating decrement on failure) | Core correctness. Keeps replay protection + budget guard. The compensating UPDATE only fires now when batcher determines definitive failure, not on every per-play wait timeout. |
| Memo on USDC transfers (`build_usdc_transfer_tx(memo=...)`) | Still required. Batch txs need bytes-uniqueness too if two campaigns batch to the same publisher in the same blockhash window. |
| `Settlement.device_id` column + DMA resolution | Unchanged. Each pending row carries it; aggregates work on it. |

### What moves location, same code

- `wait_for_tx_confirmation(90s)` — was inside `execute_settlement`'s
  per-play try/except. **Moves to `batch_settler.flush_group`.**
- γ_extra final-status check — was per-play; **moves to
  `batch_settler.flush_group`.**
- Compensating UPDATE — was per-play in `execute_settlement`. **Moves to
  `batch_settler.flush_group`** as a per-row decrement loop within a
  single transaction.

### What gets DELETED

- The per-play `wait_for_tx_confirmation` call in `execute_settlement`
  (proof.py around line 158-172 in the post-α code). The hot path is no
  longer responsible for waiting.
- `execute_settlement`'s `tx_hash`/`late_landed` block (proof.py around
  lines 142-225 post-α) collapses dramatically — replaced by writing a
  pending row.

---

## 4. What's new

- `Settlement.status` enum: add `'pending'` value (Python enum + DB)
- `Settlement.created_at` already exists; ensure it's indexed for
  efficient `WHERE status='pending' ORDER BY created_at` scans (likely
  already the case via Session 16.7 migration).
- `services/batch_settler.py` — new file, the batching loop
- `app/main.py` lifespan — start the batcher loop alongside auto_play
- `routers/proof.execute_settlement` — drop the on-chain call, write
  pending row, return
- `routers/campaigns.simulate_play` — same change (it shares
  `execute_settlement`)
- `app/services/auto_play._settle_one` — same (it calls
  `execute_settlement`)
- `routers/campaigns.refund_campaign` — flush pending first
- `app/config.py` — new settings: `BATCH_FLUSH_INTERVAL_SECONDS=10`,
  `BATCH_MAX_ROWS_PER_FLUSH=100`, `BATCH_ENABLED=true`
- `schemas.SettlementSummary` — `status` already string-typed, no schema
  change beyond accepting the new value
- Frontend: see §7

---

## 5. File-by-file change list

### Backend

#### `backend/app/models.py`
- `SettlementStatus` enum: add `PENDING = "pending"`
- No DB migration needed (status is a free-form String column)

#### `backend/app/services/calc.py`
- **No change.** `required_sol_seed_lamports` formula stays. (Slightly
  over-provisions in batch model; safe.)

#### `backend/app/services/batch_settler.py` *(NEW)*
- Module structure mirrors `auto_play.py` (lifespan task, single source
  of state, opens its own DB session, log on every batch outcome).
- Public API:
  - `async def run_batch_settler_loop(stop_event: asyncio.Event)` —
    started in lifespan
  - `async def flush_campaign(campaign_id: str) -> FlushResult` —
    synchronous flush for a single campaign, called by refund handler
  - `async def flush_all() -> FlushResult` — what the loop calls each tick
- Internal helpers:
  - `_pick_pending_rows(db, limit)` — `SELECT ... WHERE status='pending'
    ORDER BY created_at LIMIT :limit` with `FOR UPDATE SKIP LOCKED` if
    Postgres (SQLite ignores). For now SQLite, but write the query so
    Postgres semantics work.
  - `_group_by_target(rows)` — return `dict[(campaign_id, publisher_wallet)] -> list[Settlement]`
  - `_flush_group(privy, db, group)` — implements the flush algorithm
    described in §2
- Flush group's `try/except`:
  - Build USDC tx with memo `f"x402-batch:{group[0].nonce[:8]}-{len(group)}"`
  - `reference_id = f"batch-{campaign_id[:8]}-{group[0].nonce[:8]}"`
    — gives Privy idempotency for backend-side retries (different
    `reference_id` per group; same group rebuilt across loop ticks
    yields same `reference_id` → Privy returns same tx hash if it
    already broadcast, no double-broadcast)
  - `wait_for_tx_confirmation(tx_hash, 90s)`
  - On confirm: `UPDATE settlements SET status='confirmed', tx_hash=:tx
    WHERE id IN (group_ids)` in one statement.
  - On wait failure:
    - Call `get_signature_status(tx_hash)`
    - If status in (processed, confirmed, finalized) → mark confirmed
      (same UPDATE)
    - **Else (status is None — RPC blind or signature truly absent):
      LEAVE ROWS AS PENDING.** Log warning. Next loop will retry.
    - Compensate ONLY if Privy raised at simulation (`PrivyError` with
      `transaction_broadcast_failure` and detail mentioning simulation
      / rent / etc.) OR if `bt > BLOCKHASH_DEFINITIVELY_DEAD_THRESHOLD`
      seconds have elapsed since the row's `created_at` AND
      `get_signature_status` returns None across multiple checks
      (don't add this multi-check yet — leave-as-pending is the safe
      v1).

#### `backend/app/routers/proof.py`
- `execute_settlement`:
  - Keep nonce insert + atomic budget UPDATE blocks.
  - **Replace** the entire `try/except` around `build_usdc_transfer_tx`
    + `sign_and_send_solana` + wait + late-landing logic with:
    ```python
    # Queue for batch settlement. The batcher flushes pending rows
    # every BATCH_FLUSH_INTERVAL_SECONDS, grouping by (campaign,
    # publisher) and emitting one Solana tx per group.
    db.add(_settlement_row(
        campaign_id=campaign.id,
        nonce=claims.nonce,
        publisher_wallet=claims.wallet_id,
        amount_usdc=claims.amount_usdc,
        tx_hash=None,
        status_value=SettlementStatus.PENDING.value,
        device_id=claims.device_id,
    ))
    db.commit()
    return None  # no tx_hash at /proof time
    ```
  - Return type changes from `str` (tx_hash) to `None` or
    `Settlement` (return the row so the caller has the id). Update
    callers accordingly.
- `proof()` handler:
  - `ProofResponse` no longer has a `tx_hash`. Replace with
    `settlement_id` and `status` fields.
  - Don't call `_solscan_tx_url(tx_hash)` since there's no hash yet.

#### `backend/app/routers/campaigns.py`
- `simulate_play`: returns from `execute_settlement` change — adapt
  `SimulatePlayResponse` to match new shape (no `tx_hash`/`solscan_url`
  at request time; return `settlement_id` and `status='pending'`
  instead).
- `refund_campaign`: **insert a flush step before the existing refund
  logic.**
  ```python
  from ..services.batch_settler import flush_campaign

  # Drain any pending settlements first so `spent` reflects everything
  # owed; otherwise we'd refund USDC that's still committed to publishers.
  flush_result = await flush_campaign(campaign_id, privy=privy, db=db)
  if flush_result.failures:
      raise HTTPException(
          status_code=503,
          detail="pending settlements failed to flush; retry refund shortly",
      )
  # ... existing logic continues from here
  c = _owned_campaign(...)  # re-load post-flush
  remaining = float(c.budget) - float(c.spent)  # now accurate
  ```

#### `backend/app/services/auto_play.py`
- `_settle_one`: same change as proof — calls `execute_settlement` which
  now returns None/Settlement. Update its log line and don't expect a
  tx_hash to log.

#### `backend/app/main.py`
- Lifespan: start `run_batch_settler_loop` task alongside the auto-play
  loop. Both should share a stop event for clean shutdown.

#### `backend/app/config.py`
- Add settings:
  ```python
  batch_enabled: bool = True
  batch_flush_interval_seconds: int = 10
  batch_max_rows_per_flush: int = 100
  ```
- `batch_enabled=False` for tests (e.g., `e2e_demo.py`) where you want
  per-call deterministic behavior.

#### `backend/scripts/e2e_demo.py`
- Update for the new shape. Two options:
  - (a) Disable batching (`BATCH_ENABLED=false`) and add a
    synchronous `flush_all()` call after each /proof to settle on-chain.
  - (b) Keep batching enabled and add explicit `flush_all()` waits at
    each on-chain assertion.
- (a) is simpler — recommend that. Set
  `os.environ["BATCH_ENABLED"] = "false"` at top of the script (same
  pattern as `AUTO_PLAY_ENABLED`).
- The "drained tiny campaign in 2 plays" test step needs a synchronous
  flush after each /proof or it'll hang waiting for the budget to
  visibly drain.

#### `backend/scripts/audit_ledger.py`
- Add a column for `pending` count per campaign. Surface a soft
  diagnostic: campaigns with > 0 pending are not "drift" — they're
  in-flight. Don't flag DRIFT for them; flag a separate `IN-FLIGHT`
  marker instead.
- Publisher reconciliation: sum confirmed only (already does). Pending
  is excluded from the expected total — those settlements haven't been
  paid yet.

#### `backend/app/schemas.py`
- `SettlementSummary`: `status` already string; no enum-tightening
  needed. Frontend cares; backend does not.
- `ProofResponse` / `SimulatePlayResponse`: `tx_hash` becomes optional
  (now `str | None`), add `status: str`. Existing consumers tolerate
  null tx_hash already.

### Frontend

See §7 for UI shape; here just the schema-touching changes:

- `lib/aggregations.ts` — `SettlementRow.status` adds `'pending'` as a
  valid string. Already typed as `string` so likely no change.
- `lib/api.ts` — no change.

---

## 6. Edge cases and gotchas

### 6.1 Solana tx size limit (1232 bytes)
A single SPL-Token `transfer_checked` instruction is ~200 bytes. The
batch tx pattern is **one transfer per (campaign, publisher) group**
— always exactly one transfer in the tx. Tx size will never approach
the limit. Don't worry about packing multiple transfers in one tx
across publishers — different design, more complexity, no need.

### 6.2 Privy `reference_id` semantics
Reference: `BUSINESS-CONSTRAINTS.md §3` and Session 9 findings in PLAN.md.
Privy's `reference_id` provides post-broadcast idempotency. Use a
deterministic key per group:
```
reference_id = f"batch-{campaign_id[:8]}-{first_nonce[:8]}"
```
If the loop tick fires the same group twice (e.g., process restart),
Privy returns the same tx hash without re-broadcasting. **Important:**
the `first_nonce[:8]` is what makes this deterministic across retries
of the same group — sort the group's rows by `created_at` first so the
"first" is stable.

### 6.3 Backend dies mid-flush
Three scenarios:
1. Tx broadcast, signature returned, backend crashes before DB UPDATE:
   Pending rows stay pending. Next loop picks them up, re-builds the
   group, re-broadcasts with same `reference_id` → Privy returns same
   tx hash → wait succeeds → DB now updates correctly. **Idempotency
   carries us.**
2. Tx broadcast, wait succeeds, DB UPDATE half-applied: SQLite-level
   atomicity protects this — the UPDATE is one statement, all-or-nothing.
3. Tx never broadcast (Privy raised at simulation), backend crashes
   before compensation: Pending rows stay pending. Next loop retries.
   If the wallet's state hasn't changed, the tx will broadcast this
   time (memory pressure, brief RPC blip, etc.).

The system is self-healing as long as `pending` is the default state
on uncertainty.

### 6.4 Refund concurrent with batch flush
Refund handler calls `flush_campaign(campaign_id)` synchronously. The
background loop's `flush_all()` may also be processing the same
pending rows. Race window if both pick the same row:
- Both build the same tx (same group, same `reference_id` → Privy
  returns same hash from both)
- Both wait, both succeed, both do the UPDATE
- UPDATE is idempotent (`SET status='confirmed', tx_hash=:tx` on
  already-confirmed rows is a no-op)
- No drift

If we want to avoid the wasted Privy call: use SQLite's
`UPDATE settlements SET status='flushing' WHERE id IN (...) AND status='pending' RETURNING id`
to atomically claim rows. Postgres `FOR UPDATE SKIP LOCKED` is the
production version. For SQLite hackathon scope, the idempotent
double-flush is acceptable.

### 6.5 Pending rows with same campaign, same publisher, but different blockhash windows
Doesn't matter. The batcher groups by `(campaign_id, publisher_wallet)`
and sums the amount. The summed amount goes to the publisher in one
USDC transfer. Each input row gets the same `tx_hash` on confirm.

### 6.6 The atomic budget UPDATE is still per-/proof, not per-batch
This is critical. Budget reservation must happen at /proof time so
budget overcommit is impossible. `pending` rows carry the reserved
budget; failed batches release it via the compensating UPDATE.

### 6.7 The `must-fix #1 budget overcommit` is partially fixed but not fully
PLAN.md must-fix #1 says we mint unlimited proof_context JWTs at /bid.
Batch settlement doesn't change that. Out of scope for this session.

### 6.8 Stale RPC reads (devnet quirk)
After a confirmed batch tx, balance reads may lag for a few seconds.
Audit script and refund's SOL sweep should tolerate this — both
already do (`get_usdc_balance` falls through to 0 on error; sweep is
best-effort).

### 6.9 Frontend cache invalidation
Today the campaign card polls `/api/campaigns/:id/stats` every 5s.
With pending rows, the user sees:
- Plays counter ticks immediately on /proof (pending counts)
- Settlements row appears with "queued" status, no Solscan link
- After flush (~10-15s), row updates to "confirmed", Solscan link
  appears
React Query's polling handles this without explicit invalidation.

### 6.10 `protocol_fee_amount` transfer at activation
Today's flow: x402 settle → fee transfer (best-effort, Privy direct
call). This is NOT a /proof; it's its own thing. Don't batch it.
Single tx per campaign activation, fine as-is.

---

## 7. UI changes (Frontend)

Goal: surface the new pending state without imposing the batch model
on advertisers' mental model.

### 7.1 Recent settlements table (`CampaignCard.tsx`)
- Each row remains one play (one Settlement DB row). Don't roll up to
  batches.
- Add a small **status pill** to the left of the row content:
  - `pending` → small clock icon + "queued" label, muted color
  - `confirmed` → existing green dot
  - `failed` → existing red indicator
- For pending rows, the Solscan tx hash column is empty (just em-dash).
  When the batch flushes, the row updates to confirmed and the link
  appears.

### 7.2 Batch summary strip (above the table) *(optional, recommended)*
A thin one-liner above the recent settlements table:
```
Last batch: 5 plays · 0.0025 USDC · 2 minutes ago · [tx 3kd9…ZTF]
```
Computed by: most recent confirmed row's `tx_hash`, count rows sharing
that hash, sum their amounts.

Skip if scope is tight; the per-row status pill is the must-have.

### 7.3 Live activity map (`LiveActivityMap.tsx`)
Today the per-DMA counter ticks on `confirmed` (via `plays_by_dma`).

**Change: tick on pending + confirmed combined.** Map is showing plays
that happened (the ad ran), not money that moved on-chain. Settlement
state is implementation detail; the play happened the moment /proof
returned.

Backend change to support this: `campaign_stats.plays_by_dma` SQL
aggregate filter changes from
`status='confirmed'` to `status IN ('pending', 'confirmed')`.

### 7.4 Stats counters
- `total_plays` — count pending + confirmed (fail excluded)
- `last_24h_plays` — same
- `total_confirmed_usdc` — confirmed only (this measures money moved
  on-chain, not plays accumulated)

Add a new field to `CampaignStats`:
- `pending_plays: int` — count of pending rows. Surface as a small
  "N queued" indicator on the campaign card if > 0.

### 7.5 Activity feed (`Overview.tsx`)
Already pulls recent settlements across campaigns. Same status pill
treatment. Newly-arriving pending rows trigger the row-flash animation
just like confirmed rows do today (`useFlashOnArrival` hook).

### 7.6 Wizard
No change. Funding flow is unaffected by batching.

---

## 8. Existing drift to clean up

There are TWO drift artifacts in the system as of 2026-04-28 evening:

### 8.1 Pre-Session-16.5 dedup (already cleaned)
Campaign `2fc2e504` had +0.031 USDC stranded → cleaned via earlier
`cleanup_drift.py` run. Done. Don't re-run.

### 8.2 RPC-rate-limit drift from this morning (FRESH — needs cleanup)
After we shipped the α + γ_safe + γ_extra package and ran auto-play,
the RPC choke caused ~11 plays to be:
- Confirmed on-chain (publisher got paid)
- Marked `failed` in DB (compensating UPDATE rolled back spent)

Audit signature:
```
publisher  3pMCrwRq…V8W9    +0.0055 MORE
campaign  c298e3bc        -0.0030 DRIFT
campaign  ac89a867        -0.0025 DRIFT
```

(`-0.0030 + -0.0025 = -0.0055 = +0.0055 publisher MORE` — the math
matches.)

**Cleanup option (recommended):** before the new code lands, run
`scripts/cleanup_drift.py` reverse-style — send 0.0055 USDC from
publisher → treasury (or back to one of the campaigns). The publisher
got paid for plays we now have no DB record of; reclaiming the USDC
brings the audit back to zero.

Alternative: insert phantom-confirmed Settlement rows in the DB to
match the on-chain state (more correct accounting; more code). Skip
for hackathon scope.

**Validation after cleanup:** `audit_ledger.py` should show zero
DRIFT, zero SHORT, zero MORE before the new batch code begins
processing.

### 8.3 Sponsorship probe artifact
The sponsorship probe (now in `scripts/probe_sponsorship.py`) sent
0.0005 USDC from `c298e3bc` → publisher. Already reversed via the
inline cleanup snippet I ran. Don't re-run.

---

## 9. RPC switch (PREREQUISITE for testing)

`https://api.devnet.solana.com` IP-rate-limits aggressively and is the
proximate cause of the drift. **Switch before any validation.**

Options (free tier sufficient):
- **Helius** — `https://devnet.helius-rpc.com/?api-key=KEY` (free
  100k req/day, ~10 req/sec sustained)
- **QuickNode** — free tier
- **Alchemy** — free tier

User action required:
1. Sign up, get API key
2. Update `SOLANA_RPC_URL` in `backend/.env`
3. `docker compose up -d --force-recreate backend`

Without this switch, the batcher's wait+poll will hit the same wall.
Don't try to validate batch correctness on the public RPC.

The code itself is RPC-agnostic; only the env var changes.

---

## 10. Acceptance / validation

Don't merge until ALL pass:

### 10.1 Mechanical
- [ ] `docker compose run --rm backend python scripts/e2e_demo.py` →
      13/13 pass with batching enabled (or with the explicit `flush_all()`
      shim in the script).
- [ ] `tsc -b --noEmit` clean on frontend.
- [ ] Backend boots without errors. The batcher loop log line appears.

### 10.2 Drift cleanup
- [ ] Existing 0.0055 USDC drift cleaned (publisher → treasury or
      similar). `audit_ledger.py` shows zero DRIFT/SHORT/MORE before
      validation begins.

### 10.3 Soak test
With private RPC enabled:
- [ ] 3 active campaigns targeting different DMAs, auto-play running
- [ ] Run for at least 30 minutes (at default 10s flush interval, ~180
      batches)
- [ ] Pause campaigns, wait 30s for in-flight to clear
- [ ] `audit_ledger.py` returns:
  - Publisher: zero SHORT (every confirmed settlement actually paid
    on-chain)
  - Campaigns: zero DRIFT (or in-flight rows under tolerance)
  - No phantom-confirmed rows (every `confirmed` row's tx_hash exists
    on-chain — spot-check 5 random rows on Solscan)

### 10.4 Refund flow
- [ ] On a campaign with pending settlements, hit refund. The handler
      should flush pending first, then refund the correctly-reduced
      remainder.
- [ ] Audit after refund: zero drift on that campaign, advertiser
      received exactly `budget - spent_after_flush`.

### 10.5 Frontend smoke
- [ ] Open an active campaign card; auto-play firing in the background.
      Settlements appear with "queued" pill; transition to confirmed
      with Solscan link within ~15s.
- [ ] Live activity map ticks on pending (immediate visual feedback,
      no 10s lag).
- [ ] Stats counters reflect pending + confirmed correctly.

### 10.6 Restart resilience
- [ ] With pending rows in the DB, `docker compose restart backend`.
- [ ] On boot, the batcher picks up the pending rows on its next tick.
- [ ] No data loss; no double-broadcast (Privy `reference_id`
      idempotency proves itself).

### 10.7 Cross-document consistency
- [ ] PLAN.md Session 16.6 checkboxes filled in
- [ ] PLAN.md must-fix #2 (already validated) keeps its "validated"
      footer
- [ ] BACKEND-REVIEW.md §1.1 + §1.2 cross-refs updated if applicable
- [ ] Work log entry added for this session
- [ ] RUNBOOK.md gains a "Batch settlement (operations)" section
      covering: how to monitor pending count, how to manually trigger
      flush, how to disable batching for E2E testing, and the
      flush-on-refund property.

---

## 11. Reference links

- `PLAN.md → Session 16.6` — bug discovery + the failed α + γ
  iteration (DO NOT roll back; that work is the foundation here)
- `PLAN.md → must-fix before mainnet § 1, 2, 3, 4` — related but
  distinct correctness items
- `BACKEND-REVIEW.md § 1.1` — refund leak (orthogonal but related)
- `BACKEND-REVIEW.md § 1.2` — race on `campaigns.spent` (already
  fixed; the fix carries through to batch model)
- `BUSINESS-CONSTRAINTS.md § 3, § 7.14` — Privy `reference_id`
  retry-safety
- `RUNBOOK.md → Audit reconciliation, Hygiene reset` — operational
  procedures, all still valid
- Recent commits relevant to this work:
  - `26136a2` — Session 16.7 + validation pass (the foundation)
  - Anything after that on `main` — the α + γ partial work, may or
    may not be committed when you start; check `git log` and `git status`

---

## 12. Risks / open questions worth flagging on close-out

1. **Mainnet gas billing semantics** — Privy's gas sponsorship blog
   says billing flows through Privy's system on mainnet. Devnet is
   free. Document the cost model in BUSINESS-CONSTRAINTS or
   PLAN.md-resolved-decisions when this lands. Not a blocker for
   hackathon.
2. **Batch flush interval tuning** — 10s is a guess. Demo feel may
   want 5s. Production probably wants 30-60s. Make it env-configurable
   (already specified).
3. **Pending row retention** — old pending rows that genuinely never
   resolve (Privy down for hours, etc.) need an operator playbook.
   For v1, just log them; ops can investigate. v2 could add a
   "definitively dead" promotion path after BLOCKHASH_GRACE_SECONDS.
4. **Atomicity vs SQLite** — the batch UPDATE
   `WHERE id IN (group_ids)` works at SQLite scale. On Postgres
   (Session 17), `FOR UPDATE SKIP LOCKED` becomes preferred for the
   pick step.

End of brief.
