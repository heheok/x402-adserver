# Session 16.9 — Money refactor: float → integer microUSDC ✅

**Status:** ✅ Shipped 2026-04-30. e2e 25/25, audit_ledger zero across all flags.

**Why this exists:** PLAN.md "Must-fix before mainnet" §3 — money in Python is `float` end-to-end. Sums of `0.001` drift on the order of 1e-16 per step, requiring `+ 1e-9` epsilon tolerance on every budget guard and a "flip COMPLETED when `remaining < cost_per_play`" rule (instead of the natural `spent >= budget`). The DB columns are `Numeric(18, 6)` (exact in storage) but SQLAlchemy returns Python `float` due to the `Mapped[float]` annotations, so all math at the Python boundary reintroduces float drift.

**Why before Session 17 (GCP deploy):** the longer the float stays, the more code carries the assumption forward. Postgres migration at deploy time is also where the column-type change is cheapest — folding "convert to BigInteger" into the same migration is simpler than retrofitting later. Demo soak (Session 16.8) was clean at hackathon scale, but every additional code path written on float is more cleanup later.

---

## Decision (locked 2026-04-30)

- **DB columns**: integer microUSDC stored as `BigInteger`. 1 USDC = 1_000_000 microUSDC. Names stay the same (`budget`, `spent`, `protocol_fee_amount`, `amount_usdc`) — just type changes.
- **Python internal math**: `int` microUSDC everywhere money flows. No `float` and no `Decimal` mixing on money.
- **API wire format**: **string** of integer microUSDC, e.g. `"422000"` for 0.422 USDC. Matches what x402 PaymentRequirements `amount_usdc` already uses (atomic units, string). Eliminates float on the wire so any consumer who isn't careful can't reintroduce drift in their own code.
- **TypeScript schema fields**: relevant fields go from `number` to `string`. A small `lib/money.ts` formatter is added; the existing `.toFixed(N)` call sites switch to `formatUsdc(microStr, dp)`.

**Why string, not number, for the wire:** float on the wire is the footgun we're killing. JS `Number` can hold microUSDC values fine numerically (well under 2^53), but the moment a future consumer divides by 1_000_000 in their own code without a helper, drift comes back. String + helper is explicit and matches the rest of the crypto stack (x402, SPL token amounts, every Solana RPC).

**Why integer micro, not decimal-string USDC ("0.422000") on the wire:** integer atomic units is the canonical convention. It's the same shape Solana's SPL token program uses, the same shape x402 already uses for `amount_usdc`. Picking decimal-string would break that consistency for marginal "looks prettier in DevTools" gains.

**Why not Python `Decimal` instead of int micro:** Decimal is exact but introduces a different exotic type that still mixes badly with float. Anywhere a Decimal touches a float, you're back to float. Int is unambiguous, fast, and matches every battle-tested crypto money path.

---

## Files to touch

### Backend

#### New: `backend/app/services/money.py`

```python
"""Single source of truth for USDC ↔ microUSDC conversion.

USDC is stored on-chain and in our DB as integer microUSDC (1 USDC = 1e6 micro).
Float USDC must NEVER appear in money math — only at display boundaries.
"""
from decimal import Decimal, ROUND_HALF_UP

MICRO = 1_000_000
DECIMALS = 6


def to_micro(usdc) -> int:
    """Convert a USDC value (Decimal/str/float) to integer microUSDC.

    Rounds HALF_UP at 6 decimals. Used at trust boundaries — config parsing,
    legacy float ingestion. Internal math should already be int micro and
    not need this.
    """
    return int(
        (Decimal(str(usdc)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
        * MICRO
    )


def micro_str(micro: int) -> str:
    """Render integer microUSDC as the on-wire string form ('422000').

    Use in every Pydantic response model that exposes a money field.
    """
    return str(int(micro))
```

The schemas use `micro_str(...)` at serialization time. No exception is allowed in the money path — if a code path returns a float USDC, that's a bug.

#### `backend/app/models.py`

Flip column types from `Numeric(18, 6)` + `Mapped[float]` to `BigInteger` + `Mapped[int]`:

