# Session 8 — React dashboard scaffold ✅

**Date:** 2026-04-22

## Checklist

- [x] `frontend/` with Vite + React + TS (+ React Query + Zustand as deps)
- [x] Privy React SDK + provider config (Solana devnet cluster, email login, embedded wallet on login)
- [x] API client wrapper (`lib/api.ts` — public `api` singleton + `useApi()` hook that injects Privy JWT)
- [x] Dockerfile for dashboard, compose wiring (anonymous `node_modules` volume so host mount doesn't shadow image deps)
- [x] Basic layout: `<Login>` ↔ `<Home>`, gated by Privy `authenticated` state; Home smoke-tests backend `/health` via React Query
- [x] Backend CORS middleware (`cors_allow_origins` in settings, default `localhost:5173` + `127.0.0.1:5173`); exposes `X-PAYMENT-RESPONSE` for Session 9's x402 flow

**Verified in browser (2026-04-22):**

- `docker compose up -d` brings both services healthy (backend 8000, frontend 5173)
- CORS preflight from `http://localhost:5173` origin → 200 with matching allow-origin header
- Login flow: email OTP via Privy → Home renders with user email + live `/health` response
- Logout returns to Login; no console errors

**Late-cycle fix-ups (also landed in Session 8):** Privy + Solana in Vite needed the `vite-plugin-node-polyfills` plugin (for `Buffer`/`process`/`global`) plus the `@solana/kit` + `@solana-program/{memo,system,token}` peer-dep stack per Privy's Vite troubleshooting docs. Manual `globalThis.Buffer = Buffer` polyfill in main.tsx didn't work because ES-module hoisting runs Privy imports before the polyfill line. Also: rebuilding the frontend image without `--renew-anon-volumes` preserved the old `node_modules` and silently no-op'd dep updates — documented in frontend README for future dep bumps.

## Work log entry

- **2026-04-22 (Session 8):** React dashboard scaffold — Vite + React 18 + TS under `frontend/`, Privy React SDK (Solana-only embedded wallets via nested `embeddedWallets.solana.createOnLogin` per Privy Vite docs), vite-plugin-node-polyfills for Buffer/process/global, React Query wired, Zustand installed (no stores yet). Backend CORSMiddleware added, exposes `X-PAYMENT-RESPONSE`. Auth gate → Login ↔ Home. Verified in browser: email OTP → Home with live `/health` response. Branding corrected to "Advertiser Dashboard" with "demo — third-party advertiser view" subtitle.
