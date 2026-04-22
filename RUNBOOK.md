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
docker compose restart backend      # pick up new .env values
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

| Var                       | Purpose                                     | Set in Session |
| ------------------------- | ------------------------------------------- | -------------- |
| `PRIVY_APP_ID`            | Privy app credentials                       | 1              |
| `PRIVY_APP_SECRET`        | Privy app credentials                       | 1              |
| `TREASURY_WALLET_ID`      | Privy wallet id (after `bootstrap_treasury`)| 2              |
| `TREASURY_WALLET_ADDRESS` | Solana address of the treasury wallet       | 2              |
| `FAUCET_AMOUNT_USDC`      | How much USDC the faucet hands out per call | 2              |
| `FINCH_API_KEY`           | Publisher API key for `/bid` and `/proof`   | 1              |
| `JWT_SERVER_SECRET`       | Signs `proof_context` tokens                | 1              |
| `SOLANA_RPC_URL`          | Default: devnet                             | 1              |
| `X402_FACILITATOR_URL`    | Default: `https://x402.org/facilitator`     | 1              |

---

## Common errors

### `treasury not configured` (503 on `/api/faucet`)
`TREASURY_WALLET_ID` or `TREASURY_WALLET_ADDRESS` is missing/wrong in `.env`.
Re-check `docker compose exec backend env | grep TREASURY`, then `docker compose restart backend`.

### `PRIVY_APP_ID and PRIVY_APP_SECRET must be set`
Env not loaded into the container. Check:
- `backend/.env` exists (not `.env.example`)
- `docker-compose.yml` has `env_file: ./backend/.env` (it does)
- Restart: `docker compose restart backend`

### Airdrop says rate-limited
Devnet RPC airdrop is flaky. Use https://faucet.solana.com/ in a browser instead.

### Circle faucet says rate-limited
Caps at 20 USDC per 2 hours per address. Wait or use a second address.

### `InsufficientFundsForRent` or `InsufficientFundsForFee` in a Privy settlement
Wallet has no SOL. Top up via https://faucet.solana.com/ (devnet).