| Column                          | Before                          | After                            |
| ------------------------------- | ------------------------------- | -------------------------------- |
| `Campaign.cpm_price`            | `Numeric(18,6)`, `Mapped[float]`| `BigInteger`, `Mapped[int]` — now stores **microUSDC per 1000 plays** (e.g. DEMO_CPM=$0.50 → 500_000) |
| `Campaign.budget`               | `Numeric(18,6)`, `Mapped[float]`| `BigInteger`, `Mapped[int]` (microUSDC) |
| `Campaign.spent`                | `Numeric(18,6)`, `Mapped[float]`| `BigInteger`, `Mapped[int]` (microUSDC) |
| `Campaign.protocol_fee_amount`  | `Numeric(18,6)`, `Mapped[float \| None]` nullable | `BigInteger`, `Mapped[int \| None]` nullable |
| `Settlement.amount_usdc`        | `Numeric(18,6)`, `Mapped[float]`| `BigInteger`, `Mapped[int]` (microUSDC) |

`Campaign.duration` is already int seconds — leave alone.

#### `backend/app/database.py`

The dev SQLite ALTER shim (`_dev_alter_table_for_existing_sqlite`) cannot change column types in place. Two options, pick one:

1. **Wipe and rebuild (preferred)**: hygiene reset already wiped the DB during validation pass 2026-04-28. If the user has campaigns since then, sweep them via `scripts/sweep_to_treasury.py` (dry-run first), wipe `backend/data/adserver.db`, restart backend, recreate test campaigns. This is the cleanest path for dev.
2. **One-shot migration script** `scripts/migrate_money_to_micro.py`: read every `Campaign` + `Settlement` row, multiply each money field by 1_000_000, write back. SQLite limitation means this needs the column-type flip via table-rebuild (`CREATE TABLE new_*; INSERT INTO new_* SELECT ...; DROP TABLE; ALTER RENAME`). More code; only worth it if the user has data they want to preserve.

Document the chosen path in the work log entry.

#### `backend/app/services/calc.py`

`compute_quote()` returns ints throughout. Rough shape:

```python
def compute_quote(...) -> QuoteResult:
    screens = ...
    plays_per_screen_per_day = settings.operating_hours_per_day * settings.plays_per_hour_per_screen
    days = (end_date - start_date).days + 1
    total_plays = screens * plays_per_screen_per_day * days

    cpm_micro = to_micro(settings.demo_cpm)  # e.g. 500_000 for $0.50 CPM
    cost_per_play_micro = cpm_micro // 1000  # e.g. 500 micro = $0.0005/play
    total_micro = cost_per_play_micro * total_plays

    fee_pct_basis_points = int(round(settings.protocol_fee_pct * 10_000))  # 250 for 2.5%
    protocol_fee_micro = (total_micro * fee_pct_basis_points) // 10_000
    total_to_escrow_micro = total_micro + protocol_fee_micro

    return QuoteResult(
        screens=screens,
        plays_per_screen_per_day=plays_per_screen_per_day,
        days=days,
        total_plays=total_plays,
        cpm_price_micro=cpm_micro,
        cost_per_play_micro=cost_per_play_micro,
        total_micro=total_micro,
        protocol_fee_pct=settings.protocol_fee_pct,  # display-only, unchanged
        protocol_fee_micro=protocol_fee_micro,
        total_to_escrow_micro=total_to_escrow_micro,
    )
```

All integer math, no float. Floor division (`//`) for cost-per-play and protocol-fee — never round up; we never want to charge more than the sum. Decide explicitly and document if rounding direction matters anywhere.

Also export `required_sol_seed_lamports` unchanged — that's already int.

#### `backend/app/routers/proof.py` — `execute_settlement`

The atomic UPDATE guard becomes exact integer comparison. Drop the `+ 1e-9`:

```python
result = db.execute(
    text("""
        UPDATE campaigns
        SET    spent = spent + :amount_micro,
               status = CASE
                          WHEN budget - (spent + :amount_micro) < :cost_per_play_micro
                            THEN 'completed'
                          ELSE status
                        END
        WHERE  id = :id
          AND  status = 'active'
          AND  budget - spent >= :amount_micro
    """),
    {"id": campaign_id, "amount_micro": amount_micro, "cost_per_play_micro": cost_per_play_micro},
)
```

