# x402 Ad Server — Project Spec

## What We're Building

An ad server for DOOH (Digital Out of Home) advertising with crypto-based settlement on Solana. Advertisers create campaigns and fund them with USDC. When publishers (display screens) show ads, payment flows automatically from the campaign wallet to the publisher's wallet.

This is a hackathon submission for Solana's Colosseum. The goal is a working demo with real on-chain transactions on devnet, not a production-ready system.

---

## Background — The DOOH Problem

### Three parties in the system

1. **Advertiser** — wants their creative shown on digital screens. Creates campaigns, sets budget, uploads creative, pays for impressions.
2. **Ad Server (us)** — the brain in the middle. Receives bid requests from publishers, matches them to funded campaigns, validates proof of play, triggers payment. Acts as the oracle/authority for payment decisions.
3. **Publisher** — operates physical DOOH display screens (billboards, retail screens, transit displays). Sends bid requests when a screen is available, plays the ad, reports back proof of play. Already built — we implement the API they call.

### Why crypto settlement for DOOH?

Traditional DOOH payment clearing takes 60-90 days through intermediaries (ad networks, clearing houses, invoicing). Crypto settlement on Solana reduces this to seconds. The pitch: "We replaced the entire DOOH payment clearing process with a 500ms settlement on Solana."

### The payment trust problem

- Publishers won't show ads unless they're confident payment exists (advertiser might not pay)
- Advertisers won't pay unless they have proof the ad actually played (publisher might fake it)
- The ad server sits in the middle and solves both: it verifies funds exist before matching, and verifies proof of play before releasing payment

### How payment flows — two legs

There are two distinct payment events:

**Leg 1: Advertiser → Ad Server (via x402)**

1. Advertiser's platform calls ad server API to create a campaign
2. Ad server returns HTTP 402 — "this campaign costs X USDC, pay up"
3. Advertiser's system pays via x402 payment header — full budget, prepaid
4. Facilitator verifies → USDC lands in the campaign's Privy server wallet
5. Campaign status moves to "active," eligible for bid matching

**Leg 2: Ad Server → Publisher (via Privy)**

1. Publisher sends bid request → ad server matches to funded campaign
2. Publisher plays ad → submits proof of play
3. Ad server validates proof → calls Privy to send USDC from campaign wallet to publisher wallet
4. Per-play settlement — each impression paid individually
5. CPM model: a $12.50 CPM means each play costs $0.0125 USDC ($12.50 ÷ 1000 impressions)

**Refund: Ad Server → Advertiser**
When campaign ends (expired or manually stopped) and budget is not fully spent, remaining USDC is refunded to the advertiser's wallet.

### The ad server is a business, not an escrow

The ad server receives payment, holds funds, disburses to publishers, and refunds the remainder. Like any ad network — except settlement is in USDC on Solana, advertiser payment uses x402, and publisher payment happens per-play in seconds instead of 60-90 day invoice cycles.

### What about the dashboard?

For the hackathon, we build a demo dashboard to make the loop clickable for judges. In production, there is no dashboard from us — advertisers have their own platforms and integrate via our API. The demo dashboard is just a prop.

---

## Decision Log — Why We Chose What We Chose

### Why Privy server wallets instead of Anchor/smart contracts?

We considered three approaches:

- **Option A: Raw Solana keypairs per campaign** — simplest but fully custodial, ad server holds all private keys, one breach = all funds lost. Rejected.
- **Option B: Anchor program with PDAs** — trustless on-chain escrow, Program Derived Addresses act as campaign wallets controlled by smart contract code. Best for production but requires Rust/Anchor expertise and 4-5 weeks. Too slow for 19-day hackathon.
- **Option C: Privy server wallets** — create a managed wallet per campaign via API, ad server controls them via Privy's API. Not trustless (Privy + our server control funds) but requires zero Rust, entire backend is Python. Saves 5-6 days. **Chosen for hackathon.**

Production roadmap would upgrade to Option B (Anchor PDAs) for trustless on-chain escrow.

### Why Solana?

- Hackathon is Solana Colosseum — required
- Sub-cent transaction fees make per-impression micropayments viable
- Fast finality (~400ms) fits the 2-second proof latency budget
- Privy has full Solana support including server wallets

