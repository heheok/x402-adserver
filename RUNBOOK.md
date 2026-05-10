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

## Prod-shape compose (local validation)

`docker-compose.prod.yml` is what runs on the GCE VM (Session 18). Use it
locally to validate any change before deploying. The shape: backend on the
internal docker network only (no public 8000), Caddy on 80/443 doing TLS
termination + static SPA + reverse proxy, multi-stage `frontend/Dockerfile.prod`
that bakes the Vite build into the Caddy image. See `worklog/session-17.md`
for the full topology rationale.

### Stop dev first (always)

Both stacks bind-mount `./backend/data`, so running them at the same time
means two `batch_settler` loops racing on the same SQLite file. **Always
`docker compose down` before bringing up the prod-shape.**

### Start / stop / rebuild

```bash
docker compose down                                                 # stop dev stack first
docker compose -f docker-compose.prod.yml up -d --build              # start prod-shape (cold ~80s, incremental ~15s)
docker compose -f docker-compose.prod.yml logs -f caddy              # tail Caddy access + error logs
docker compose -f docker-compose.prod.yml logs -f backend            # tail FastAPI logs
docker compose -f docker-compose.prod.yml down                       # stop prod-shape
```

### Rebuild after code changes

Code is baked into images — `--reload` and the source bind-mount are gone.
Rebuild whichever container's source changed:

```bash
# React/Caddyfile changes → rebuild the multi-stage caddy+SPA image
docker compose -f docker-compose.prod.yml up -d --build caddy

# Python changes → rebuild the backend image
docker compose -f docker-compose.prod.yml up -d --build backend
```

After a frontend rebuild, **hard-refresh the browser** (Ctrl+Shift+R) — the
old JS bundle is otherwise cached and you'll see stale behavior.

### Open the prod-shape

- Dashboard: https://localhost
- Browser will warn about the cert. Caddy issues a self-signed cert from its
  local CA for any domain that resolves to `localhost`. Click through; the
  cert + CA persist via the `caddy_data` named volume so the warning only
  appears the first time per browser profile.
- API health (through Caddy): https://localhost/health

### Set DOMAIN for non-localhost testing

Caddy reads `${DOMAIN}` from the compose env (defaults to `localhost`).
There are also two TLS modes selected via `CADDYFILE`:

- `CADDYFILE=Caddyfile` (default) — auto-TLS. Local CA when DOMAIN is
  `localhost`, otherwise Let's Encrypt via HTTP-01. Use this only for
  staging hosts that point directly at the VM (no Cloudflare proxy in
  front).
- `CADDYFILE=Caddyfile.cloudflare` — static TLS via the Cloudflare Origin
  Cert mounted from `backend/.secrets/cf-origin/`. This is what the GCE
  deploy uses (CF orange-cloud + Full strict). Locally you can test the
  exact prod image by faking the cert dir with self-signed files.

```bash
# Staging host on a real domain WITHOUT Cloudflare in front (rare):
DOMAIN=staging.solboards.xyz docker compose -f docker-compose.prod.yml up -d --build

# Reproduce the prod CF-fronted image locally (with a placeholder cert):
CADDYFILE=Caddyfile.cloudflare docker compose -f docker-compose.prod.yml up -d --build
```

Port 80 must be publicly reachable for HTTP-01 (auto-TLS path only). The
Cloudflare path doesn't need any LE plumbing.

### Solana RPC 403 ("Access forbidden")

If the funding flow fails with a 403 from `/solana-rpc`, Solana's anti-abuse
layer is rejecting the proxy's headers. The Caddyfile strips `Origin` and
`Referer` for this exact reason — verify those `header_up -Origin` and
`header_up -Referer` lines are still in the `@solana_rpc` handle block. Quick
reproduction:

```bash
# Should succeed (200, "ok")
curl -sk -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}' \
  https://localhost/solana-rpc

# Should also succeed AFTER the strip; was 403 before the fix
curl -sk -X POST -H "Content-Type: application/json" -H "Origin: https://localhost" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}' \
  https://localhost/solana-rpc
```

See `worklog/session-17.md` and `memory/project_x402_solana_rpc_origin_strip.md`
for the full diagnostic.

### Cloudflare Origin Cert (prod TLS)

The GCE deploy uses CF orange-cloud (proxied) with **Full (strict)** SSL
mode. CF Universal SSL handles browser-facing TLS at the edge; Caddy
serves a 15-year ECDSA Origin Cert that CF validates on the CF→origin
hop. No Let's Encrypt anywhere.

**Files**

```
backend/.secrets/cf-origin/origin.pem    # certificate, public
backend/.secrets/cf-origin/origin.key    # private key, chmod 600
```

