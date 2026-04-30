# Session 17 — Local prod-shape compose ✅

**Status:** ✅ Shipped 2026-04-30. End-to-end demo loop verified locally on `https://localhost`.

**Why this exists:** the original PLAN.md Session 17 was Cloud Run + Cloud SQL deployment prep. That topology has two real frictions for this project: (a) `batch_settler` is a long-running async loop, which fights Cloud Run's request-driven scale-to-zero model (forces `min-instances=1` or a Cloud Run Job + Scheduler split), and (b) SQLite → Postgres migration adds risk we can't afford at this point in the timeline (just stabilized the integer-microUSDC refactor in 16.9 and the NEEDS_REVIEW path in 16.8). The demo runs on devnet for one judge user; we don't need horizontal scale, we need a stable always-on host.

**Decision (2026-04-30):** swap the deploy target to a single **GCE e2-small VM running `docker compose -f docker-compose.prod.yml up`**, with Caddy doing TLS termination + static SPA + reverse proxy. SQLite stays on the VM's persistent disk via the existing bind mount — no Postgres migration. Cost ~$13/mo against GCP free-trial credits, vs ~$30-40/mo for the Cloud Run + Cloud SQL + VPC connector shape. Mainnet upgrade path is clean (same containers can move to Cloud Run if production demands later).

This session is the **local validation** of that prod-shape. Session 18 is the actual GCE deploy (gated on the domain).

---

## What shipped

### New files at repo root