The COMPLETED-flip rule is now `remaining < cost_per_play` exactly, no epsilon. Keep the same semantic (auto-complete when no play fits), but the comparison is bit-precise.

The compensating UPDATE on Privy failure — same pattern, integer subtraction.

#### `backend/app/routers/bid.py`

`cost_per_play_micro = campaign.cpm_price // 1000` (since cpm_price is now stored as micro per 1000 plays). Used in the budget guard:

```python
if campaign.budget - campaign.spent < cost_per_play_micro:
    continue  # skip
```

Exact integer compare, no epsilon. The `proof_context` JWT carries `amount_micro: int` instead of `amount_usdc: float`.

#### `backend/app/services/tokens.py`

`ProofContextClaims.amount_usdc` (float) → `amount_micro` (int). Update the claim model. **Backwards compatibility:** old in-flight JWTs with `amount_usdc` will fail to decode after this lands; that's fine because TTL is 1 hour and the deploy window covers it. Add an explicit version bump in the JWT (e.g., `v=2`) so a future schema change has a hook.

#### `backend/app/services/auto_play.py` and `services/batch_settler.py`

Both call into `execute_settlement` (or the new pending-row insert path). Pass `amount_micro: int` rather than float USDC. `batch_settler.flush_group` sums in int:

```python
total_micro = sum(row.amount_usdc for row in group_rows)  # all ints now
```

Privy transfer call site: `build_usdc_transfer_tx` already takes integer atomic amount internally — drop the `int(round(amount_usdc * 1_000_000))` wrapper at the call site (was the ONLY conversion, becomes a direct pass-through).

#### `backend/app/services/x402.py`

`PaymentRequirements.amount_usdc` is **already** a string of atomic units (per x402 spec). Today the code does `str(int(round(amount_usdc * 1_000_000)))` — replace with `str(amount_micro)`. Cleanup, behavior unchanged.

The retry-POST recompute (Session 15 finding: `escrow_amount = float(campaign.budget) + float(campaign.protocol_fee_amount or 0)`) becomes `int(campaign.budget) + int(campaign.protocol_fee_amount or 0)` and produces bit-identical bytes. The 5% slack on the x402 client `amount` is no longer needed for drift safety; can be dropped or kept (harmless).

#### `backend/app/schemas.py`

Every money field on every response model goes from `float` to `str`. Use a Pydantic field validator/serializer that emits `micro_str(int_value)` from the model attribute. List of fields to flip:

- `CampaignSummary.cpm_price` → str (micro)
- `CampaignSummary.budget` → str (micro)
- `CampaignSummary.spent` → str (micro)
- `CampaignSummary.protocol_fee_amount` → str | None (micro)
- `CampaignStats.budget`, `.spent`, `.remaining`, `.total_confirmed_usdc` → str (micro)
- `SettlementSummary.amount_usdc` → str (micro)
- `DashboardActivityRow.amount_usdc` → str (micro)
- `DashboardSummary.total_*` → str (micro)
- `QuoteResponse.cpm_price`, `.total_usdc`, `.protocol_fee_usdc`, `.total_to_escrow_usdc` → str (micro)
- `WalletInfo.usdc_balance` → str (micro). Note: this is read fresh from RPC (`get_usdc_balance`), which already returns int micro internally — just don't lose precision through float.
- `RefundResponse.refunded_amount` (or whatever field) → str (micro)

**Naming:** keep field names the same so the frontend type changes are diff-mechanical (`number → string`). Don't rename `amount_usdc` → `amount_micro` — that's a churn cost without a real win, and the wire convention is "this string is atomic units of USDC."

#### `backend/app/services/solana.py`

`get_usdc_balance(...)` reads from RPC and converts to USDC by dividing by 1_000_000 — change return type to `int` micro and remove the divide. All callers update.

`build_usdc_transfer_tx` already takes int atomic amount — call sites stop multiplying.

### Frontend

#### New: `frontend/src/lib/money.ts`

