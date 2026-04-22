# Operations Runbook

Click-by-click instructions for every repeated ops task. Grows as we build.
Keep this up to date when a procedure changes.

Addresses in the examples are from the current dev treasury:
- `TREASURY_WALLET_ADDRESS=D4atNw3qRuXUkcKVuzGgosJemP3bboT1B7FSNjHdpjUJ`

Always run commands from the repo root (`C:\Development\x402`).

---

## Daily dev commands

### Start / stop the backend
```bash
docker compose up -d backend        # start in background
docker compose logs -f backend      # tail logs
docker compose down                 # stop everything
docker compose restart backend      # pick up CODE changes only (uvicorn --reload does this automatically)
```

### Pick up new `.env` values (env_file gotcha)
`docker compose restart` does NOT re-read the `env_file` — it stops and starts
the existing container with its frozen environment. After editing
`backend/.env`, recreate the container:
```bash
docker compose up -d --force-recreate backend
```
Verify with:
```bash
docker compose exec backend env | grep VAR_NAME
```

### Rebuild after changing requirements.txt or Dockerfile
```bash
docker compose build backend
docker compose up -d backend
```

### Open the API
- Health: http://localhost:8000/health
- OpenAPI UI: http://localhost:8000/docs

---

## Balance checks

### Treasury (or any address)
```bash
# uses TREASURY_WALLET_ADDRESS from .env
docker compose run --rm backend python scripts/check_balance.py

# or pass an explicit address
docker compose run --rm backend python scripts/check_balance.py <address>
```

### Via Solscan (web)
```
https://solscan.io/account/<address>?cluster=devnet
```
Click the **Tokens** tab to see the USDC balance.

---

## Top up the treasury

The treasury pays out devnet USDC to advertisers via `POST /api/faucet`. It needs
both SOL (for tx fees) and USDC (for faucet payouts).

### Top up SOL
1. Open https://faucet.solana.com/
2. Select **devnet**
3. Paste `TREASURY_WALLET_ADDRESS`
4. Request 1 SOL (site caps per request — re-run if you need more)

Rate-limited? Fallbacks: https://solfaucet.com or https://faucet.quicknode.com/solana/devnet

### Top up USDC
1. Open https://faucet.circle.com
2. Network: **Solana Devnet**
3. Paste `TREASURY_WALLET_ADDRESS`
4. Request USDC (capped at 20 USDC per 2 hours)

### Verify
```bash
docker compose run --rm backend python scripts/check_balance.py
```

---

## Treasury lifecycle

### Create a new treasury wallet (first time, or after rotating)
```bash
docker compose run --rm backend python scripts/bootstrap_treasury.py
```

Copy the printed `TREASURY_WALLET_ID` and `TREASURY_WALLET_ADDRESS` into
`backend/.env`, then:
```bash
docker compose restart backend
```

The script is idempotent — if `TREASURY_WALLET_ID` is already set in `.env`,
it prints the existing values and exits without creating anything new.

### Rotate the treasury (abandon old, make new)
1. Delete `TREASURY_WALLET_ID` and `TREASURY_WALLET_ADDRESS` lines from `backend/.env`
2. Run `bootstrap_treasury.py` again
3. Paste the new values back into `.env`
4. Restart backend
5. Fund the new treasury (SOL + USDC) via the faucets above

Privy does not support wallet deletion — the old treasury stays in your Privy
app forever but simply stops being referenced.

---

## End-to-end smoke test

Runs the full loop against live devnet — seeds a fresh campaign, exercises the
happy path and every edge case, reports pass/fail per step. Spends ~0.03 USDC
per run from the treasury; costs ~0.001 SOL for fees.

```bash
docker compose run --rm backend python scripts/e2e_demo.py
```

What it covers:
- seed campaign (create wallet → SOL-fund from treasury → USDC-fund → activate)
- happy path: `/bid` → `/proof` → on-chain settlement
- replay rejected (409 on duplicate nonce)
- expired `proof_context` (400)
- paused campaign → empty seatbid
- budget drained → auto-flip to `completed`, empty seatbid afterwards
- refund + double-refund guard

Quarantines any pre-existing ACTIVE campaign for the duration of the run and
restores them on exit. Safe to re-run without DB reset.

Troubleshooting: if pre-flight says "treasury has only 0.0 USDC" but Solscan
shows funds, re-run — the devnet RPC 429'd and our balance helper falls
through to 0. The script has one retry built in; a second run almost always
clears it.

---

## Retry pending-failed settlements

