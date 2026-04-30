# Session 4 — Bid matching ✅

**Date:** 2026-04-21

## Checklist

- [x] `services/tokens.encode_proof_context` / `decode_proof_context` (HS256, self-contained claims)
- [x] `POST /bid` — OpenRTB-lite parsing, FIFO campaign pick, minted `proof_context` JWT
- [x] No-bid paths: missing impression, missing publisher wallet, no active campaigns, budget exhausted
- [x] Pure in-process: one DB query, no external calls — fits the <500ms budget

**Exit criteria met:** Verified via 4 curl smokes (no-key 401, no-match no-bid, positive bid with decoded JWT, exhausted no-bid). Signed `proof_context` decoded cleanly to the expected claims (campaign_id, bid_id, publisher wallet, fresh nonce, timestamp, amount = cpm/1000).

## Work log entry

- **2026-04-21 (Session 4):** `POST /bid` implemented with FIFO matching + signed `proof_context`. Four curl smokes pass (no-key 401, no-match no-bid, positive bid, budget-exhausted no-bid). `services/tokens` now has working HS256 encode/decode ready for Session 5 proof verification.