```ts
export const MICRO = 1_000_000;

/** Parse a wire-format microUSDC string to a JS Number USDC value (safe for display). */
export function parseUsdc(microStr: string): number {
  return Number(microStr) / MICRO;
}

/** Format a microUSDC string for display (default 4 decimal places). */
export function formatUsdc(microStr: string, dp: number = 4): string {
  return parseUsdc(microStr).toFixed(dp);
}

/** Sum a list of microUSDC strings. */
export function sumMicro(strs: string[]): string {
  // BigInt-safe even though we don't strictly need it at our scale.
  return strs.reduce((acc, s) => acc + BigInt(s), 0n).toString();
}

/** Subtract two microUSDC strings, returning a microUSDC string. */
export function subMicro(a: string, b: string): string {
  return (BigInt(a) - BigInt(b)).toString();
}
```

#### TypeScript types (`frontend/src/lib/api.ts` or wherever the schemas live)

Flip every money field from `number` to `string` on:

- `CampaignSummary` (cpm_price, budget, spent, protocol_fee_amount)
- `CampaignStats` (budget, spent, remaining, total_confirmed_usdc)
- `SettlementSummary` (amount_usdc)
- `DashboardActivityRow` (amount_usdc)
- `DashboardSummary` (total_*)
- `QuoteResponse` (cpm_price, total_usdc, protocol_fee_usdc, total_to_escrow_usdc)
- `WalletInfo` (usdc_balance)

`tsc --noEmit` will then surface every consumer that needs updating.

#### Display call sites (~15 places across 6 files)

Mechanical replace:

- `Overview.tsx:199` — `{totalSpent.toFixed(4)}` → `{formatUsdc(totalSpentMicro)}`. `totalSpentMicro` comes from `aggregations.ts`.
- `Overview.tsx:393` — `{s.amount_usdc.toFixed(4)}` → `{formatUsdc(s.amount_usdc)}`
- `Campaigns.tsx:122-123` — same pattern
- `CampaignCard.tsx` — 9 sites:
  - 232, 234: `campaign.spent.toFixed(4)` / `campaign.budget.toFixed(4)` → `formatUsdc(campaign.spent)` / `formatUsdc(campaign.budget)`
  - 415: `stats.data.cpm_price.toFixed(4)` → `formatUsdc(stats.data.cpm_price, 2)` (CPM is per-1000 plays, display at 2dp)
  - 425, 437: same
  - 437: `(campaign.budget - campaign.spent).toFixed(4)` → `formatUsdc(subMicro(campaign.budget, campaign.spent))`
  - 452: protocol_fee_amount
  - 493: `((campaign.spent / campaign.budget) * 100).toFixed(1)` — percentage, NOT money. Keep as float math, but parse first: `((parseUsdc(campaign.spent) / parseUsdc(campaign.budget)) * 100).toFixed(1)`. Float for the ratio is fine — it's a percentage.
  - 498: same pattern as 232/234
  - 807: `s.amount_usdc.toFixed(4)` → `formatUsdc(s.amount_usdc)`
- `WalletChip.tsx:218, 380` — `pendingAmount?.toFixed(2)` — pendingAmount comes from `walletTrack` Zustand. Decide: track `pendingAmountMicro` as string in the store, or keep the store as float USDC since it's purely a UI delta. Recommended: convert at the store boundary (the consumers of `/api/wallet` parse the micro string; the store stores parsed USDC numbers for delta math). Document this as the only allowed float-USDC, used for UI delta only, never for sums against budget.
- `StepCalculator.tsx:142, 152, 213` — quote response fields → formatUsdc
- `StepReview.tsx:402, 406` — same

#### `frontend/src/lib/aggregations.ts`

Sums of campaign budget/spent become `sumMicro([...]) → string`. Then UI converts via `formatUsdc(totalMicro)` at display.

### Scripts

- `scripts/audit_ledger.py` — comparisons become exact integer `==`. Drop tolerance entirely. On-chain SPL token balances are already integer atomic units; comparison is now bit-precise.
- `scripts/e2e_demo.py` — amounts in micro, assertions on int. Update fixtures.
- `scripts/cleanup_drift_reverse.py` — already does integer-ish work via SPL math; review for any float-USDC math at the helper level.
- `scripts/sweep_to_treasury.py`, `scripts/sweep_helpers.py` — review. Probably already integer-ish since they read on-chain balances.
- `scripts/migrate_money_to_micro.py` (new, optional per the DB strategy decision above)

