# x402 Ad Server — Backend

FastAPI + SQLite. Session 1 scaffold — all endpoints return 501 except `/health` and `/docs`.

## Run locally with Docker

```bash
cp backend/.env.example backend/.env
docker compose up --build backend
```

Then visit:

- http://localhost:8000/health → `{"status":"ok",...}`
- http://localhost:8000/docs → OpenAPI UI listing every endpoint

## Run locally without Docker

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows cmd
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Layout

```
backend/
  app/
    main.py              # FastAPI app + lifespan (init_db on startup)
    config.py            # Settings via pydantic-settings
    database.py          # SQLAlchemy engine + session + init_db()
    models.py            # campaigns, settlements, used_nonces
    schemas.py           # pydantic request/response models
    dependencies.py      # X-API-Key (publisher) + Privy JWT (advertiser) guards
    routers/
      health.py          # GET /health — implemented
      wallet.py          # /api/wallet, /api/faucet — Session 2
      campaigns.py       # /api/campaigns/* — Sessions 3 & 6
      bid.py             # POST /bid — Session 4
      proof.py           # POST /proof — Session 5
    services/
      privy.py           # Privy REST client — Session 2
      x402.py            # facilitator client — Session 3
      tokens.py          # proof_context JWT helpers — Sessions 4–5
  requirements.txt
  Dockerfile
  .env.example
```

## What works right now (Session 1)

- `GET /health` — live.
- `GET /docs` — every planned endpoint is visible with the right shapes.
- SQLite DB created on startup at `./data/adserver.db` (inside container) with three tables.
- Two auth guards wired but unverified — `X-API-Key` does a string match; Privy JWT currently accepts any non-empty bearer token (real JWKS verification lands in Session 2).

See `../PLAN.md` for the full session roadmap and what's next.