- **`Caddyfile`** — `{$DOMAIN:localhost}` site block. Three handlers in order: `/solana-rpc(/*)` reverse-proxy to `https://api.devnet.solana.com` (with header_up -Origin -Referer to dodge Solana's anti-abuse 403 — see "Solana 403" below), `/api/* /health /bid /proof` to `backend:8000`, and a SPA fallback that serves `frontend/dist` with `try_files {path} /index.html` for client-side routes.
- **`docker-compose.prod.yml`** — three services: `backend` (Dockerfile-built, internal-only via `expose`, no `--reload`, no source bind-mount, only `./backend/data` and `./backend/.secrets` mounted), `caddy` (built from `frontend/Dockerfile.prod`, ports 80/443, named volumes `caddy_data` + `caddy_config` for cert persistence), and `DOMAIN=${DOMAIN:-localhost}` env so the same compose validates locally and ships to prod.
- **`frontend/Dockerfile.prod`** — multi-stage. Stage 1 (`node:20-alpine`): `npm ci`, `vite build`, with `VITE_PRIVY_APP_ID` and `VITE_API_BASE_URL` as ARGs (defaulted, overridable at build time). Stage 2 (`caddy:2-alpine`): copies `dist/` → `/srv/frontend` and `Caddyfile` → `/etc/caddy/Caddyfile`. Build context is repo root so the Dockerfile can pull both `frontend/` and the top-level Caddyfile. Output is a single immutable `x402-web` image — same artifact will push to Artifact Registry in Session 18.

### Frontend changes

- **`frontend/.env.production`** — `VITE_API_BASE_URL=` (empty → axios uses relative paths, browser hits Caddy on the same origin), `VITE_SOLANA_RPC_URL=/solana-rpc` (relative; resolved against `window.location.origin` at runtime).
- **`frontend/src/lib/rpc.ts`** (new) — `solanaRpcUrl()` helper. Falls back to `https://api.devnet.solana.com` when the env var is unset (dev compose), resolves relative paths against `window.location.origin` so the same prod build works on `https://localhost`, the future real domain, anywhere.
- **`frontend/src/components/wizard/StepReview.tsx`** — passes `rpcUrl: solanaRpcUrl()` to `createX402Client`. This was the actual fix for the funding-flow CORS issue: x402-solana's `network: "solana-devnet"` alone made it use the hardcoded default `https://api.devnet.solana.com` for its internal Connection, ignoring Privy's `solanaClusters` config.
- **`frontend/src/main.tsx`** — Privy `solanaClusters` rpcUrl now also reads from `solanaRpcUrl()`. Less critical (Privy's own RPC calls aren't on the critical demo path) but keeps a single source of truth.

### Backend change

- **`backend/app/routers/campaigns.py`** — `list_campaigns` filters out `CampaignStatus.DRAFT` rows so abandoned drafts (left over from a /api/campaigns POST that didn't complete the x402 funding step) don't pollute the dashboard. Drafts still in DB so the funding retry path keeps working; `GET /api/campaigns/:id` still returns them so any future "resume draft" UX can work without backend changes.

---

## Solana 403 (the gotcha worth remembering)

**Symptom:** the funding flow's `getAccountInfo` call to the USDC mint failed in the prod-shape with what the browser surfaced as a CORS error. After we proxied through Caddy at `/solana-rpc`, the failure mode changed to a JSON-RPC `{"code":403,"message":"Access forbidden"}` response from upstream.

**Root cause:** `https://api.devnet.solana.com` runs an anti-abuse layer that rejects any request whose `Origin` header isn't on their (undocumented) allowlist. `http://localhost:5173` is allowlisted; `https://localhost` is not. Server-side requests with no `Origin` are accepted.

- Direct `curl` (no Origin) → 200.
- `curl -H "Origin: https://localhost"` → 403.
- Browser via dev compose at `http://localhost:5173` → 200 (allowlisted origin).
- Browser via prod compose at `https://localhost` → 403 surfaced as CORS (response had no `Access-Control-Allow-Origin`).

**Fix:** strip Origin and Referer in the Caddy `/solana-rpc` reverse-proxy block. Server-to-server-shaped request → Solana accepts.

```
header_up -Origin
header_up -Referer
```

Saved as a memory (`project_x402_solana_rpc_origin_strip.md`) so we don't re-debug it.

---

## Local validation (2026-04-30)

- `docker compose down` → `docker compose -f docker-compose.prod.yml up -d --build` clean.
- Multi-stage build: `npm ci` cached on `package-lock.json` layer, `vite build` re-runs only on source changes. ~80 s cold, ~15 s incremental.
- `https://localhost` loads dashboard (browser cert warning expected — Caddy local CA).
- Login + faucet works → `/api/wallet/*` proxies cleanly through Caddy.
- Create campaign + fund via x402 works (after the Origin-strip fix). 5 RPC calls per fund, all 200, 60-200 ms each. That's the normal Solana-tx call count: getLatestBlockhash, getAccountInfo (mint), getAccountInfo (source ATA), getAccountInfo (dest ATA), sendTransaction.
- Auto-play continues to settle on-chain.
- Drafts no longer appear in the dashboard list after the backend filter.

---

## Files to NOT touch in Session 18

The compose, Caddyfile, Dockerfile.prod, and frontend env all use `${DOMAIN:-localhost}` / `window.location.origin` / relative paths so they work as-is on the real domain. **Nothing in this commit needs to change for the GCP deploy** beyond setting `DOMAIN=your-domain.com` in the VM's environment. That's the whole point of getting this right locally first.

---

## Pre-deploy checklist (move to Session 18)

- [ ] Domain decided (only blocker)
- [ ] GCE e2-small VM provisioned (us-central1, Debian 12, Docker installed)
- [ ] Static external IP reserved
- [ ] DNS A record pointing at the IP
- [ ] Firewall: 80/443 from 0.0.0.0/0, 22 from operator IP (or via IAP)
- [ ] `backend/.env` and `backend/.secrets/` scp'd to the VM
- [ ] `backend/data/` (or empty replacement) on the VM's persistent disk
- [ ] Push `x402-web` image to Artifact Registry, or build on the VM (decide based on bandwidth)
- [ ] `DOMAIN=your-domain.com docker compose -f docker-compose.prod.yml up -d --build` on the VM
- [ ] Caddy fetches Let's Encrypt cert on first boot (port 80 must be reachable for HTTP-01 challenge)
- [ ] Smoke-test the demo loop on the live URL

Demo flags (`AUTO_PLAY_ENABLED`, `/api/faucet`, `/api/campaigns/:id/simulate-play`, `DEMO_PUBLISHER_WALLET`) stay enabled for the hackathon submission — they're the demo. PLAN.md's earlier "must NOT ship to production" applied to a future mainnet deploy, not this devnet hackathon submission.