Both are gitignored under `backend/.secrets/`. The compose bind-mounts
the dir into Caddy at `/etc/caddy/cf-origin/:ro`. Only consumed when
`CADDYFILE=Caddyfile.cloudflare`.

**Generate / regenerate**

CF dashboard → SSL/TLS → Origin Server → Create Certificate:
- Private key type: **ECC** (= ECDSA P-256, smaller + faster than RSA)
- Hostnames: `solboards.xyz, *.solboards.xyz`
- Validity: **15 years**
- Save both files immediately — the private key is shown only once.

**Cache rules (matters for demo-day rebuilds)**

CF caches static responses by default. Without exceptions, judges may
see stale `index.html` after a deploy. CF dashboard → Caching → Cache
Rules:
- `URI Path matches "/index.html"` → bypass cache
- `URI Path starts with "/api/"` → bypass cache
- Static hashed assets (`/assets/*-[hash].js`) keep CF's default cache —
  Vite's content hashing makes them safely cacheable.

If you forget to set the rules and ship a stale-looking deploy, manual
purge: CF dashboard → Caching → Configuration → Purge Everything (or
purge by URL).

**Rotate (15 years from now, or sooner if compromised)**

1. CF dashboard → SSL/TLS → Origin Server → revoke the old cert.
2. Generate a new one (same steps as above).
3. Replace `backend/.secrets/cf-origin/origin.pem` + `origin.key` on the
   VM.
4. `docker compose -f docker-compose.prod.yml restart caddy` to pick up
   the new files (Caddy reads them on boot).

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
   OR USE THE faucet-fill.js on devtools on faucet website for automatic fill...

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

## Reclaim stranded SOL from terminated campaign wallets

Privy can't delete wallets, so every campaign that reaches a terminal status
(REFUNDED, COMPLETED, EXPIRED) leaves its unburned seed SOL stranded on-chain
unless something sweeps it. As of 2026-05-10 the live `/refund` handler does
this automatically (see PLAN.md "SOL gas subsidy model — refund-time leak");
the script below recovers SOL stranded **before** that fix and from
COMPLETED/EXPIRED campaigns that never had refund clicked.

```bash
# Dry-run (default) — prints what would happen, no on-chain txs.
docker compose run --rm backend python scripts/recover_refunded_sol.py

# Sanity-check on one campaign before bulk:
docker compose run --rm backend python scripts/recover_refunded_sol.py \
    --campaign-id <id> --execute

# Bulk execute:
docker compose run --rm backend python scripts/recover_refunded_sol.py --execute

# Restrict to one terminal status:
docker compose run --rm backend python scripts/recover_refunded_sol.py \
    --status completed
```

Filters: `status IN (refunded, completed, expired)` only. EXPIRED wallets
with on-chain USDC > $0.001 are skipped (they need a refund click first —
that path moves the USDC AND sweeps the SOL). Active/paused/draft are
never touched. Idempotent: re-running on a swept wallet is a no-op.
Per-campaign try/except so one bad row doesn't kill the run. Leaves a
1,000,000-lamport buffer per wallet (~$0.20 mainnet, dust on devnet).

ATA rent (~2,039,280 lamports/wallet) is **not** recovered by this script —
the USDC token account stays open. See PLAN.md for the deferred ATA-close work.

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

This is **especially disruptive now** with multi-play per tick — a single
auto-play burst (10–20 plays/tick) can drain the e2e's tiny-budget tests
within seconds and turns 13/13 into 9/11 typical. Always stop first.

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

## Audit reconciliation

`scripts/audit_ledger.py` is a read-only health check that compares DB state
against on-chain USDC balances. Run it post-deploy, after a stress test, or
whenever a user reports a payment issue. ~5 seconds runtime.

```bash
docker compose run --rm backend python scripts/audit_ledger.py
```

Three sections, each with its own pass criteria:

### 1. Publisher reconciliation

For each `publisher_wallet` that has received any confirmed settlement, sums
`amount_usdc` from the DB and compares to on-chain USDC balance.

| Flag    | Meaning                              | Action                                                                                                                           |
| ------- | ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| `OK`    | DB sum within 1e-6 of on-chain       | nothing                                                                                                                          |
| `SHORT` | on-chain _less_ than DB says we paid | **bug** — settlement minted but didn't land                                                                                      |
| `MORE`  | on-chain _more_ than DB says         | external inflow (other ad networks, manual transfers) — fine for real publishers, suspicious for the demo publisher in isolation |

### 2. Campaign wallet reconciliation

Per campaign, expected on-chain USDC depends on lifecycle:

| Status                                  | Expected USDC                                                                     |
| --------------------------------------- | --------------------------------------------------------------------------------- |
| `draft`                                 | 0 (never funded)                                                                  |
| `active`/`paused`/`completed`/`expired` | `budget - spent` (+ `protocol_fee_amount` if fee tx never confirmed)              |
| `refunded`                              | 0 (+ orphaned fee if `protocol_fee_tx_hash` is null — see BACKEND-REVIEW.md §1.1) |

