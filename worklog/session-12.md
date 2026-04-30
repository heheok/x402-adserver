# Session 12 — Treasury topup helpers (multi-wallet workaround) ✅

**Date:** 2026-04-27

## Checklist

- [x] `scripts/bootstrap_helpers.py` (new, separate from `bootstrap_treasury.py`) — creates N helper Privy server wallets (default 3, `--count N`); prints `HELPER_WALLET_IDS` + `HELPER_WALLET_ADDRESSES` (comma-separated) for paste into `.env`. Settings fields added to `app/config.py`.
- [x] Each helper seeded with 0.01 SOL from the treasury via `build_sol_transfer_tx` + `wait_for_tx_confirmation`. RPC airdrop dropped — same lesson as the campaign-wallet seed flow (devnet airdrops silently fail).
- [x] `scripts/sweep_helpers.py` — default mode reads env, zips ids+addresses, sweeps any non-zero helper to `TREASURY_WALLET_ADDRESS`. Plus `--wallet-id` + `--wallet-address` rescue mode for one-off sweeps.
- [x] `RUNBOOK.md` "helper multiplex" section under Top up — bootstrap, paste, recreate, daily click+sweep routine, plus rescue command.
- [x] Circle account-upgrade probe — `/v1/faucet/drips` returns HTTP 403 for sandbox keys (verified 2026-04-24, KYC-gated). Manual web-faucet sweep is the only path until/unless Circle upgrade lands.

**Why this is first:** lead time matters. Every day we don't run the helper-claim routine is ~60 USDC of foregone treasury runway. Shipped before the wizard work so it accumulates in the background.

**Why multi-wallet manual:** Circle programmatic `/v1/faucet/drips` returns HTTP 403 for sandbox keys (verified 2026-04-24) — the docs' "requires upgrading to mainnet" line maps to a real account-level KYC gate. Public web faucet is captcha-gated so cannot be safely automated. Per-address rate limit (20 USDC / 2h) is the documented Circle policy, verified empirically on 2026-04-27 (one helper claim then immediately a treasury claim from the same browser session — both succeeded), so N independent addresses give N × 20 USDC per cycle.

**Exit criteria met (2026-04-27):** rescued the throwaway helper from `create_helper_wallet.py` (recovered 20 USDC into treasury), bootstrapped 3 fresh helpers, manually claimed Circle faucet into all 4 (4 × 20 = 80 USDC), `sweep_helpers.py` consolidated all of it to treasury in one run with 4 Solscan tx hashes. Treasury USDC visibly grew by ~80.

**Reference-id length gotcha:** Privy caps `reference_id` at 64 chars. Initial sweep used a full uuid4 string suffix → 68 chars → 400 `invalid_data`. Codebase convention is `uuid4().hex[:8]` (matches `routers/wallet.py` faucet, `routers/campaigns.py` campaign-bootstrap). Kept that pattern in both helper scripts.

## Work log entry

- **2026-04-27 (Session 12):** Treasury topup helpers shipped. Manual experiment confirmed Circle's per-address rate limit is real (claim into helper + immediate claim into treasury from same browser → both succeeded). New `scripts/bootstrap_helpers.py` creates N Privy server wallets and treasury-seeds each with 0.01 SOL via `build_sol_transfer_tx` + `wait_for_tx_confirmation` (the RPC-airdrop path silently fails the same way it does for campaign wallets, so we don't even try). New `scripts/sweep_helpers.py` reads zipped `HELPER_WALLET_IDS` / `HELPER_WALLET_ADDRESSES`, sweeps any non-zero helper to treasury, plus `--wallet-id` + `--wallet-address` rescue mode for one-offs. Used the rescue mode to recover 20 USDC from the throwaway helper created by `create_helper_wallet.py` during the manual probe. End-to-end verified: 4 helpers (3 bootstrap + 1 rescued) → 4 × Circle web-faucet claims → one `sweep_helpers.py` run consolidated 80 USDC to treasury with 4 Solscan tx hashes. **Reference-id length gotcha**: Privy's 64-char cap meant the first sweep failed with `invalid_data` — full uuid4 string suffix was 68 chars. Codebase convention is `uuid4().hex[:8]`, kept that in both new scripts. RUNBOOK has the daily-routine click sequence + rescue command.
