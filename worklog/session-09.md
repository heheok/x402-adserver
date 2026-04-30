# Session 9 — Dashboard flows (fund) ✅

**Date:** 2026-04-22

## Checklist

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

## Work log entries

- **2026-04-22 (Session 9 start):** `WalletPanel` implemented — `/api/wallet` query with 400/404 retry for fresh-signup server-side link lag, pulsing "inbound +X USDC, confirming on devnet" indicator that clears when the new balance lands, fallback "Create Solana wallet" button via `useSolanaWallets().createWallet()` for users whose account predates the corrected Solana-only config. Bug fix: `/api/faucet` reference_id now has a uuid suffix — Privy's `reference_id` is validated post-broadcast (duplicate keys still broadcast the tx then error with `invalid_data` at record time), so without the suffix every click after the first returned 502 despite the transfer succeeding. Documented in `BUSINESS-CONSTRAINTS.md §3` and §7 blocker #14 ("Retry safety for non-idempotent on-chain operations"). Comment in `services/privy.py` clarifies why the existing retry loop is still safe (narrow to `transaction_broadcast_failure` which means broadcast did not happen).
- **2026-04-22 (Session 9 close):** Campaign funding flow shipped end-to-end. `<CreateCampaignForm>` + PayAI's `x402-solana@^2.0.4` auto-handshake against our existing backend. Path getting there cost four trips through the facilitator; each fix documented in Session 9 block above: (1) destination USDC ATA must be pre-created server-side → `build_campaign_bootstrap_tx` bundles SOL seed + ATA create, must confirm before returning 402; (2) x402.org v1 facilitator entry is `solana-devnet`, not CAIP-2; (3) `x402.org/facilitator` 308-redirects to `www.`; (4) `extra.feePayer` must be facilitator's address (Config 2 is the only working path on this stack) — fetched from `/supported` + cached in `get_facilitator_fee_payer()`. Advertiser-SOL-seed branch removed (facilitator pays gas). `lib/walletTrack.ts` shared Zustand store drives `WalletPanel` polling after any money-moving mutation so the debit lands visibly within 2–4s. E2E script (`scripts/e2e_demo.py`) unchanged — still 13/13 on the path that bypasses `/api/campaigns`.
