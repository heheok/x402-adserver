# frontend — Solboards dashboard

Vite + React + TypeScript. Privy for auth + embedded wallet. React Query for
server state. Zustand for the small `walletTrack` store that drives post-tx
balance polling.

**For the hackathon, this is a demo prop, not a product we ship.** See
`BUSINESS-CONSTRAINTS.md §5` for the production UX model.

## Run (Docker)

From the repo root:

```bash
cp frontend/.env.example frontend/.env
# fill in VITE_PRIVY_APP_ID

docker compose up -d frontend
# → http://localhost:5173
```

## Run (local Node)

```bash
cd frontend
npm install
cp .env.example .env         # then fill in VITE_PRIVY_APP_ID
npm run dev
```

## When you add/remove a dependency

The compose file uses an anonymous volume to keep the container's
`node_modules` from being shadowed by the host mount. That means a plain
`docker compose up -d` after editing `package.json` will keep using the old
deps. You need:

```bash
docker compose build frontend
docker compose up -d --force-recreate --renew-anon-volumes frontend
```

`--renew-anon-volumes` is the key — without it, the anon volume persists
across rebuilds and the new deps never make it into the container.

## Structure

```
src/
  main.tsx                       React root, PrivyProvider + QueryClientProvider
  App.tsx                        auth gate — <Login> or <Home>
  lib/
    api.ts                       axios instance + useApi() hook (Privy JWT)
    queryClient.ts               shared react-query client
    walletTrack.ts               Zustand store, drives post-tx balance polling
    format.ts                    address truncation + Solscan URL helpers
    errors.ts                    humanizeError() — unwraps FastAPI {detail}
  pages/
    Login.tsx                    unauthenticated landing
    Home.tsx                     authenticated dashboard
  components/
    WalletPanel.tsx              advertiser wallet + faucet button
    CampaignsPanel.tsx           list + new-campaign trigger
    CampaignCard.tsx             one campaign — expandable detail + actions
    CreateCampaignForm.tsx       wizard shell — STEPS array + step state
    wizard/
      StepImage.tsx              Step 1: upload (1920×1080, GCS via /api/creatives)
      StepTargeting.tsx          Step 2: DMA cards, live REACH
      StepSchedule.tsx           Step 3: native date pickers
      StepCalculator.tsx         Step 4: server-derived budget via /quote
      StepReview.tsx             Step 5: confirm + x402 fund flow
  styles.css                     dark theme, tiny design system
```