### Why FastAPI (Python) + React instead of Next.js?

- Next.js is overkill — no SSR needed, the dashboard is a thin client
- Python team is stronger/faster
- Clean separation: API logic in Python, dumb UI in React
- Two deploys, two repos, no coupling

### Why per-play settlement instead of batching?

- For the demo, real-time balance drain is visually impressive (judges see money move)
- Solana devnet has no real gas costs so there's no reason to batch
- Production would batch when cost-per-play is very low (e.g., $0.002) to save on fees

### Why JWT for proof_context?

- Self-contained: everything needed for settlement is inside the token (campaign_id, wallet_id, nonce, amount)
- No DB lookup needed for validation — just verify signature
- Tamper-proof: if the publisher or anyone modifies it, signature verification fails
- The publisher treats it as opaque — they store it and echo it back, never decode it

### Why FIFO matching instead of real auction?

- The contract specifies first-price auction (`at: 1`) but for MVP, we're not running competitive bidding between multiple advertisers for the same impression
- FIFO (first funded campaign that fits gets the impression) is sufficient
- Real auction logic can be added later when there are multiple active campaigns competing

### Why Privy embedded wallets instead of Phantom/wallet connect?

We considered three approaches:

- **Phantom wallet connect** — classic Web3 UX, but judges need Phantom installed + devnet mode + devnet USDC preloaded. Too much friction for a demo.
- **Privy embedded wallet only** — email login creates a wallet automatically, zero friction. But the wallet starts empty — need a way to fund it.
- **Privy embedded wallet + treasury faucet** — email login, zero friction, plus a "Get test USDC" button that sends devnet USDC from a pre-funded treasury wallet. **Chosen.**

The treasury wallet is a Privy server wallet we pre-load with devnet USDC from Circle's faucet before the demo. One extra API endpoint (`POST /api/faucet`), maybe 30 minutes of work. Judges never leave the app.

In production there is no faucet — advertisers fund their own wallets through exchanges or existing USDC holdings. The embedded wallet approach still works: advertisers log into our API dashboard via email, get a wallet, and use it to pay for campaigns via x402.

---

## Edge Cases to Handle

### Fraud prevention

- **Double-play claims**: Publisher submits same proof twice. Mitigated by nonce tracking — each proof_context has a unique nonce, stored in used_nonces table. Duplicate nonce = reject.
- **Fake proof of play**: Publisher fabricates proof without playing ad. Mitigated by proof_context JWT signature — they can't forge a valid token. For production, would add hardware attestation.
- **Expired proofs**: proof_context should have a TTL. If proof comes in hours after the bid, reject it. Check `created_at` in the JWT against current time.

### Budget management

- **Budget exhaustion mid-flight**: Always check `budget - spent > cost_per_play` BEFORE returning a bid. If budget is too low, return no-bid.
- **Race condition on balance**: Two bid requests come in simultaneously for the same campaign with only enough budget for one. Use database-level locking or atomic decrement to prevent over-commitment.
- **Deposit confirmation**: Don't trust the frontend saying "I deposited." Always verify on-chain balance of the campaign wallet via Solana RPC before activating.

### Infrastructure failures

- **Privy API down**: Settlement fails. Log the pending settlement, return `{"status": "error"}` to the publisher. Implement a retry queue for failed settlements.
- **Solana RPC slow**: Transaction might take longer than 2 seconds. Consider async settlement — confirm the proof immediately, queue the payment, retry if it fails.
- **Database unavailable**: Nonce check fails. Err on the side of caution — if you can't verify a nonce isn't used, reject the proof.

---

## x402 Protocol — Used for Advertiser Payment

x402 is Coinbase's open payment protocol that uses HTTP 402 status codes for internet-native payments. We use it for the advertiser → ad server payment leg.

### How it works in our system:

1. Advertiser calls `POST /api/campaigns` with campaign details
2. Ad server responds with **HTTP 402 Payment Required** + payment requirements header (amount, USDC, Solana network, campaign wallet address)
3. Advertiser's system creates a payment payload (signs a USDC transfer) and resends the request with `X-PAYMENT` header
4. Ad server forwards the payment to the x402 facilitator for verification + settlement
5. Facilitator verifies signature, executes USDC transfer on Solana, returns tx hash
6. Payment confirmed → campaign goes active

