# Session 16.6 — SOL exhaustion + RPC-rate-limit drift (resolved by 16.8) ✅

**Date:** 2026-04-28

**Discovery:** after letting auto-play run for hours, one campaign's proof transactions started failing with `InsufficientFundsForRent` from Privy:

```
ERROR app.routers.proof :: settlement failed campaign=ac89a867…
PrivyError: privy error 400: Transaction simulation failed: Transaction
results in an account (0) with insufficient funds for rent
```

The campaign wallet had drained its 0.01 SOL seed paying validator fees across hundreds of plays; Privy's simulation rejected further txs to preserve the rent-exempt minimum. Two compounding drift sources came out of the diagnostic work:

1. **SOL exhaustion** — fixed by an iteration that ships in the committed-to-main work alongside Session 16.8: right-sized SOL seed at creation time (`services/calc.required_sol_seed_lamports`) + refund-time SOL sweep back to treasury (`services/solana.get_sol_lamports` + sweep block in `routers/campaigns.refund_campaign`). The seed is `6_000 lamports per total_play + 50_000 reserve`, computed from the calculator's `total_plays`. Way more than enough for batch model since plays no longer map 1:1 to txs.
2. **RPC-rate-limit drift** — fixed by Session 16.8 (batch settlement). The α + γ_safe + γ_extra iteration (added wait_for_tx_confirmation + late-landing get_signature_status check) fixed one drift direction (false-confirmed-without-landing), but exposed another: under devnet RPC's 4 req/s/method limit, both wait + γ_extra went blind, returned None, and the compensating UPDATE wrongly rolled back txs that actually landed. Per-play architecture was wrong; batch model leaves rows pending on RPC blindness.

## Resolution

- [x] Discuss a solution → BATCH-SETTLEMENTS.md (Session 16.8 brief)
- [x] Fix the issue → Session 16.8 batch settlement landed; α + γ work preserved as foundation (wait + γ_extra moved into `services/batch_settler.flush_group`)
- [x] Fix the drift → 0.0055 USDC publisher MORE / campaigns DRIFT cleaned via `scripts/cleanup_drift_reverse.py` (publisher → campaigns split: 0.0030 to c298e3bc, 0.0025 to ac89a867; audit returned zero across all flags before new code processed anything)
