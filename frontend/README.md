# frontend — x402 Ad Server dashboard

Vite + React + TypeScript. Privy for auth + embedded wallet. React Query for
server state. Zustand for client state (no stores yet as of Session 8).

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
  main.tsx          React root, wraps app in PrivyProvider + QueryClientProvider
  App.tsx           auth gate — shows <Login> or <Home>
  lib/
    api.ts          axios instance + useApi() hook (injects Privy JWT)
    queryClient.ts  shared react-query client
  pages/
    Login.tsx       unauthenticated landing — single "sign in" button
    Home.tsx        authenticated landing — smoke-tests backend /health
  styles.css        dark theme, tiny design system
```