### What is the facilitator?

The facilitator is a third-party server that verifies and settles x402 payments. It's the neutral party that actually moves the money on-chain. The advertiser doesn't send money to us directly — the facilitator validates the signed payment and executes the transfer. This is what makes x402 trustless.

### Facilitator options for Solana devnet (all confirmed working):

**x402.org testnet facilitator (recommended for hackathon)**

- Endpoint: `https://x402.org/facilitator`
- No API keys needed, no signup
- Works on Solana devnet out of the box

**CDP facilitator (Coinbase)**

- Endpoint: `https://api.cdp.coinbase.com/platform/v2/x402`
- Requires CDP API keys (free signup)
- 1,000 free transactions/month
- Solana devnet network ID: `solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1`

**PayAI facilitator**

- Endpoint: `https://facilitator.payai.network`
- No API keys needed
- Supports `solana-devnet`

### x402-solana npm package

There's a ready-made library specifically for x402 on Solana that works with Privy: `x402-solana`

**Client side (React dashboard — simulates advertiser):**

```typescript
import { createX402Client } from "x402-solana/client";
import { useSolanaWallets } from "@privy-io/react-auth/solana";

const client = createX402Client({
  wallet,
  network: "solana-devnet",
  maxPaymentAmount: BigInt(10_000_000), // max 10 USDC
});

// Automatically detects 402, signs payment, retries with X-PAYMENT header
const response = await client.fetch("/api/campaigns", {
  method: "POST",
  body: JSON.stringify(campaignData),
});
```

**Server side (FastAPI — our ad server):**
The x402-solana package has server-side helpers too, but they're in TypeScript/Express. Since our backend is FastAPI (Python), we need to implement the server-side x402 logic manually:

1. Return 402 + payment requirements header (JSON with amount, asset, network, payTo address)
2. On retry, extract `X-PAYMENT` header
3. Forward to facilitator's `/verify` endpoint for validation
4. Forward to facilitator's `/settle` endpoint for on-chain settlement
5. Confirm tx hash, activate campaign

This is straightforward HTTP — no special library needed on the Python side.

### Devnet USDC

Get devnet USDC from Circle's faucet: https://faucet.circle.com — select "Solana Devnet" and enter the wallet address. No need to mint your own tokens.

### Why x402 makes sense here:

In production, advertisers are external parties with their own platforms. They're not using our UI — they're calling our API. x402 is how they pay us programmatically over HTTP. No invoices, no wire transfers, no payment forms. The payment is part of the API call itself.

### Two payment legs, two mechanisms:

- **Advertiser → Ad Server:** x402 (HTTP-native payment, advertiser initiates, facilitator settles)
- **Ad Server → Publisher:** Privy server wallet transfer (we initiate after proof of play, no facilitator needed)

### For the hackathon demo:

The React dashboard simulates the advertiser's platform using the `x402-solana` client library + Privy embedded wallet. When the user clicks "Fund Campaign," the x402 client automatically handles the 402 handshake: detects the 402 response, signs the USDC transfer via Privy, resends with payment header. Judges see the full x402 protocol in action with real devnet transactions.

---

## Production Roadmap (post-hackathon)

1. **Anchor program with PDAs** — replace Privy server wallets with trustless on-chain escrow. Each campaign gets a PDA (Program Derived Address) controlled by the smart contract, not by any private key. Refunds enforced by code, not by us.
2. **x402 `upto` scheme** — when available, replace prepay+refund with authorization-based spending. Funds stay in advertiser's wallet, we draw per-play. No refund needed.
3. **Multisig oracle** — replace single ad-server signer with 2-of-3 multisig (ad server + independent verifier + arbitrator).
4. **Batch settlement** — accrue micropayments and batch-settle when threshold reached.
5. **Hardware attestation** — TPM-signed proofs from display devices for tamper-proof proof of play.
6. **Dispute resolution** — on-chain dispute window where either party can challenge settlements.
7. **Formal security audit** — professional audit of Solana program before mainnet ($30-80K).