`POST /proof` writes a failed `Settlement` row when Privy or the facilitator
reject the settlement tx (most commonly Privy's simulation RPC lagging a fresh
wallet's funding). Retry them once the lag clears:

```bash
docker compose run --rm backend python scripts/retry_settlements.py
docker compose run --rm backend python scripts/retry_settlements.py --limit 20
```

Exit code 0 if every scanned row ended `confirmed` or `skipped`, 1 if any are
still failing — pipe that into cron/automation if you want.

---

## Auto-play (demo-only)

Server-side background loop that auto-settles one play every
`AUTO_PLAY_INTERVAL_SECONDS` on a random active + funded campaign. Only meant
for the dashboard demo — production publishers drive `/bid` + `/proof`
themselves. **Must be off in any deployed environment.**

### Enable / disable
Edit `backend/.env`:
```
AUTO_PLAY_ENABLED=true            # or false
AUTO_PLAY_INTERVAL_SECONDS=15     # tick interval
DEMO_PUBLISHER_WALLET=<address>   # who receives the settlements
```
Then **recreate** the container (restart won't pick up env changes — see the
env_file gotcha above):
```bash
docker compose up -d --force-recreate backend
```

### Verify it's running
```bash
docker compose logs backend | grep auto-play | tail -10
```
Expected: one `auto-play loop starting — interval=15s` line, then one
`auto-play: campaign=... tx=...` line per tick.

### Tail it live
```bash
docker compose logs -f backend | grep --line-buffered auto-play
```

### Check status from the browser / CLI
```bash
curl http://localhost:8000/api/auto-play-status
# → {"enabled":true,"interval_seconds":15}
```
The dashboard polls this and shows a pulsing "Auto-simulating…" badge when enabled.

### Behaviour notes
- Picks at **random** from campaigns with `status=active` AND
  `remaining >= cpm_price/1000`. Oldest-funded doesn't win; multiple active
  campaigns all tick along.
- A campaign drained mid-tick (manual simulate, external `/proof`) will log
  a harmless `auto-play skipped … status=409` on the next tick that picks it.
- Failed on-chain settlements land in the `settlements` table with
  `status=failed` the same way manual ones do — clear with
  `scripts/retry_settlements.py`.

---

## Privy sanity check

Confirms the Privy app still has server-wallet access.
```bash
docker compose run --rm backend python scripts/probe_privy.py
```

Creates one throwaway wallet and lists existing wallets. Exit code 0 = healthy.

---

## Database

Currently SQLite at `backend/data/adserver.db` inside the `backend_data` volume.

### Reset the DB (wipe campaigns, settlements, nonces)
```bash
docker compose down
docker volume rm x402_backend_data
docker compose up -d backend
```
Tables are recreated automatically on startup via `init_db()`.

### Inspect the DB
```bash
docker compose exec backend sqlite3 /app/data/adserver.db
# then at the sqlite prompt:
.tables
SELECT id, status, budget, spent FROM campaigns;
.quit
```

---

## Environment variables reference

Set in `backend/.env` (copy from `backend/.env.example` to start).

| Var                           | Purpose                                                  | Set in Session |
| ----------------------------- | -------------------------------------------------------- | -------------- |
| `PRIVY_APP_ID`                | Privy app credentials                                    | 1              |
| `PRIVY_APP_SECRET`            | Privy app credentials                                    | 1              |
| `TREASURY_WALLET_ID`          | Privy wallet id (after `bootstrap_treasury`)             | 2              |
| `TREASURY_WALLET_ADDRESS`     | Solana address of the treasury wallet                    | 2              |
| `FAUCET_AMOUNT_USDC`          | How much USDC the faucet hands out per call              | 2              |
| `PUBLISHER_API_KEY`           | Publisher API key for `/bid` and `/proof`                | 1              |
| `JWT_SERVER_SECRET`           | Signs `proof_context` tokens                             | 1              |
| `SOLANA_RPC_URL`              | Default: devnet                                          | 1              |
| `X402_FACILITATOR_URL`        | Default: `https://www.x402.org/facilitator`              | 1              |
| `CORS_ALLOW_ORIGINS`          | Comma-separated allowed origins (dashboard)              | 8              |
| `DEMO_PUBLISHER_WALLET`       | Demo-only: receives plays from `/simulate-play`+auto-play | 10            |
| `AUTO_PLAY_ENABLED`           | Demo-only: server background loop settles plays (off)    | 11             |
| `AUTO_PLAY_INTERVAL_SECONDS`  | Auto-play tick interval (default 15)                     | 11             |

---

## Common errors

### `treasury not configured` (503 on `/api/faucet`)
`TREASURY_WALLET_ID` or `TREASURY_WALLET_ADDRESS` is missing/wrong in `.env`.
Re-check `docker compose exec backend env | grep TREASURY`, then recreate
(not restart) the container: `docker compose up -d --force-recreate backend`.

### `PRIVY_APP_ID and PRIVY_APP_SECRET must be set`
Env not loaded into the container. Check:
- `backend/.env` exists (not `.env.example`)
- `docker-compose.yml` has `env_file: ./backend/.env` (it does)
- **Recreate** (not just restart): `docker compose up -d --force-recreate backend`

### `verify failed: fee_payer_not_managed_by_facilitator` (402 on `/api/campaigns` retry)
The x402-solana client built a tx with a fee-payer that isn't the facilitator's
managed address. Check that `services/x402.build_payment_requirements` is still
receiving the facilitator's feePayer (fetched by `get_facilitator_fee_payer()`
from `GET /supported`) — not the advertiser wallet. See PLAN.md Session 9.

### `No facilitator registered for scheme: exact and network: solana:...`
Backend is sending the CAIP-2 form of the Solana devnet id against a v1 handshake.
`services/x402.DEVNET_NETWORK` must be `"solana-devnet"` (short name) for v1 — the
CAIP-2 form is only registered under v2.

### Airdrop says rate-limited
Devnet RPC airdrop is flaky. Use https://faucet.solana.com/ in a browser instead.

### Circle faucet says rate-limited
Caps at 20 USDC per 2 hours per address. Wait or use a second address.

### `InsufficientFundsForRent` or `InsufficientFundsForFee` in a Privy settlement
Wallet has no SOL. Top up via https://faucet.solana.com/ (devnet).