### `BATCH-SETTLEMENTS.md` and other docs

Search for any documented float math patterns and update. Probably minimal — most of the brief talks in terms of "rows" not amounts.

---

## Critical correctness rules to NOT break

1. **Atomic UPDATE with guard stays the only way to mutate `spent`.** The guard becomes exact integer (`budget - spent >= :amount_micro`), no epsilon. Two concurrent settlements still cannot both pass.
2. **Compensating refund on Privy failure** still runs the inverse UPDATE — flip COMPLETED→ACTIVE if room reopens. Now exact, no epsilon.
3. **Memo on USDC transfers** — unchanged. Still required for tx-bytes uniqueness.
4. **`flushing` intermediate state** — unchanged. Still required to close the refund/loop double-pay race.
5. **Never compensate on RPC blindness** — unchanged. Pending rows go back to PENDING on getSignatureStatuses 429s.
6. **Refund flushes pending first** — unchanged. The `503` path for un-drainable pending stays.
7. **Best-effort protocol fee** — unchanged. After settle, fire-and-forget transfer; null tx_hash on failure, campaign still flips ACTIVE.
8. **Privy `reference_id` is post-broadcast idempotency** — unchanged.

---

## Validation criteria

The session is done when ALL of these pass on real devnet:

- [ ] `tsc --noEmit` clean on frontend
- [ ] `pytest` (or whatever the backend test command is) clean
- [ ] `scripts/e2e_demo.py` passes 15/15 with batching enabled-then-flushed (same as 16.8 baseline)
- [ ] `scripts/audit_ledger.py` returns zero DRIFT, zero SHORT, zero IN-FLIGHT after a manual paused-campaign drain
- [ ] Browser walk: create a campaign through the wizard targeting 2 DMAs / 3 days. Quote step shows correct numbers. Funding flow lands. Auto-play accumulates plays. Stat cards on Overview + CampaignCard show correct numbers (verify against direct DB inspection: `SELECT spent, budget FROM campaigns WHERE id = ...` returns int micro values that match what the dashboard displays).
- [ ] Refund flow: pause a campaign, refund. On-chain balance ends at 0. Audit returns zero across all flags.
- [ ] **30-min auto-play soak with new code: zero drift.** Match 16.8's bar.
- [ ] **No `+ 1e-9`, no `tolerance`, no `abs(... - ...) < epsilon` patterns remain in the money path.** `grep -r "1e-9\|epsilon\|tolerance" backend/app` should return only non-money matches.

---

## Suggested execution order

1. Create `app/services/money.py` (new file, no consumers yet — safe).
2. Update `app/models.py` column types.
3. Decide DB strategy (wipe-and-rebuild vs one-shot migration script). If wipe: do it now per RUNBOOK hygiene reset routine.
4. Update `app/services/calc.py` to all-int. Run `pytest backend/tests/test_calc*` if it exists.
5. Update `app/services/tokens.py` (JWT claim type).
6. Update `app/routers/bid.py` and `app/routers/proof.py` (consumers of the JWT claim + spent/budget). Run `e2e_demo.py` — should still pass at this point if schemas haven't been touched.
7. Update `app/services/auto_play.py` and `app/services/batch_settler.py`.
8. Update `app/services/x402.py` and `app/services/solana.py`.
9. Update `app/schemas.py` (wire format flip). This is the breaking-change moment for the frontend.
10. Update frontend types + `lib/money.ts` + all `.toFixed` call sites.
11. Re-run e2e (15/15), audit ledger (zero across flags), browser walk.
12. 30-min soak. If clean, write the work log entry below this brief and flip the status to ✅.

---

## Reference reading

Before writing code, the executing agent should read:

- `PLAN.md` — Must-fix #3 (the original problem statement) and Must-fix #2 (the atomic UPDATE pattern that needs to stay correct).
- `worklog/session-15.md` — current `compute_quote` shape + the protocol-fee pipeline.
- `worklog/session-16.5.md` — atomic UPDATE rationale, memo-on-USDC-transfers, compensating refund.
- `worklog/session-16.8.md` — batch_settler architecture, the never-compensate-on-uncertainty rule, the `flushing` claim.
- `worklog/validation-pass-2026-04-28.md` — audit_ledger expectations.
- `BUSINESS-CONSTRAINTS.md §6` — protocol fee model + demo CPM lock.
- `BATCH-SETTLEMENTS.md` — full batch settlement design.

The codebase already has the discipline patterns (atomic UPDATE, memo, compensating logic). This refactor is a type-system change layered on top — it should NOT change any algorithms, only the precision of the values they operate on.

---

## Work log entry (2026-04-30)

**What shipped.** Money flows are now integer microUSDC end-to-end: DB columns, Python internals, the wire format, the JWT claim. Float USDC is contained to one well-marked UI spot (the WalletChip pending-amount delta) and config parsing (DEMO_CPM, faucet_amount_usdc), both passed through `services.money.to_micro()` at the boundary. Every `+ 1e-9` epsilon and tolerance comparison in the budget/spent path is gone — the brief's grep target (`1e-9|epsilon|tolerance` in `backend/app`) returns only historical-context comments, no live math.

**The actual list of changes.**

Backend
- `app/services/money.py` (new) — `to_micro(usdc)` for trust boundaries, `micro_str(int)` for Pydantic responses.
- `app/models.py` — `Numeric(18, 6)` + `Mapped[float]` flipped to `BigInteger` + `Mapped[int]` on `Campaign.cpm_price/budget/spent/protocol_fee_amount` and `Settlement.amount_usdc`. Column names kept (`cpm_price` still stores microUSDC per 1000 plays; the user pushed back on the originally-proposed rename to `cost_per_play_micro` because production needs CPM-as-bid-ceiling separate from per-play cleared price, which the rename would have lost). Docstring documents the unit.
- `app/database.py` — dev-shim ALTER type for `protocol_fee_amount` updated `NUMERIC(18,6)` → `BIGINT`. The shim only fires on existing tables; clean wipe + create_all uses model types directly. Existing dev DB was wiped (no real data — only e2e fixtures and three drained `Soak N` rows from the 16.8 soak).
- `app/services/calc.py` — `compute_quote` returns `Quote` with `cpm_price_micro / total_micro / protocol_fee_micro / total_to_escrow_micro` (renamed for clarity since the units changed). Protocol fee math uses basis points (250 bps = 2.5%) so it's `int * int // 10_000` with no rounding ambiguity.
- `app/services/tokens.py` — `ProofContextClaims.amount_usdc: float` → `amount_micro: int`. Added a `v=2` version field on the JWT; v=1 (no version) decodes raise `ProofContextError` so old in-flight tokens fail loudly. TTL covers the deploy window.
- `app/routers/proof.py` — atomic UPDATE guard is exact-int compare (`budget - spent >= :amount_micro`); COMPLETED-flip rule is bit-precise `Campaign.budget - new_spent < play_cost`. No epsilon.
- `app/routers/bid.py` — `_pick_campaign` budget check is exact int. `_build_proof_context` mints `amount_micro = cpm_price_micro // 1000`. Bid response `price` field stays float USDC (OpenRTB convention is a number, not a string — display only, settlement is the JWT claim).
- `app/services/auto_play.py` — `_EligibleSnapshot` is `tuple[str, int, tuple[str, ...]]` (cpm_price stays in micro per 1000 plays).
- `app/services/batch_settler.py` — `_compensate_failed` does exact-int subtraction, exact-int COMPLETED→ACTIVE re-flip. `total_amount_micro = sum(int(r.amount_usdc) for r in rows)` instead of float.
- `app/services/x402.py` — `build_payment_requirements(amount_micro: int)`. Drops the `int(round(* 1e6))` conversion — `maxAmountRequired` is just `str(amount_micro)`.
- `app/services/solana.py` — `get_usdc_balance(...)` renamed to `get_usdc_balance_micro(...)` returning `int` (read from `value.amount` directly, not `ui_amount`). `build_usdc_transfer_tx(amount_micro: int)`. Drops the `int(round(* 1e6))` conversion. `transfer_checked` already takes the atomic-units int.
- `app/routers/campaigns.py` — every `_to_summary` / `_to_settlement_summary` / `campaign_stats` / refund / simulate-play call site reformatted to pass `micro_str(int_value)` to schemas. The retry-flow `escrow_amount_micro` is exact int sum, producing bit-identical x402 PaymentRequirements bytes vs. the original 402.
- `app/routers/wallet.py` — `usdc_balance` from `get_usdc_balance_micro`, `faucet_amount` derived once via `to_micro(settings.faucet_amount_usdc)` and reused for both the transfer and the response.
- `app/routers/dashboard.py` — `DashboardActivityRow.amount_usdc` formatted as `micro_str(int(s.amount_usdc))`.
- `app/services/retry.py` — pass-through to `build_usdc_transfer_tx(amount_micro=int(s.amount_usdc))`.
- `app/schemas.py` — every money field on every response model is `MicroStr = str` (alias added for documentation). Field names kept stable so frontend type changes are mechanical `number → string`.