---

## Architecture

Two separate projects, one GCP deployment:

### 1. FastAPI Ad Server (Python)

- **Deploy:** Google Cloud Run
- **Database:** Cloud SQL (Postgres) or Firestore
- **Secrets:** GCP Secret Manager
- **Two audiences, two auth methods:**
  - Publisher → `X-API-Key` header
  - Dashboard (advertiser) → Privy JWT in `Authorization: Bearer` header

### 2. React Dashboard (Vite)

- **Deploy:** Cloud Storage + Cloud CDN (or second Cloud Run)
- **Auth:** Privy embedded wallets (email/social login → auto Solana wallet)
- **Role:** Thin client, no backend logic. Calls FastAPI `/api/*` routes.

## Wallet Infrastructure — Privy

- **No Anchor program. No Rust. No smart contracts.**
- Privy server wallets replace on-chain escrow for the hackathon MVP.
- One Privy server wallet created per campaign (holds campaign USDC budget received via x402).
- **Advertiser wallet:** Privy embedded wallet via email/social login. No Phantom, no browser extensions. Wallet is created automatically on signup.
- **Treasury wallet:** A pre-funded Privy server wallet controlled by us, loaded with devnet USDC from Circle's faucet before the demo. Used to fund advertiser embedded wallets via a "Get test USDC" button.
- Publisher wallet comes from the publisher's bid request (`imp.ext.wallet_id`).
- Publisher settlement: FastAPI calls `privy.walletApi.solana.signAndSendTransaction()` to move USDC from campaign wallet → publisher wallet.
- Refunds: FastAPI calls Privy to send remaining USDC from campaign wallet → advertiser's embedded wallet.
- Network: **Solana devnet** for hackathon. All SOL is free (airdrop via `solana airdrop` or faucet.solana.com). Devnet USDC is free from Circle's faucet: https://faucet.circle.com (select "Solana Devnet").

### Wallet map

```
Treasury wallet (Privy server wallet, pre-funded with devnet USDC)
  ↓ "Get test USDC" button
Advertiser embedded wallet (Privy, created on email login)
  ↓ x402 payment (POST /api/campaigns)
Campaign wallet (Privy server wallet, one per campaign)
  ↓ proof of play settlement
Publisher wallet (address from the publisher's bid request)
```

### Demo flow for judges

1. Judge opens app → logs in with email → Privy creates Solana wallet (invisible to user)
2. Clicks "Get test USDC" → treasury sends 100 devnet USDC to their wallet
3. Creates campaign → clicks "Fund" → x402 handshake → USDC moves from their wallet to campaign wallet
4. Clicks "Simulate ad play" → proof of play fires → USDC moves from campaign wallet to publisher
5. Dashboard shows balance draining in real time with Solscan tx links
6. Clicks "Refund" → remaining USDC returns to their wallet
   All in-browser, no extensions, no Phantom, zero friction.

## Publisher Contract (OpenRTB-Lite)

The publisher side is DONE. The publisher sends bid requests and proof-of-play. We implement two endpoints:

### POST /bid — Publisher calls when a screen needs an ad

**Publisher sends:**

```json
{
  "id": "pub-<uuid>",
  "imp": [
    {
      "id": "1",
      "video": {
        "mimes": ["video/mp4", "image/jpeg", "image/png"],
        "minduration": 1,
        "maxduration": 30,
        "w": 1920,
        "h": 1080,
        "protocols": [2]
      },
      "displaymanager": "dooh-pub",
      "displaymanagerver": "1.0",
      "ext": { "wallet_id": "publisher_solana_address" }
    }
  ],
  "device": {
    "devicetype": 8,
    "w": 1920,
    "h": 1080,
    "geo": { "lat": 40.7128, "lon": -74.006 },
    "ext": { "screen_size_inches": 55 }
  },
  "site": {
    "id": "venue-001",
    "name": "Times Square Digital Board",
    "cat": ["IAB22"],
    "ext": { "venue_type": "retail" }
  },
  "at": 1,
  "cur": ["USD"]
}
```

**We respond (HTTP 200):**

