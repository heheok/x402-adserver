# Solboards — Backend

FastAPI + SQLite. Full demo loop: campaign create → x402 fund → bid →
proof-of-play → settle → refund. See `../PLAN.md` for the session-by-session
roadmap and `../RUNBOOK.md` for every ops procedure.

## Run locally with Docker

```bash
cp backend/.env.example backend/.env
# fill in PRIVY_APP_ID + PRIVY_APP_SECRET, run scripts/bootstrap_treasury.py
# and scripts/bootstrap_protocol_revenue.py once each, paste outputs back
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
    main.py              # FastAPI app + lifespan (init_db + auto_play loop)
    config.py            # Settings via pydantic-settings
    database.py          # SQLAlchemy engine + init_db + dev SQLite ALTER shim
    models.py            # campaigns, settlements, used_nonces
    schemas.py           # pydantic request/response models
    dependencies.py      # X-API-Key (publisher) + Privy JWT (advertiser) guards
    routers/
      health.py          # GET /health, GET /api/auto-play-status
      wallet.py          # /api/wallet, /api/faucet
      campaigns.py       # /api/campaigns/* (incl. /quote, /simulate-play)
      creatives.py       # POST /api/creatives (GCS upload)
      markets.py         # GET /api/markets (DMA inventory)
      bid.py             # POST /bid
      proof.py           # POST /proof
    services/
      privy.py           # Privy REST client (signAndSendTransaction)
      x402.py            # facilitator client (verify, settle, fee_payer)
      solana.py          # USDC transfer + SOL seed + ATA create helpers
      tokens.py          # proof_context JWT helpers
      venues.py          # publisher inventory index (DMA targeting)
      calc.py            # campaign budget calculator (compute_quote)
      gcs.py             # creative bucket upload
      auto_play.py       # demo-only background settlement loop
      retry.py           # failed-settlement retry helper
  data/                  # gitignored — venues.json + adserver.db live here
  scripts/               # bootstrap_*.py, sweep_helpers.py, e2e_demo.py, etc.
  requirements.txt
  Dockerfile
  .env.example
```

See `../PLAN.md` for the full session roadmap and `../RUNBOOK.md` for ops procedures.
