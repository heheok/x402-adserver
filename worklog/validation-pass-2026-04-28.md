# Validation pass — post-Session 16.7 hygiene reset + clean simulation ✅

**Date:** 2026-04-28

## What shipped

Two new ops scripts:

- `scripts/audit_ledger.py` — read-only reconciliation across three sections (publisher / campaign-wallet / service-wallet) with SHORT/DRIFT/MORE/OK flags and a tolerance-aware comparison.
- `scripts/sweep_to_treasury.py` — drains every owned Privy server wallet to treasury with a USDC-then-SOL ordering, gas-seed pre-pass for wallets that have USDC but zero SOL, dry-run by default.

## Forensic finding

The one DRIFT row in the initial audit (refunded campaign `2fc2e504` with 0.031 USDC stranded on-chain) was traced to pre-Session-16.5 settlement-tx-bytes dedup. Decoded the campaign's refund tx via `get_transaction(jsonParsed)` + pre/post token balance deltas: refund correctly sent `budget - spent = 2.8305` per the DB; campaign wallet held 2.8615 going in (because 62 of the 99 "confirmed" /proof settlements had been collapsed by Solana network dedup before the memo fix shipped at 18:16 the same day the campaign ran). Math reconciled exactly (62 × 0.0005 = 0.031). Same-shape leak as BACKEND-REVIEW.md §1.1, different root cause; current refund code has the §1.1 property but not the dedup property (memo fix landed 16.5).

## Hygiene reset executed

Stopped backend → swept 12.82 USDC + 5.48 SOL across 51 campaign wallets + 4 helpers + protocol-revenue + demo-publisher → wiped `backend/data/adserver.db` → restart → audit returned empty (zero campaigns, zero settlements, treasury holds the consolidated funds).

## Controlled simulation

Funded 3 campaigns through the wizard targeting different DMAs, paused after auto-play accumulated 844 plays / 0.4220 USDC across them. Audit returned **zero DRIFT, zero SHORT** on every reconciliation — publisher's 844 plays = 0.422000 USDC matched on-chain to the microUSDC, all 3 paused campaigns matched their `budget - spent` exactly, protocol revenue = 0.765000 USDC = 30.6 × 2.5% bit-perfect.

## Refund flow validated

Refunded the meatiest paused campaign (`a8960943`, 17.0525 USDC remaining); on-chain ended at 0.0000, no leak, other 2 campaigns unaffected. Atomic UPDATE + memo fix from Session 16.5 confirmed correct under real concurrent load.

## RUNBOOK additions

Two new sections document the audit + reset routines including a forensic recipe for tx-level investigation.

## Frontend polish bugs found and fixed

- Leaflet z-index bleed above wizard modal (added `isolation: isolate` on `.x-map`, bumped Modal `zIndex` 100 → 1000).
- The live activity map's integer-zoom-snap leaving big empty space around tight DMA bounds (`zoomSnap={0.25}` + tighter padding + `maxZoom={7}`).
- UX nit: relocated the protocol-fee tx Solscan link from a standalone block under the map to a sub-link under the Protocol fee stat itself, and added a campaign-wallet Solscan link under the Remaining stat.