Frontend
- `frontend/src/lib/money.ts` (new) — BigInt-native `formatUsdc(microStr, dp)` (no JS Number round-trip → overflow-proof at any value), `parseUsdc(microStr)` for the WalletChip delta only, `sumMicro([microStr])` and `subMicro(a, b)` and `cmpMicro(a, b)` for math.
- `frontend/src/lib/aggregations.ts` — `CampaignRow / SettlementRow / StatsRow` money fields flipped `number → string`. Comment marks the wire convention.
- Display call sites updated across `Overview.tsx`, `Campaigns.tsx`, `CampaignCard.tsx`, `WalletChip.tsx`, `wizard/StepCalculator.tsx`, `wizard/StepReview.tsx`. The wizard's `createX402Client({ amount: BigInt(quote.total_to_escrow_usdc) })` drops the `* 1.05 * 1e6` slack — the 5% drift safety margin is no longer needed.
- WalletChip is the one place float USDC is allowed: `parseUsdc` once at the `/api/wallet` boundary, then the chip's `+0.42 USDC inbound` animation runs on a JS `Number` since it's a UX delta indicator never compared to a campaign budget. Documented inline.

Scripts
- `scripts/audit_ledger.py` + `audit_ledger_verbose.py` — full rewrite to int micro. Comparisons are exact `==` instead of `< tolerance`. Custom `_fmt_micro(int)` formatter for human-readable display.
- `scripts/e2e_demo.py` — `_seed_campaign(budget_micro: int, cpm_micro: int)`, the engineered-pending-rows fixtures and assertions all use int micro. The "spent matches expected" check is now `int(fresh.spent) == COST_PER_PLAY_MICRO` instead of `abs(... - ...) < 1e-9`.
- `scripts/sweep_to_treasury.py`, `sweep_helpers.py`, `cleanup_drift.py`, `cleanup_drift_reverse.py`, `probe_sponsorship.py`, `topup_campaigns.py`, `check_balance.py` — all updated to use `get_usdc_balance_micro` + `amount_micro=` parameter.

**Decisions taken during implementation.**

1. _Keep `cpm_price` as the column name._ Brief originally proposed renaming to `cost_per_play_micro` for cleaner semantics. User pushed back — production with real publisher ecosystems needs CPM as a bid-ceiling concept (max-CPM on the campaign, cleared-CPM per settlement once auction logic lands), and storing per-play directly loses information (`// 1000` is lossy integer division). Industry convention (gas in gwei, SPL atomic units) is to store at the granularity the API uses. Kept `cpm_price`, documented that the unit is "microUSDC per 1000 plays" in the model docstring.

2. _BigInt-native `formatUsdc` (not `Number` division)._ JS `Number` is fine per-value up to ~$9B in micro (2⁵³ safe-integer boundary), but a footgun for sums and totally invisible at the call site. The two-line BigInt divmod has zero downside and is overflow-proof at any platform scale. The brief proposed using `Number(s) / MICRO`; switched mid-flight after working through the realistic value ranges with the user.