Comparison is **exact integer microUSDC equality** (Session 16.9 — money is
int micro end-to-end, no tolerance band). Any non-zero diff flags
`DRIFT` unless explained by another column:

| Flag           | Meaning                                              | Action                                    |
| -------------- | ---------------------------------------------------- | ----------------------------------------- |
| `OK`           | actual == expected, no review rows                   | nothing                                   |
| `IN-FLIGHT`    | actual is HIGH by exactly the `pending` column total | wait — batch settler hasn't flushed yet   |
| `NEEDS-REVIEW` | rows are parked awaiting operator triage             | run `scripts/triage_stuck.py list`        |
| `DRIFT`        | unexplained mismatch                                 | investigate via the forensic recipe below |

The `review` column shows `N/<sum>` of NEEDS_REVIEW rows for the campaign.
A row can have a non-empty `review` AND `OK` flag simultaneously — the
common case is "broadcast landed but worker died before \_mark_confirmed,"
where on-chain is correct but the DB row hasn't caught up. The summary
line at the bottom prints `🔍 NEEDS_REVIEW (run scripts/triage_stuck.py list)`
with the total stuck amount whenever any review rows exist.

The script also prints `Total stranded USDC across refunded campaigns` and
`Of that, declared orphaned fee` — these quantify §1.1's leak in dollars.

### 3. Service wallets

Just prints SOL + USDC for treasury, protocol revenue, helpers, and demo
publisher. No expected vs actual — these fluctuate by design.

### Forensic recipe — what did this tx actually transfer?

When the audit shows DRIFT and you need to know _exactly_ what happened
on-chain, decode the tx's pre/post token balances:

```bash
docker compose exec backend python -c "
import asyncio, sys
sys.path.insert(0, '/app')
from solana.rpc.async_api import AsyncClient
from solders.signature import Signature
from app.config import get_settings

TX = '<tx hash from DB or Solscan>'

async def main():
    settings = get_settings()
    async with AsyncClient(settings.solana_rpc_url) as c:
        sig = Signature.from_string(TX)
        resp = await c.get_transaction(sig, max_supported_transaction_version=0, encoding='jsonParsed')
        meta = resp.value.transaction.meta
        pre  = {b.account_index: float(b.ui_token_amount.ui_amount or 0) for b in (meta.pre_token_balances or [])}
        post = {b.account_index: float(b.ui_token_amount.ui_amount or 0) for b in (meta.post_token_balances or [])}
        for i in sorted(set(pre) | set(post)):
            print(f'idx={i} delta={post.get(i,0) - pre.get(i,0):+.6f}')

asyncio.run(main())
"
```

Used 2026-04-28 to confirm a refunded campaign's stranded 0.031 USDC was
pre-Session-16.5 dedup damage (refund tx really did send `budget - spent`,
the strand was 62 phantom-confirmed plays where the on-chain transfer
network-deduped before the memo fix).

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

## Batch settlement (Session 16.8)

`/proof`, simulate-play, and auto-play don't broadcast on-chain anymore —
they write a `pending` row to `settlements` and return sub-100ms. A
background loop in `app/services/batch_settler.py` flushes pending rows
every `BATCH_FLUSH_INTERVAL_SECONDS`, grouping by `(campaign_id,
publisher_wallet)` and emitting **one Solana tx per group**. Replaces
the per-play settlement model that was fragile under devnet RPC rate
limits.

### Settings (backend/.env)

```
BATCH_ENABLED=true
BATCH_FLUSH_INTERVAL_SECONDS=5
BATCH_MAX_ROWS_PER_FLUSH=100
```

Recreate the container to pick up env changes (env_file gotcha at the top
of this doc).

### State machine

```
pending ── batcher claims ──▶ flushing ── tx confirms ──▶ confirmed
                                  │
                                  ├── on-chain status uncertain ──▶ needs_review (manual triage)
                                  │   (Privy 5xx after broadcast, or 400 "already exists",
                                  │    or RPC blind on confirmation poll)
                                  │
                                  └── Privy refused pre-broadcast ──▶ failed (compensating UPDATE)
```

`pending` carries a reserved budget (the `/proof` atomic UPDATE moved
`spent` at queue time). `needs_review` keeps the reservation — operator
decides via `triage_stuck.py` whether the on-chain tx landed (then
`confirm`) or didn't (then `compensate`, which releases spent like
`failed` does). `failed` is reserved for the Privy-rejected-pre-broadcast
case where we have positive evidence the broadcast did NOT happen.
Replay protection holds across all three terminal states because the
nonce stays consumed.

