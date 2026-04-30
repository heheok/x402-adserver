# Session 2 — Privy + wallet endpoints ✅

**Date:** 2026-04-21

## Checklist

- [x] Add `solana==0.36.6`, `solders==0.23.0` to `requirements.txt`
- [x] Privy REST client (`services/privy.PrivyClient`) — create, list, get, signAndSend, get_user, fetch_jwks
- [x] Solana helpers (`services/solana`) — USDC balance, USDC transfer tx builder, devnet SOL airdrop
- [x] Treasury bootstrap script (`scripts/bootstrap_treasury.py`) — idempotent, prints env vars + Circle faucet instructions
- [x] Privy JWT verification against JWKS (`dependencies._verify_privy_jwt`, ES256)
- [x] `GET /api/wallet` — resolves advertiser's Solana wallet via Privy, reads USDC balance from RPC
- [x] `POST /api/faucet` — treasury → advertiser (100 USDC) via signAndSendTransaction
- [x] **User action**: rebuild image, run `bootstrap_treasury.py`, paste vars into `.env`, fund treasury via Circle faucet

**Exit criteria:** Log in via Privy on the React dashboard (or any JWT source), hit `/api/faucet`, see USDC arrive in the user's wallet on Solscan devnet.

**Privy API validated (2026-04-21):** creation, listing, and `signAndSendTransaction` all documented and exercised. Probe script confirmed full access. Devnet caip2 = `solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1`. Campaign-wallet reuse helper lives in `PrivyClient.create_solana_wallet()` — Session 3 calls it per campaign.

## Work log entry

- **2026-04-21 (Session 2):** Privy client, Solana helpers (balance + USDC transfer builder + airdrop), real JWKS JWT verification, `bootstrap_treasury.py`, `check_balance.py`, `/api/wallet`, `/api/faucet`. Treasury wallet `dh52nvrial6szf2bupq4dcar` / `D4atNw3qRuXUkcKVuzGgosJemP3bboT1B7FSNjHdpjUJ` created and funded by user (SOL + ~20 USDC). Published `RUNBOOK.md` at repo root for ops.
