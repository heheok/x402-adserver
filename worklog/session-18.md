# Session 18 — Deploy to GCE VM (solboards.xyz) ✅

**Status:** ✅ Shipped. Live at `https://solboards.xyz` on a single GCE e2-small VM behind Cloudflare. Two infra follow-ups intentionally deferred post-hackathon (see bottom).

**Date completed:** 2026-05-03.

---

## Final topology

Single GCE **e2-small** VM (us-central1, Debian 12, Docker) running `docker compose -f docker-compose.prod.yml up`:

- **backend** — FastAPI on the internal docker network, SQLite on the VM's persistent disk.
- **caddy + spa (`x402-web`)** — multi-stage image baking the Vite build into Caddy, terminates TLS on 80/443, reverse-proxies `/api/*` to backend.

Cloudflare in front: orange-cloud (proxied) + **CF Origin Cert** (15-year ECDSA, hostnames `solboards.xyz, *.solboards.xyz`) baked into Caddy. Mode = **Full (strict)**. CF benefits: hidden origin IP, edge cache, DDoS shield. No Let's Encrypt anywhere.

Cost: ~$13/mo against GCP free-trial credits.

**Why this topology** (decided 2026-04-30, replacing the earlier Cloud Run + Cloud SQL plan): see `worklog/session-17.md`. Short version: single-VM compose is cheaper, simpler, keeps SQLite, and matches our existing prod-shape compose file.

---

## What shipped

### Cloudflare

- ✅ Domain **solboards.xyz** registered, DNS on Cloudflare. Locked 2026-05-03.
- ✅ Proxy mode = orange-cloud + CF Origin Cert. Locked 2026-05-03.
- ✅ Origin Cert generated (ECC, 15 years) — saved to `backend/.secrets/cf-origin/origin.pem` + `origin.key`, with offsite backup.
- ✅ SSL/TLS → Overview → encryption mode set to **Full (strict)**.
- ✅ Caching → Cache Rules → bypass cache for `URI Path matches "/index.html"` and `URI Path starts with "/api/"`. Static hashed assets (`/assets/*-[hash].js`) keep CF's default cache.
- ✅ DNS A record `solboards.xyz` → VM's reserved static IP, **proxied (orange)**. `www` added.

### GCE VM

- ✅ Provisioned e2-small (us-central1, Debian 12), Docker installed.
- ✅ Reserved static external IP.
- ✅ Firewall: 80/443 from 0.0.0.0/0, 22 from operator IP. (Tightening 80/443 to CF's published IP ranges deferred.)
- ✅ `x402-web` image built with `CADDYFILE=Caddyfile.cloudflare`.
- ✅ `scp -r backend/.env backend/.secrets/ vm:~/x402/backend/` (CF Origin Cert + Privy creds + GCS SA key).
- ✅ `chmod 600` on `backend/.secrets/cf-origin/origin.key` on the VM.
- ✅ `CADDYFILE=Caddyfile.cloudflare DOMAIN=solboards.xyz docker compose -f docker-compose.prod.yml up -d --build`.

### Verification

- ✅ CF→origin handshake: `curl -kI https://<vm-ip>/` returns 200 with the CF Origin cert.
- ✅ Edge: `curl -I https://solboards.xyz/` returns 200 with CF's edge cert (`cf-ray` present).
- ✅ CF Cache Rules took effect: `cf-cache-status` is `BYPASS` for `/`, `/api/health`, `/api/campaigns`; `HIT` (or `MISS` then `HIT`) for `/assets/*-[hash].js`.
- ✅ Full demo loop smoke-tested on `https://solboards.xyz` — login → faucet → fund → bid → proof → settle → refund.

### Nightly SQLite backup → GCS (shipped 2026-05-03)

- Bucket `gs://solboards-db-backups` (us-central1, UBLA), 7-day lifecycle for auto-delete.
- Host script `~/backup-db.sh` on the VM uses `sqlite3 .backup` (multi-process safe, doesn't block writers) into `/tmp/`, then `gcloud storage cp` to the bucket with date-keyed filename, then cleanup.
- Cron: daily at **03:00 UTC**.
- Auth: VM's default compute SA `657107916157-compute@developer.gserviceaccount.com` granted `roles/storage.objectAdmin` on the bucket. VM scopes widened to `cloud-platform` (default GCE scope is `devstorage.read_only`, which silently breaks any write workflow).
- Cost: ~$0.007/mo at current DB size.

---

## Deferred follow-ups (post-hackathon)

Both intentionally pushed past the Colosseum submission. Tracked in PLAN.md → Buffer.

- **Workload Identity for the GCS creatives bucket.** Today the JSON SA key sits in `backend/.secrets/`. Acceptable for the demo; replace with Workload Identity Federation before any production handoff.
- **Treasury topup cron migration.** If/when the Circle devnet faucet is upgraded out of the 20 USDC / 2h cap, move the topup cron from local Windows Task Scheduler to Cloud Scheduler + Cloud Function so it survives the operator's laptop being off.
