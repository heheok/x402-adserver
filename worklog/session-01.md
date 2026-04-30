# Session 1 — Scaffold + plumbing ✅

**Date:** 2026-04-21

## Checklist

- [x] `PLAN.md` with full roadmap
- [x] `backend/` layout (app, routers, services, models)
- [x] FastAPI skeleton with health endpoint
- [x] SQLite + SQLAlchemy engine, session, `Base.metadata.create_all`
- [x] DB models: `campaigns`, `settlements`, `used_nonces`
- [x] Config via `pydantic-settings` + `.env.example`
- [x] Auth dependency stubs (`X-API-Key` for publisher, Privy-JWT placeholder)
- [x] Router stubs for `/bid`, `/proof`, `/api/campaigns`, `/api/wallet`, `/api/faucet`
- [x] `Dockerfile` for backend
- [x] `docker-compose.yml` (backend service only for now)
- [x] `.gitignore`, `README.md` run instructions

**Exit criteria:** `docker compose up backend` serves `GET /health` → 200, `GET /docs` lists all stub endpoints returning 501.

## Work log entries

- **2026-04-21 (Session 1):** scaffold committed. Backend boots in Docker, all stub endpoints return 501. SQLite tables auto-created. See `backend/README.md`.
- **2026-04-21 (Session 1 close-out):** Privy REST API validated against current docs (create, list, signAndSendTransaction all confirmed). User populated `backend/.env` with `PRIVY_APP_ID` / `PRIVY_APP_SECRET`, verified `/health` and `/docs` live. Cleared to start Session 2.
- **2026-04-21 (Session 1 probe):** `scripts/probe_privy.py` succeeded — listed 0 wallets, created test Solana wallet `joitr710uuxa942x6kjr4x2g` / `3pMCrwRq5tNy1GdonrPivP389eYjeeoGTiMZDtQmV8W9`. Server wallets are fully accessible on this Privy app. Fixed: added `./backend/scripts` volume mount to compose + `COPY scripts ./scripts` to Dockerfile so dev scripts ship with the container.