```json
{
  "id": "pub-<uuid>",
  "seatbid": [
    {
      "bid": [
        {
          "id": "bid-<unique>",
          "impid": "1",
          "price": 12.5,
          "adm": "https://cdn.example/creatives/abc123.mp4",
          "crid": "creative-abc123",
          "w": 1920,
          "h": 1080,
          "ext": {
            "duration": 15,
            "mime_type": "video/mp4",
            "proof_context": "<signed_jwt>"
          }
        }
      ],
      "seat": "advertiser-seat-001"
    }
  ],
  "cur": "USD"
}
```

**No-bid:** return `{"id": "...", "seatbid": [], "cur": "USD"}` (HTTP 200) or HTTP 204.

**Latency target:** <500ms. No on-chain calls in this path.

### POST /proof — Publisher calls after ad played

**Publisher sends:**

```json
{
  "proof_context": "<the_jwt_we_sent_in_bid_response>",
  "start_time": 1744300800,
  "duration": 15
}
```

**Our logic:**

1. Decode + verify `proof_context` JWT signature
2. Extract: campaign_id, wallet_id, nonce, amount_usdc
3. Validate: nonce not used, timestamp within window, duration meets minimum
4. Trigger Privy `signAndSendTransaction()` → USDC from campaign wallet to publisher wallet_id
5. Update DB: mark nonce used, decrement campaign balance, log tx hash
6. Return `{"status": "confirmed"}` (HTTP 200)

**Latency budget:** 2 seconds (enough for Privy API call + Solana tx).

### proof_context Token Design

Signed JWT containing everything needed for settlement:

```python
proof_context = jwt.encode({
    "campaign_id": "camp_abc",
    "bid_id": "bid-xyz-789",
    "wallet_id": "publisher_solana_address",
    "nonce": "unique_random_string",
    "created_at": 1744300785,
    "amount_usdc": 0.0125  # CPM $12.50 ÷ 1000
}, SERVER_SECRET, algorithm="HS256")
```

No DB lookup needed for validation — decode, verify sig, check nonce, pay.

## Advertiser API Endpoints

These are the endpoints advertisers call from their own platforms. For the hackathon demo, our React dashboard calls these same endpoints. In production, there is no dashboard from us — advertisers integrate directly.

### POST /api/faucet (demo only)

Send devnet USDC from the treasury wallet to the authenticated advertiser's embedded wallet.

- Treasury wallet is a Privy server wallet pre-loaded with devnet USDC before the demo
- Sends a fixed amount (e.g., 100 USDC) per request
- Only exists on devnet — would not exist in production
- Returns: amount sent, tx_hash

### GET /api/wallet

Get the authenticated advertiser's wallet info.
Returns: wallet_address, usdc_balance (read from Solana RPC).
Dashboard uses this to show the user's balance and enable/disable the "Fund Campaign" button.

### POST /api/campaigns/quote (Session 15)

Calculator endpoint. Wizard's Step 4 hits this; the same `compute_quote`
runs server-side on POST `/api/campaigns` so the dashboard preview always
matches what gets charged.

- Body: `{target_dmas, start_date, end_date}`
- Returns: `{screens, plays_per_screen_per_day, days, total_plays, cpm_price, total_usdc, protocol_fee_pct, protocol_fee_usdc, total_to_escrow_usdc}`

Screen counts come from the server-side venues index, CPM from `DEMO_CPM`,
fee from `PROTOCOL_FEE_PCT`. Clients don't supply these — single source of
truth on the server.

### POST /api/campaigns (x402 payment flow)

Create and fund a campaign. This is the x402 integration point.