**Why we don't auto-retry uncertain rows:** Privy's `reference_id` is a
post-broadcast recorder, not a pre-broadcast blocker (verified
2026-04-30, see PLAN.md must-fix #4). Re-broadcasting a row whose
reference_id Privy has already recorded causes a real on-chain
duplicate-payment despite Privy returning 400 "already exists" — we
watched a paused campaign drain $0.139 across 25 minutes from two
cycling rows. The new behavior parks once and stops, bounding loss to
at most one batch amount.

### Monitor pending count

```bash
docker compose exec backend sqlite3 /app/data/adserver.db \
  "SELECT status, COUNT(*) FROM settlements GROUP BY status;"
```

Or via the audit:

```bash
docker compose run --rm backend python scripts/audit_ledger.py
# Per-campaign 'pending' column shows N/sum(amount); IN-FLIGHT flag
# replaces DRIFT for campaigns with pending settlements that haven't
# transferred yet.
```

### Watch the loop live

```bash
docker compose logs -f backend | grep "batch settler\|batch flush"
```

Per-tick log line: `batch settler tick — confirmed=N failed=M left_pending=K`.
Per-group log lines:

- `batch flush confirmed campaign=… rows=N tx=…` — happy path.
- `batch flush RPC-blind, parked NEEDS_REVIEW` — got a tx_hash from Privy
  but couldn't confirm via getSignatureStatuses; row goes to operator triage.
- `batch flush post-broadcast uncertain, parked NEEDS_REVIEW` — Privy
  returned 5xx or 400 "already exists" without a tx_hash we can trust.
- `batch flush DEFINITIVE failure` — clean Privy refusal pre-broadcast,
  rows go to `failed` with compensation.
- `batch settler startup: parked N orphaned FLUSHING rows -> NEEDS_REVIEW`
  — fired once at process start when previous worker died mid-flush.

### Manually trigger a flush

```bash
docker compose exec backend python -c \
  "import asyncio; from app.services.batch_settler import flush_all; \
   r = asyncio.run(flush_all()); print(r)"
```

Returns a `FlushResult` with confirmed/failed/left_pending counts. Useful
when ops needs to drain everything before stopping the backend.

### Disable batching (E2E testing)

```bash
# In .env
BATCH_ENABLED=false
```

The lifespan loop no longer starts. `/proof` still writes pending rows;
callers must manually call `flush_all()` to settle. `scripts/e2e_demo.py`
sets this in `os.environ` at script start and inserts a `flush_all()`
call after each `/proof` step.

### Flush-on-refund property

`refund_campaign` synchronously calls `flush_campaign(id)` before
computing `remaining = budget - spent`. If pending rows can't be
flushed (RPC blind across multiple retries), refund returns 503 and
the advertiser retries shortly. If any rows are in `needs_review`,
refund returns 409 — the operator must triage those first (otherwise
we'd refund USDC that may have already been paid to the publisher).
**Never proceed with refund while pending or needs_review rows exist.**

---

## Triage stuck settlements (NEEDS_REVIEW)

Settlement rows in `needs_review` are batches whose on-chain status the
batcher couldn't determine for itself: process killed mid-flush, or Privy
returned 5xx / 400 "already exists" mid-broadcast. The fix is operator-
driven because the wrong call (re-broadcast) is a live wallet drain;
see "Why we don't auto-retry uncertain rows" above.

### When you'll see them

- After a backend crash / OOM / kill that landed during a flush window.
- After Privy or its CDN had a hiccup. Audit shows a `review` column
  on the affected campaign and the summary line
  `🔍 NEEDS_REVIEW (run scripts/triage_stuck.py list): X USDC`.
- After `/api/campaigns/{id}/refund` returns 409 with the message
  `campaign has N settlement(s) requiring manual review`.

### List

```bash
docker compose exec backend python scripts/triage_stuck.py list
```

Groups by `(campaign, publisher)` — same shape the batcher would have
flushed in one tx. Each group prints the campaign name, wallet (with
Solscan link), publisher, batch memo (`x402-batch:<first_nonce[:8]>-<n>`),
the row IDs, and the total amount.

### Find the on-chain truth

The deterministic question to answer: **did the batch's tx actually land
on-chain?** Two ways:

**A. Eyeball Solscan.** Open the wallet's URL from the list output, scroll
the recent transactions, look for one whose memo contains the batch memo
(e.g. `x402-batch:auto-017-15`). The tx detail page on Solscan shows the
memo program instruction's data field.

**B. Memo lookup snippet.** When you have many groups to triage or want
to script, use this one-off (also useful as a template; not yet a CLI
subcommand):

```bash
docker compose exec backend python -c "
import asyncio
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.signature import Signature
from app.config import get_settings

WALLET = '<campaign wallet from triage list>'
TARGET_MEMO = '<batch memo from triage list, e.g. x402-batch:auto-017-15>'
MEMO_PROGRAM_ID = 'MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr'

async def main():
    settings = get_settings()
    async with AsyncClient(settings.solana_rpc_url) as c:
        sigs_resp = await c.get_signatures_for_address(Pubkey.from_string(WALLET), limit=50)
        for s in (sigs_resp.value or []):
            tx_resp = await c.get_transaction(Signature.from_string(str(s.signature)),
                encoding='jsonParsed', max_supported_transaction_version=0)
            if not tx_resp.value: continue
            for ix in (tx_resp.value.transaction.transaction.message.instructions or []):
                if str(getattr(ix, 'program_id', '')) == MEMO_PROGRAM_ID:
                    parsed = getattr(ix, 'parsed', None)
                    if isinstance(parsed, str) and TARGET_MEMO in parsed:
                        print(f'MATCH: {s.signature}'); return
        print('NO MATCH — broadcast did not land')

asyncio.run(main())
"
```

### Decide

| On-chain state                                                     | Action                                                                                                                                                                                                             |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Tx with matching memo found, status=confirmed/finalized            | `triage_stuck.py confirm --row-ids <ids> --tx-hash <found>`                                                                                                                                                        |
| No matching memo after blockhash window (~2 min past `created_at`) | `triage_stuck.py compensate --row-ids <ids>`                                                                                                                                                                       |
| Multiple matching memos for the same batch                         | **Real double-broadcast.** Confirm with the first hash; the second is a duplicate payment that left the campaign wallet — accept as drift on devnet, or use `cleanup_drift_reverse.py` to claw back if it matters. |

### Confirm

```bash
docker compose exec backend python scripts/triage_stuck.py confirm \
  --row-ids id1,id2,id3 --tx-hash <signature>
```

Marks the rows `confirmed` with the supplied tx hash. Does NOT touch
`spent` — the publisher really did get paid by that tx, and the original
`/proof` UPDATE already accounted for it.

### Compensate

```bash
docker compose exec backend python scripts/triage_stuck.py compensate \
  --row-ids id1,id2,id3
```

Marks the rows `failed` AND decrements `campaign.spent` by their summed
amount AND flips `completed → active` if the refund creates room for one
more play. Use ONLY when you have positive evidence the broadcast did NOT
land (memo lookup returned no match, blockhash window has passed).

### Cleanup verification

After every triage action:

```bash
docker compose exec backend python scripts/triage_stuck.py list   # should be empty
docker compose run --rm backend python scripts/audit_ledger.py    # campaign should reconcile
```

### Restart resilience

- **Pending rows** survive a restart. The batcher claims them on the next
  tick. Safe because they were never broadcast.
- **Flushing rows** are presumed orphaned (their worker died) and flipped
  to `needs_review` on startup. The startup log line is
  `batch settler startup: parked N orphaned FLUSHING rows -> NEEDS_REVIEW`.
  Operator runs `scripts/triage_stuck.py list` to surface them.

We deliberately do NOT auto-retry orphaned flushing rows. Privy's
`reference_id` does not actually block re-broadcasts (verified
2026-04-30 — Privy returns 400 "already exists" but the new tx still
lands on-chain), so any re-broadcast of an orphaned row whose
reference_id Privy already saw is a live wallet drain. The triage CLI
gives the operator the explicit gate to verify on Solscan whether the
original tx landed before any DB mutation. See must-fix #4 in PLAN.md
for the production-grade fix that would re-enable automation.

### Tuning

- **5s interval** is the demo default. Production probably wants 30–60s
  to amortize RPC pressure over fewer batches.
- **2s polling** inside `wait_for_tx_confirmation` (configured in
  batch_settler) keeps `getSignatureStatuses` under devnet's 4 req/s/method
  limit even with 4–5 concurrent flushes. Don't drop below 1s without
  switching to a private RPC.
- **Sequential flush** within a tick (not parallel). Keeps RPC pressure
  flat. At hackathon scale (≤10 active campaigns) the wall-clock cost is
  bounded; large fleets would parallelize with rate-limit gating.

---

## Auto-play (demo-only)

Server-side background loop that fires `random.randint(MIN, MAX)` plays
**concurrently** every `AUTO_PLAY_INTERVAL_SECONDS` across active + funded
campaigns. Only meant for the dashboard demo — production publishers drive
`/bid` + `/proof` themselves. **Must be off in any deployed environment.**

### Enable / disable

Edit `backend/.env`:

```
AUTO_PLAY_ENABLED=true              # or false
AUTO_PLAY_INTERVAL_SECONDS=15       # tick interval
AUTO_PLAY_PLAYS_PER_TICK_MIN=10     # plays per tick lower bound
AUTO_PLAY_PLAYS_PER_TICK_MAX=20     # plays per tick upper bound
DEMO_PUBLISHER_WALLET=<address>     # who receives the settlements
```

Then **recreate** the container (restart won't pick up env changes — see the
env_file gotcha above):

```bash
docker compose up -d --force-recreate backend
```

### Calibrating the rate

Calculator math says `screens × 144 plays/screen/day`. To hit roughly that
rate on the dashboard:

```
target_plays_per_sec ≈ (screens × 144) / 86400
mean_plays_per_tick   = target_plays_per_sec × AUTO_PLAY_INTERVAL_SECONDS
```

For a 1-DMA SF demo (115 screens) → ~1 play/sec → ~15 plays/tick at 15 s
interval. Setting `MIN=10`, `MAX=20` lands on that with natural variance.

### Verify it's running

```bash
docker compose logs backend | grep auto-play | tail -25
```

Expected: one `auto-play loop starting — interval=15s` line, then a burst of
`auto-play: campaign=... tx=...` lines clustered per tick (one per play).

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

- Picks at **random** (with replacement) from campaigns with `status=active`
  AND `remaining >= cpm_price/1000`. A single tick can land multiple plays
  on the same campaign; each pick re-randomizes the device.
- Each play opens its own DB session (concurrent writes safe). The
  SQLAlchemy connection pool is sized 30 + 60 overflow so 10–20 concurrent
  Privy awaits don't exhaust it.
- Each USDC transfer carries an SPL Memo program v2 instruction tagged with
  the nonce, otherwise concurrent transfers with identical (from, to,
  amount) within one blockhash window get deduped by the network to one
  on-chain tx. The memo bytes make each tx unique. This is internal — no
  publisher contract change.
- A campaign drained mid-tick (manual simulate, external `/proof`) logs a
  harmless `auto-play skipped … status=409` on the next tick that picks it.
- Failed on-chain settlements land in the `settlements` table with
  `status=failed` the same way manual ones do, AND **the budget reservation
  is automatically refunded** via a compensating UPDATE — failed plays no
  longer burn budget. Clear failed rows with `scripts/retry_settlements.py`.

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
  {
    "$lookup": {
      "from": "companies",
      "let": { "cid": "$companyId" },
      "pipeline": [
        { "$match": { "$expr": { "$eq": [{ "$toString": "$_id" }, "$$cid"] } } }
      ],
      "as": "company"
    }
  },
  { "$unwind": "$company" },
  {
    "$project": {
      "_id": 0,
      "device_id": { "$toString": "$_id" },
      "venue_id": "$companyId",
      "dma": { "$toLower": "$company.market" },
      "venue_name": "$company.companyName"
    }
  }
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

| Mongo code | Display label |
| ---------- | ------------- |
| `ny`       | New York      |
| `la`       | Los Angeles   |
| `sf`       | San Francisco |
| `mia`      | Miami         |
| `bos`      | Boston        |
| `aus`      | Austin        |

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
  - surfaced on the dashboard's campaign card with a Solscan link.
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

## Content moderation (Vertex AI)

Each upload to `/api/creatives` is classified by Gemini 2.5 Flash via Vertex AI
against a three-tier policy (auto-reject NSFW/scam/quality, review for
alcohol/political/competitor brands, approve otherwise). Auth is a dedicated
service account `x402-moderation-classifier` bound only to
`roles/aiplatform.user` (least privilege — separate from the GCS uploader SA).

### One-time provisioning (CMD)

```cmd
gcloud config set project x402-494608

gcloud services enable aiplatform.googleapis.com

gcloud iam service-accounts create x402-moderation-classifier --display-name="x402 moderation classifier (Vertex AI)"

gcloud projects add-iam-policy-binding x402-494608 --member="serviceAccount:x402-moderation-classifier@x402-494608.iam.gserviceaccount.com" --role=roles/aiplatform.user

if not exist backend\.secrets mkdir backend\.secrets
gcloud iam service-accounts keys create backend\.secrets\moderation-classifier-sa.json --iam-account=x402-moderation-classifier@x402-494608.iam.gserviceaccount.com
```

### `.env` lines

```
MODERATION_ENABLED=true
MODERATION_MODEL=gemini-2.5-flash
VERTEX_PROJECT_ID=x402-494608
VERTEX_LOCATION=us-central1
MODERATION_CREDENTIALS_JSON=/app/.secrets/moderation-classifier-sa.json
```

### Disable for local dev

`MODERATION_ENABLED=false` short-circuits to instant approve — use this for
`scripts/e2e_demo.py` runs and any local work where you don't want to burn
Vertex quota or load the SA key.

### Inspect moderation rows

```bash
# Default = pending review queue
docker exec solboards-backend python scripts/list_pending_moderation.py

# Other filters
docker exec solboards-backend python scripts/list_pending_moderation.py --status reject
docker exec solboards-backend python scripts/list_pending_moderation.py --status all --limit 200
docker exec solboards-backend python scripts/list_pending_moderation.py --advertiser did:privy:abc...
docker exec solboards-backend python scripts/list_pending_moderation.py --id <creative_id>
```

Read-only this session — manual approve/reject CLIs are deferred. Until then,
the dashboard advertiser sees their `review` upload succeed and the campaign
launches normally; the row is just visible to the operator.

### Cost expectations

Per-image: ~2k input tokens (1080p image + system policy prompt) + ~150 output
tokens at Gemini 2.5 Flash rates ($0.30/M in, $2.50/M out) = **~$0.001/image**.
At hackathon volume (dozens of uploads) the entire bill is sub-dollar. See
`worklog/session-19.5.md` for the full pricing comparison vs. Vision API.

### Rotate the SA key

```cmd
gcloud iam service-accounts keys create backend\.secrets\moderation-classifier-sa.json --iam-account=x402-moderation-classifier@x402-494608.iam.gserviceaccount.com
```

Then `docker compose up -d --force-recreate backend`.

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

### Hygiene reset (drain + DB wipe)

The "Reset the DB" command above only wipes Python-side state. After running
the demo for a while you also accumulate stranded USDC in per-campaign Privy
server wallets, helpers, the protocol-revenue wallet, and the demo publisher.
Privy doesn't support wallet deletion, so the wallets persist forever — but
their contents can be swept back to treasury before wiping the DB.

This is the right routine pre-deploy or whenever you want a clean baseline
for an audit run.

Use it to draw a known-clean line: any subsequent drift in `audit_ledger.py`
is a real bug, not legacy.

#### Sequence

```bash
# 1. Stop the long-running backend (auto-play would fight the sweep on shared SQLite)
docker compose stop backend

# 2. Dry-run sweep — prints every wallet + USDC/SOL it would touch, no on-chain txs
docker compose run --rm backend python scripts/sweep_to_treasury.py

# 3. Eyeball the dry-run. Confirm the destination is your treasury and the
#    amounts look sane. Then execute:
docker compose run --rm backend python scripts/sweep_to_treasury.py --execute

# 4. Wipe the DB
rm backend/data/adserver.db

# 5. Restart — create_all rebuilds empty tables on boot
docker compose start backend

# 6. Confirm clean baseline
docker compose run --rm backend python scripts/audit_ledger.py
```

#### What gets swept

- All campaign wallets in the DB (`campaigns.wallet_id` / `.wallet_address`)
- Helper wallets (`HELPER_WALLET_IDS` / `_ADDRESSES`)
- Protocol revenue wallet
- Demo publisher (looked up via Privy `list_wallets` by address match)

#### What does NOT get swept

- **Treasury** — the destination
- **Advertiser embedded wallets** — owned by Privy users, not server wallets.
  The dev's own test wallet keeps its funds; on next login the dashboard shows
  whatever was left there. If a controlled simulation needs a clean advertiser
  wallet, sweep that one wallet manually via a one-off Privy `sign_and_send`.

#### Gas-seed pre-pass

Wallets with USDC but zero SOL (typically protocol revenue + demo publisher,
which only ever received USDC inflows) can't pay their own tx fee. The script
detects this and treasury fronts 0.001 SOL before the USDC sweep. Total cost
~0.002 SOL across the two wallets — negligible.

#### Failure modes

- **`transaction_broadcast_failure` retry warnings** during the gas-seed
  → USDC sweep window are expected. Privy's simulation read-replica trails
  devnet by tens of seconds; the existing retry-with-backoff in
  `sign_and_send_solana` handles it. Each affected wallet typically needs
  2-3 retries; `reference_id` gives Privy-side idempotency so duplicate
  broadcasts are safe.
- If the sweep fails partway, just re-run — the script reads live balances
  on each invocation, so partial failures are idempotent.

#### Post-reset

- Helpers, protocol-revenue, and demo-publisher each retain ~0.001 SOL
  (the `SOL_BUFFER_LAMPORTS` left for future fee headroom). Their accounts
  stay alive on Solana.
- Pre-existing campaign wallets in Privy still exist, but with ~0 USDC and
  ~0 SOL above the buffer. Future flows that try to reuse them will need
  to re-seed — but in practice every new campaign creates a fresh wallet,
  so they're orphans.

---

## Environment variables reference

Set in `backend/.env` (copy from `backend/.env.example` to start).

| Var                               | Purpose                                                   | Set in Session |
| --------------------------------- | --------------------------------------------------------- | -------------- |
| `PRIVY_APP_ID`                    | Privy app credentials                                     | 1              |
| `PRIVY_APP_SECRET`                | Privy app credentials                                     | 1              |
| `TREASURY_WALLET_ID`              | Privy wallet id (after `bootstrap_treasury`)              | 2              |
| `TREASURY_WALLET_ADDRESS`         | Solana address of the treasury wallet                     | 2              |
| `FAUCET_AMOUNT_USDC`              | How much USDC the faucet hands out per call               | 2              |
| `FAUCET_LIFETIME_CAP_USDC`        | Lifetime per-Privy-DID drain ceiling (default 100)        | 19             |
| `HELPER_WALLET_IDS`               | CSV of helper Privy wallet ids (sweep source)             | 12             |
| `HELPER_WALLET_ADDRESSES`         | CSV of helper Solana addresses (matching order)           | 12             |
| `PUBLISHER_API_KEY`               | Publisher API key for `/bid` and `/proof`                 | 1              |
| `JWT_SERVER_SECRET`               | Signs `proof_context` tokens                              | 1              |
| `SOLANA_RPC_URL`                  | Default: devnet                                           | 1              |
| `X402_FACILITATOR_URL`            | Default: `https://www.x402.org/facilitator`               | 1              |
| `CORS_ALLOW_ORIGINS`              | Comma-separated allowed origins (dashboard)               | 8              |
| `DEMO_PUBLISHER_WALLET`           | Demo-only: receives plays from `/simulate-play`+auto-play | 10             |
| `AUTO_PLAY_ENABLED`               | Demo-only: server background loop settles plays (off)     | 11             |
| `AUTO_PLAY_INTERVAL_SECONDS`      | Auto-play tick interval (default 15)                      | 11             |
| `AUTO_PLAY_PLAYS_PER_TICK_MIN`    | Plays per tick lower bound (default 1)                    | 16             |
| `AUTO_PLAY_PLAYS_PER_TICK_MAX`    | Plays per tick upper bound (default 1)                    | 16             |
| `GCS_BUCKET_NAME`                 | Public-read GCS bucket for advertiser creatives           | 13             |
| `GCS_CREDENTIALS_JSON`            | Container path to GCS service-account JSON                | 13             |
| `MODERATION_ENABLED`              | If false, skip Vertex AI call and auto-approve            | 19.5           |
| `MODERATION_MODEL`                | Vertex Gemini model id (default `gemini-2.5-flash`)       | 19.5           |
| `VERTEX_PROJECT_ID`               | GCP project for Vertex AI calls                           | 19.5           |
| `VERTEX_LOCATION`                 | Vertex region (default `us-central1`)                     | 19.5           |
| `MODERATION_CREDENTIALS_JSON`     | Container path to the moderation classifier SA key        | 19.5           |
| `DEMO_CPM`                        | Locked CPM in USD (default 0.5 = $0.0005/play)            | 15             |
| `OPERATING_HOURS_PER_DAY`         | Frequency constant; default 12                            | 15             |
| `PLAYS_PER_HOUR_PER_SCREEN`       | Frequency constant; default 12 (one every 5 min)          | 15             |
| `PROTOCOL_FEE_PCT`                | Default 0.025 (2.5%)                                      | 15             |
| `PROTOCOL_REVENUE_WALLET_ID`      | Privy wallet id (after `bootstrap_protocol_revenue`)      | 15             |
| `PROTOCOL_REVENUE_WALLET_ADDRESS` | Solana address of the protocol-fee sink wallet            | 15             |

---

## Common errors

### `treasury not configured` (503 on `/api/faucet`)

`TREASURY_WALLET_ID` or `TREASURY_WALLET_ADDRESS` is missing/wrong in `.env`.
Re-check `docker compose exec backend env | grep TREASURY`, then recreate
(not restart) the container: `docker compose up -d --force-recreate backend`.

### `faucet lifetime cap reached` (429 on `/api/faucet`)

Advertiser hit `FAUCET_LIFETIME_CAP_USDC` (default 100). The cap counts
`PENDING + CONFIRMED` rows in `faucet_claims` for that Privy DID;
`FAILED` rows don't count, `RETURNED` rows don't count. To clear the cap
for one advertiser without changing the env (e.g. judge ran out mid-demo):

```sql
DELETE FROM faucet_claims WHERE advertiser_id='did:privy:...';
```

On the VM:
```bash
docker compose -f docker-compose.prod.yml exec backend \
  sqlite3 /app/data/adserver.db \
  "DELETE FROM faucet_claims WHERE advertiser_id='did:privy:XXX';"
```

Alternatively, the user can drain their wallet to treasury via their own
client; `POST /api/faucet/reset` (called automatically after a successful
drain, or manually with their bearer token) marks the caller's outstanding
claims as `RETURNED` and releases the cap. Trust-based for the demo —
no on-chain verification of the drain tx — see `BUSINESS-CONSTRAINTS.md §6`.

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
