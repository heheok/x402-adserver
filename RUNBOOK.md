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

### Top up USDC — single address (slow path)
1. Open https://faucet.circle.com
2. Network: **Solana Devnet**
3. Paste `TREASURY_WALLET_ADDRESS`
4. Request USDC (capped at 20 USDC per 2 hours per address)

### Top up USDC — helper multiplex (recommended, ~2 min/day)

Circle's 2h-per-address cap is per-address, not per-IP — verified 2026-04-27.
We multiplex it via N helper wallets that get funded manually then swept back
to the treasury. With N=3 helpers you can pull 60 USDC every 2h instead of 20.

**One-time setup** (per Privy app):
```bash
docker compose run --rm backend python scripts/bootstrap_helpers.py
# (or --count 5 for more throughput)
```
Paste the printed `HELPER_WALLET_IDS=...` and `HELPER_WALLET_ADDRESSES=...`
lines into `backend/.env`, then:
```bash
docker compose up -d --force-recreate backend
```

**Daily routine** (~2 min):
1. Open https://faucet.circle.com (Solana / Devnet) in a browser.
2. For each address in `HELPER_WALLET_ADDRESSES`: paste, click claim, wait
   for confirmation. (Optionally also claim into `TREASURY_WALLET_ADDRESS`
   on the same pass — it counts as another address.)
3. Sweep helpers → treasury:
```bash
docker compose run --rm backend python scripts/sweep_helpers.py
```
Expect one Solscan link per non-empty helper. Exit code 0 = all swept.

### Rescue a one-off helper (not in env)
If you funded a wallet manually (e.g. via `create_helper_wallet.py`) and
need to sweep it once without adding it to `.env`:
```bash
docker compose run --rm backend python scripts/sweep_helpers.py \
    --wallet-id <id> --wallet-address <address>
```

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

**Stop the long-running backend first if `AUTO_PLAY_ENABLED=true`** in
`.env` (the demo default). Otherwise the live container's auto-play loop
hits the same SQLite DB through the bind mount and adds phantom plays
during the e2e's bid → proof retry window, breaking the spent-equals-one-play
assertion. The e2e's own lifespan force-disables auto-play via os.environ,
but that only affects its own container.

