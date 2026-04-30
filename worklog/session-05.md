# Session 5 — Proof of play + settlement ✅

**Date:** 2026-04-21

## Checklist

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

## Work log entry

- **2026-04-21 (Session 5):** `POST /proof` implemented end-to-end. First true on-chain test of the pipeline: bid → proof → real USDC transfer on devnet. Tx hash `3i5y7hga…xQ9h` settles 0.0125 USDC treasury → publisher. Replay protection verified (409 on duplicate nonce). DB state consistent across campaigns/used_nonces/settlements.