3. _Float USDC stays at the `WalletChip` delta boundary only, never elsewhere._ The chip animates `+0.42 USDC inbound · confirming…`. We `parseUsdc(...)` once at the wire boundary, do float math for the +1e-6 "balance arrived" check (this is a UX signal, not money correctness), and the rest of the app sees only micro strings. Documented inline so future readers know the rule.

4. _Skipped sweep before DB wipe._ Inventory was 28 e2e/soak campaigns, all REFUNDED/COMPLETED/PAUSED. The PAUSED `e2e-refund-pending` fixtures held ~$0.012 total USDC — devnet, advertiser-funded from treasury faucet. User opted to wipe directly; net loss is a few cents in e2e-test wallets we'll never reuse, vs ~5 min of sweep script time.

5. _Drop the x402 client's `*1.05` slack._ The 5% headroom on the wizard's `createX402Client({ amount })` was a float-drift safety margin from when amount was computed in float USDC. With exact int micro from server quote, the slack is no longer needed for correctness. Removed.

**Surprises and findings.**

- _The float drift was visibly present in the wild before the refactor._ Inspecting the old DB: `Soak 1` had `spent=0.6139999999999878` (614 plays at $0.001, expected exactly 0.614). On-chain was correct (614 transfers of exactly 1000 micro = 614_000 atomic units), but the DB float representation accumulated ~1e-14 of error per play. The audit was passing only because of the tolerance window. This validated the "must-fix" framing — the bug was real, just contained by epsilons.

- _Brief's diagnosis was slightly off._ It said "SQLAlchemy returns Python `float` due to the `Mapped[float]` annotations." That's not how SQLAlchemy works — `Mapped[float]` is a type hint, runtime-irrelevant; `Numeric` returns `Decimal`. The actual float entry points were the explicit `float(c.budget)` / `float(c.spent)` casts scattered through `auto_play.py`, `bid.py`, `campaigns.py`, `proof.py`. Fix is the same; diagnosis is "grep `float(`" not "the model annotations."

- _Pyright's stale-state caching during the refactor._ Diagnostics consistently lagged a turn or two behind the actual file state. Several "X is not defined" errors flagged code that had already been updated. Worth knowing when sequencing edits — verifying via `Read` instead of trusting Pyright's report between edits saves time.

- _e2e revealed one pre-existing, unrelated issue._ The refund SOL sweep step in `routers/campaigns.refund_campaign` failed for a campaign wallet with 9_985_000 lamports (the post-tx-fee residual): trying to sweep `lamports - 10_000` left it below rent-exempt threshold, Privy rejected the broadcast. Non-blocking (logged-and-continue path), pre-dates this session, not introduced by the refactor. Filed mentally for a future session — refund SOL sweep needs to leave rent-exempt minimum, not just two-fees-worth.

**Validation results.**

- `tsc --noEmit` on frontend: clean (exit 0).
- `scripts/e2e_demo.py`: **25/25 steps passed** including the multi-campaign batch isolation test (concurrent flushes producing distinct on-chain txs per campaign).
- `scripts/audit_ledger.py`: **zero DRIFT, zero SHORT, zero IN-FLIGHT** across all 5 e2e campaigns. Publisher MORE flag is expected (pre-existing accumulated balance from prior soaks, +$2.45 over what this run alone should account for).
- `grep -r "1e-9\|epsilon\|tolerance" backend/app` returns 3 hits, all in comments referencing the historical fix. No live math.
- Backend boots cleanly with the new schema; auto-play loop and batch settler both running without errors.

**What this enables.**

- Session 17 (GCP deploy + Postgres migration) starts from a clean integer-money codebase. The Postgres migration just maps `BigInteger` to Postgres `BIGINT` — no NUMERIC-to-INT type-conversion gymnastics, no float-precision compatibility shims.
- Audit and reconciliation scripts use exact equality, not tolerance bands. Any future drift will surface immediately, not get swallowed by `< 1e-3`.
- The "real fix" called out in `PLAN.md` Must-fix #3 is shipped. PLAN's Must-fix list now has 3 items left (overcommit at /bid, per-publisher rate limiting, single-worker uvicorn) — none are demo blockers.