```bash
docker compose stop backend
docker compose run --rm backend python scripts/e2e_demo.py
docker compose start backend
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

## Publisher inventory (DMA targeting)

`/api/markets`, the wizard's targeting step, and the `/bid` DMA filter all
read from `backend/data/venues.json` — a flattened export of the demo
publisher's Mongo `screens` ⋈ `companies` collections. The file is
**gitignored** (publisher-private inventory data); each dev environment
re-provisions it via Mongo Compass. Loaded once at app startup.

### Refresh / re-export

Required when:
- Setting up a new dev environment.
- The publisher's Mongo inventory changes (new screens, new venues).

Run the aggregation in Compass against the publisher's database:

```json
[
  { "$lookup": {
      "from": "companies",
      "let": { "cid": "$companyId" },
      "pipeline": [
        { "$match": { "$expr": { "$eq": [ { "$toString": "$_id" }, "$$cid" ] } } }
      ],
      "as": "company"
  }},
  { "$unwind": "$company" },
  { "$project": {
      "_id": 0,
      "device_id":  { "$toString": "$_id" },
      "venue_id":   "$companyId",
      "dma":        { "$toLower": "$company.market" },
      "venue_name": "$company.companyName"
  }}
]
```

The `let`/`pipeline` form is mandatory: `screens.companyId` is a string but
`companies._id` is an ObjectId, so a plain `localField`/`foreignField`
lookup returns zero matches. Export the result as JSON to
`backend/data/venues.json` (Compass tends to append a redundant `.json`
extension — rename if needed).

Restart the backend to reload:
```bash
docker compose restart backend
```

Expected log line:
```
venues loaded: N devices across 6 DMAs (skipped: M empty-dma, 0 unknown-dma)
```

If the file is missing, the loader falls back to the committed
`backend/data/venues.example.json` — one fake venue per DMA, enough to
keep the demo loop runnable on a fresh clone before someone runs the
Compass export. Loud warning in the logs so it's clear which dataset is
loaded. With neither file present, `/bid` returns no-bid for every
request and `/api/markets` returns an empty list.

### DMA codes

The Mongo `market` field is short lowercase codes — `services/venues.DMA_LABELS`
canonicalizes them to the display labels surfaced everywhere else:

| Mongo code | Display label    |
| ---------- | ---------------- |
| `ny`       | New York         |
| `la`       | Los Angeles      |
| `sf`       | San Francisco    |
| `mia`      | Miami            |
| `bos`      | Boston           |
| `aus`      | Austin           |

Rows with empty or unknown `market` are skipped at load time with an info log.

### Bid request shape (publisher contract)

`/bid` requires `imp[0].ext.device_id` in addition to `imp[0].ext.wallet_id`
— the device id resolves to a DMA via the venues index, then the FIFO
matcher filters on `target_dmas` membership + schedule window. Missing or
unknown `device_id` → empty seatbid (no-bid).

---

## Protocol revenue wallet (Session 15)

The 2.5% protocol fee charged on every campaign creation is auto-transferred
from the campaign wallet to a dedicated Privy server wallet right after
x402 settle confirms. Lives separately from treasury so accounting stays
clean (treasury = faucet source, protocol-revenue = fee sink).

### One-time setup

```bash
docker compose run --rm backend python scripts/bootstrap_protocol_revenue.py
```

Paste the printed lines into `backend/.env`:
```
PROTOCOL_REVENUE_WALLET_ID=<id>
PROTOCOL_REVENUE_WALLET_ADDRESS=<address>
```
Then recreate (env_file gotcha):
```bash
docker compose up -d --force-recreate backend
```

The script is idempotent — if `PROTOCOL_REVENUE_WALLET_ID` is already set,
prints existing values and exits without creating anything new.

The wallet does **not** need any SOL or USDC ATA pre-creation. Each fee
transfer is paid for by the campaign wallet, and `build_usdc_transfer_tx`
creates the destination ATA idempotently as part of the same tx.

### Behaviour notes

- Fee transfer is **best-effort**: a failure logs at exception level but the
  campaign still flips ACTIVE. The fee then sits in the campaign wallet and
  gets refunded to the advertiser if the campaign is refunded — the advertiser
  is never short-changed; we just lose 2.5% revenue we would have collected.
- Each campaign's fee is one Privy tx, persisted as `Campaign.protocol_fee_tx_hash`
  + surfaced on the dashboard's campaign card with a Solscan link.
- The fee amount comes from `services/calc.compute_quote()` — same function
  the wizard's `/api/campaigns/quote` endpoint uses. Server-side single source
  of truth.

### Verify the wallet is collecting fees

```bash
docker compose run --rm backend python scripts/check_balance.py $PROTOCOL_REVENUE_WALLET_ADDRESS
```

Or on Solscan: `https://solscan.io/account/<address>?cluster=devnet` — each
campaign creation should show one inbound USDC transfer.

---

## Creative uploads (GCS)

Advertiser creatives uploaded via the dashboard wizard land in a public-read
GCS bucket. The bucket and a dedicated upload-only service account are
provisioned once per environment.

### One-time provisioning (CMD)
```cmd
gcloud config set project x402-494608

gcloud storage buckets create gs://x402-adserver-creatives --location=us-central1 --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding gs://x402-adserver-creatives --member=allUsers --role=roles/storage.objectViewer

gcloud iam service-accounts create x402-creatives-uploader

gcloud storage buckets add-iam-policy-binding gs://x402-adserver-creatives --member="serviceAccount:x402-creatives-uploader@x402-494608.iam.gserviceaccount.com" --role=roles/storage.objectCreator

if not exist backend\.secrets mkdir backend\.secrets
gcloud iam service-accounts keys create backend\.secrets\gcs-creatives-sa.json --iam-account=x402-creatives-uploader@x402-494608.iam.gserviceaccount.com
```

Bucket names are globally unique — if `x402-adserver-creatives` is taken, suffix
it (e.g. `x402-adserver-creatives-494608`) and update `GCS_BUCKET_NAME` to match.