1. Advertiser sends `{name, creative_url, creative_id, target_dmas, start_date, end_date}` only — no budget, CPM, or duration in the body (server-derived from `DEMO_CPM` + the calculator + the venues index).
2. Ad server runs `compute_quote` to derive `total_to_escrow = total + 2.5% fee`, creates campaign record (status: "draft") + creates Privy server wallet.
3. Ad server returns **HTTP 402** with payment requirements (amount = `total_to_escrow_usdc`, USDC, Solana, campaign wallet address).
4. Advertiser's system pays via x402 — sends USDC to the campaign wallet, retries request with X-PAYMENT header.
5. Ad server verifies + settles via facilitator.
6. Campaign wallet now holds `budget + fee`. Server fires a Privy USDC tx campaign-wallet → `PROTOCOL_REVENUE_WALLET_ADDRESS` for the fee (best-effort; failure leaves the fee in the campaign wallet but doesn't block activation).
7. Campaign status → "active".
8. Returns: campaign summary including `protocol_fee_amount` + `protocol_fee_tx_hash`.

### GET /api/markets (Session 14)

Per-DMA display counts derived from the venues index. Drives the wizard's
targeting cards.
Returns: `[{dma, display_count}, ...]` for the canonical DMA labels.

### GET /api/campaigns

List all campaigns for the authenticated advertiser.
Returns: array of campaigns with id, name, status, budget, spent, remaining balance.

### GET /api/campaigns/:id

Full campaign detail.
Returns: status, budget, spent, remaining_balance, play_count, created_at, wallet_address.

### GET /api/campaigns/:id/stats

Campaign performance stats.
Returns: total_plays, total_spent, remaining_budget, avg_cpm_effective, list of recent settlements with tx_hashes and Solscan links.

### GET /api/campaigns/:id/settlements

Settlement history for the campaign.
Returns: array of {nonce, publisher_wallet, amount_usdc, tx_hash, timestamp, status}.

### POST /api/campaigns/:id/pause

Pause a campaign — stops it from being matched to bid requests.
Updates status: "active" → "paused".

### POST /api/campaigns/:id/resume

Resume a paused campaign.
Updates status: "paused" → "active" (only if balance > 0).

### POST /api/campaigns/:id/refund

Refund unspent budget to advertiser's embedded wallet.

1. Verify campaign is paused or completed (no active matching)
2. Calculate remaining: budget - spent
3. Privy `signAndSendTransaction()` → send remaining USDC from campaign wallet back to advertiser's embedded wallet address
4. Update campaign status → "refunded", record refund tx hash
5. Returns: refund_amount, tx_hash

## Auth

### Publisher auth

- `X-API-Key` header on `/bid` and `/proof`
- Checked via simple middleware

### Advertiser auth

- Privy JWT in `Authorization: Bearer <token>` header on `/api/*` routes
- Verify against Privy's JWKS public keys
- Extract user_id and wallet address from token claims
- For hackathon demo: our React dashboard uses Privy embedded wallets to get this JWT
- For production: advertiser's own platform authenticates via Privy or API key

## Database Schema (minimal)

### campaigns

- id (uuid, PK)
- advertiser_id (string — from Privy user ID)
- advertiser_wallet (string — Solana address to refund unspent budget to)
- name (string)
- creative_url (string — public GCS URL set by `/api/creatives` upload, Session 13)
- creative_id (string — stable crid for publisher caching)
- cpm_price (decimal — USD; server-set from `DEMO_CPM`, Session 15)
- budget (decimal — playable amount = `total_usdc` from the calculator; excludes protocol fee)
- spent (decimal — USDC paid out to publishers so far)
- status (enum: draft, active, paused, completed, refunded, **expired** — Session 14)
- wallet_id (string — Privy server wallet ID for this campaign)
- wallet_address (string — Solana address of campaign wallet)
- duration (integer — creative playback seconds; default 15, no longer user-supplied as of Session 15)
- refund_tx_hash (string, nullable)
- target_dmas (JSON list of canonical DMA labels — Session 14, mandatory at create time)
- start_date (date — UTC, inclusive — Session 14)
- end_date (date — UTC, inclusive; campaigns auto-flip to `expired` when today > end_date — Session 14)
- protocol_fee_amount (decimal, nullable — 2.5% of total, transferred to PROTOCOL_REVENUE_WALLET on activation — Session 15)
- protocol_fee_tx_hash (string, nullable — Solscan-linked from the dashboard — Session 15)
- created_at (timestamp)

### settlements

- id (uuid, PK)
- campaign_id (FK → campaigns)
- nonce (string, unique — from proof_context)
- publisher_wallet (string — Solana address from the publisher's bid request)
- amount_usdc (decimal)
- tx_hash (string — Solana transaction signature)
- status (enum: confirmed, failed)
- created_at (timestamp)

### used_nonces

- nonce (string, PK) — fast lookup to prevent double-pay

## Campaign Lifecycle

1. **Draft** — advertiser called POST /api/campaigns, campaign record created, Privy wallet created, awaiting payment
2. **Active** — x402 payment confirmed, protocol fee transferred, campaign eligible for bid matching
3. **Paused** — advertiser paused the campaign, not matched to bid requests, can resume or refund
4. **Completed** — budget fully spent (`budget - spent < cpm_price/1000`)
5. **Refunded** — campaign ended with unspent budget, remainder sent back to advertiser wallet
6. **Expired** (Session 14) — `end_date` passed before budget drained; lazy-flipped on the next `/bid` pass; refund button still applies

## Matching Logic (FIFO)

When the publisher sends a bid request (must include `imp[0].ext.device_id`):

1. Resolve `device_id` to a DMA via the venues index. Unknown device → no-bid.
2. Query active campaigns ordered by `created_at` ASC.
3. While iterating, lazy-flip any campaign whose `end_date` is in the past to `EXPIRED`.
4. Pick the first campaign where:
   - DMA membership: `dma ∈ target_dmas`
   - Schedule window: `start_date ≤ today ≤ end_date`
   - Remaining budget: `budget - spent ≥ cpm_price / 1000`
5. No real auction — first-price, first-come-first-serve.
6. If no campaign matches, return empty seatbid (200 with `seatbid: []`).

## Key Decisions (summary — see Decision Log above for full rationale)

- **Solana devnet** for hackathon — $0 real cost
- **Privy server wallets** — no Anchor/Rust, no smart contracts, all Python. Chosen over raw keypairs (security risk) and Anchor PDAs (too slow to build in 19 days).
- **x402 for advertiser payment** — advertiser pays full campaign budget via x402 (HTTP 402 handshake + facilitator settlement). Using x402.org testnet facilitator (no API keys needed). React dashboard uses `x402-solana/client` with Privy to handle the 402 flow automatically.
- **Prepay + refund model** — advertiser pays full budget upfront via x402. Unspent budget is refunded when campaign ends.
- **Per-play publisher settlement** for demo (not batched) — visually impressive, balance ticks down in real time
- **proof_context as JWT** — self-contained, no DB lookup for validation, tamper-proof
- **FIFO matching** — not a real auction, first funded campaign wins. Good enough for MVP.
- **CPM pricing in USD, settlement in USDC** — 1:1 peg assumed for hackathon
- **FastAPI + React** — separate repos, clean split. Python backend, thin React frontend.
- **GCP deployment** — Cloud Run for API, Cloud Storage + CDN for dashboard, Cloud SQL for DB

## Hackathon Deadline

**19 days** to Solana Colosseum submission.

## Stack Summary

| Component        | Tech                                             | Deploy                       |
| ---------------- | ------------------------------------------------ | ---------------------------- |
| Ad Server API    | Python, FastAPI, Privy SDK, solana-py            | Cloud Run                    |
| Dashboard UI     | React, Vite, Privy React SDK, x402-solana/client | Cloud Storage + CDN          |
| x402 Facilitator | x402.org testnet facilitator (hosted, no setup)  | https://x402.org/facilitator |
| Database         | Postgres (Cloud SQL) or SQLite                   | Cloud SQL                    |
| Wallet infra     | Privy server + embedded wallets                  | Privy cloud                  |
| Blockchain       | Solana devnet, USDC (SPL token)                  | —                            |
| Devnet USDC      | Circle faucet                                    | https://faucet.circle.com    |
| Secrets          | GCP Secret Manager                               | —                            |

## What We're NOT Building (deferred post-hackathon)

- Anchor/Solana program (on-chain escrow with PDAs)
- Dispute resolution system
- Multisig oracle
- Hardware attestation for proof of play
- x402 `upto` scheme (authorization-based spending without prepay)
- Batch settlement (per-play is fine for demo)
- Real auction logic (FIFO is enough)
- Publisher SDK (already exists)
- Formal security audit
- Advertiser self-service platform (we build a demo dashboard; real advertisers bring their own)