### `.env` lines
```
GCS_BUCKET_NAME=x402-adserver-creatives
GCS_CREDENTIALS_JSON=/app/.secrets/gcs-creatives-sa.json
```
The path is the **container** path. `docker-compose.yml` mounts
`./backend/.secrets` to `/app/.secrets` read-only.

After editing `.env`: `docker compose up -d --force-recreate backend`.

### Sanity check
```bash
curl -F "file=@/path/to/1920x1080.jpg" \
     -H "Authorization: Bearer <privy-jwt>" \
     http://localhost:8000/api/creatives
```
Expected: `{"creative_id":"...","creative_url":"https://storage.googleapis.com/<bucket>/creatives/<uuid>.jpg",...}`.
The URL must open in a browser without auth.

### Rotate the SA key
```cmd
gcloud iam service-accounts keys create backend\.secrets\gcs-creatives-sa.json --iam-account=x402-creatives-uploader@x402-494608.iam.gserviceaccount.com
```
Then `docker compose up -d --force-recreate backend` to pick up the new file
(actually a restart suffices since the file path doesn't change, but recreate
is the safe default we use everywhere).

---

## Privy sanity check

Confirms the Privy app still has server-wallet access.
```bash
docker compose run --rm backend python scripts/probe_privy.py
```

Creates one throwaway wallet and lists existing wallets. Exit code 0 = healthy.

---

## Database

Currently SQLite at `backend/data/adserver.db`. Lives on the host via the
`./backend/data:/app/data` bind mount declared in `docker-compose.yml` —
named volume was retired in Session 14 so the user-supplied `venues.json`
(see DMA targeting section) sits next to the DB. Both files are gitignored.

### Reset the DB (wipe campaigns, settlements, nonces)
```bash
docker compose stop backend
rm backend/data/adserver.db
docker compose start backend
```
Tables (and Session 14 + 15 columns) are recreated automatically on startup
via `init_db()` + the dev-only `_dev_alter_table_for_existing_sqlite()` shim.

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
| `HELPER_WALLET_IDS`           | CSV of helper Privy wallet ids (sweep source)            | 12             |
| `HELPER_WALLET_ADDRESSES`     | CSV of helper Solana addresses (matching order)          | 12             |
| `PUBLISHER_API_KEY`           | Publisher API key for `/bid` and `/proof`                | 1              |
| `JWT_SERVER_SECRET`           | Signs `proof_context` tokens                             | 1              |
| `SOLANA_RPC_URL`              | Default: devnet                                          | 1              |
| `X402_FACILITATOR_URL`        | Default: `https://www.x402.org/facilitator`              | 1              |
| `CORS_ALLOW_ORIGINS`          | Comma-separated allowed origins (dashboard)              | 8              |
| `DEMO_PUBLISHER_WALLET`       | Demo-only: receives plays from `/simulate-play`+auto-play | 10            |
| `AUTO_PLAY_ENABLED`           | Demo-only: server background loop settles plays (off)    | 11             |
| `AUTO_PLAY_INTERVAL_SECONDS`  | Auto-play tick interval (default 15)                     | 11             |
| `GCS_BUCKET_NAME`             | Public-read GCS bucket for advertiser creatives          | 13             |
| `GCS_CREDENTIALS_JSON`        | Container path to GCS service-account JSON               | 13             |
| `DEMO_CPM`                    | Locked CPM in USD (default 0.5 = $0.0005/play)           | 15             |
| `OPERATING_HOURS_PER_DAY`     | Frequency constant; default 12                           | 15             |
| `PLAYS_PER_HOUR_PER_SCREEN`   | Frequency constant; default 12 (one every 5 min)         | 15             |
| `PROTOCOL_FEE_PCT`            | Default 0.025 (2.5%)                                     | 15             |
| `PROTOCOL_REVENUE_WALLET_ID`  | Privy wallet id (after `bootstrap_protocol_revenue`)     | 15             |
| `PROTOCOL_REVENUE_WALLET_ADDRESS` | Solana address of the protocol-fee sink wallet       | 15             |

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
