# Design brief — Solboards dashboard

Paste this into Claude (or your design tool) to generate visual mockups for
the dashboard facelift. The current frontend is functional but utilitarian;
the goal is "polished modern dashboard" without changing the data model or
the demo loop. Once you have mockups you like, share them back and I'll
implement them in React + CSS.

---

## Project context

**Solboards** — DOOH ad platform on Solana devnet. Advertisers fund
campaigns in USDC via Coinbase's x402 payment protocol; publishers (digital
out-of-home screen networks) get paid per-play via on-chain settlements.

End-to-end loop: advertiser logs in (Privy embedded wallet) → uploads
creative → picks DMAs + dates → server computes budget (locked CPM × screens
× duration) → funds via x402 (signed USDC transfer to a fresh per-campaign
Privy server wallet) → 2.5% protocol fee auto-skimmed → publishers' devices
fetch ads via `/bid`, signal proof-of-play via `/proof` → ad server settles
each play on-chain (campaign wallet → publisher wallet) → leftover budget
refundable.

Stack: FastAPI + SQLite backend, React + Vite + TypeScript frontend, Privy
server wallets (no Anchor, no Rust), x402.org public facilitator, GCS for
creative hosting. Hackathon submission for Solana Colosseum, 19-day build.

Audience for this dashboard: advertisers + judges. Not the publisher side.

---

## Layout

- **Top header** (full width, ~64px tall): app name on the left, **Wallet
  chip** on the right.
- Below header: **two-tab nav** — Overview · Campaigns — with a "+ New
  campaign" button on the right of the tab row, opening a centered modal.
- Tab content: full-width container, max ~1200px, centered.

## Wallet chip (header, right side)

- **Collapsed**: pill labeled `Wallet · {balance} USDC ▾`. The "Wallet" word
  + chevron make clickability obvious. When balance < 1 USDC, the chip
  pulses or gets an accent border to draw attention to the faucet.
- **Click → dropdown panel** anchored to the chip (~320px wide):
  - Wallet address (truncated, copy button)
  - **Primary CTA**: `+ Get test USDC` button — prominent, accent color, larger than the rest
  - Solscan link (small, secondary)
  - "Create Solana wallet" fallback button (only shown when no Solana wallet exists on the Privy account)
- **States to design**:
  - Collapsed normal
  - Collapsed low-balance (with hint)
  - Expanded dropdown
  - Expanded with pending-faucet-tx state ("inbound +100 USDC, confirming…")
  - No-wallet fallback

## Overview tab

- **Top stat grid** — 4 cards in a row:
  - Active campaigns
  - Total spent (USDC)
  - Total plays
  - Last 24h plays

  Each card: big number, small label, optional sparkline-ish flourish.

- **Status breakdown row** — 5 small cards or chips:
  `Active N · Paused N · Completed N · Expired N · Expiring soon N`.
  "Expiring soon" = active campaigns with `end_date - today ≤ 3 days`.

- **Recent activity feed** (last 10 settlements across all campaigns): each
  row shows time-ago, campaign name, DMA, USDC amount, Solscan tx link.
  Empty state: "No plays yet — create a campaign to get started."

- **States**:
  - Empty (no campaigns at all → big CTA)
  - Normal (with stats)
  - Loading (skeleton)

## Campaigns tab

- List of **expandable campaign cards**. Card collapsed shows: name, status
  badge, progress bar (spent/budget), brief targeting summary ("New York ·
  3 days").
- Click to expand into:
  - Stats (plays, CPM, remaining budget, protocol fee, schedule, target DMAs, campaign-wallet Solscan link)
  - Action buttons appropriate to the status (Simulate play, Pause, Resume, Refund)
  - Recent settlements list (10 rows) with Solscan tx links
  - Last-play indicator with venue DMA when present
- **Status badges**: 6 visually distinct states (draft, active, paused,
  completed, expired, refunded). Active = green/glowing; expired = orange;
  refunded/completed = neutral.
- **Empty state**: "No campaigns yet — click + New campaign."

## Modal — Create campaign wizard

Centered, ~640px wide, dimmed backdrop. ESC + click-outside dismiss (with a
confirm prompt if mid-flow).

- **Header bar inside modal**: 5-step progress indicator (filled circle for
  current step, checkmarks for completed). Steps:
  `Creative · Targeting · Schedule · Budget · Review`.
- **Step 1 — Creative**: file picker, drag-and-drop area, validation
  message, image preview thumbnail, upload progress bar.
- **Step 2 — Targeting**: 6 DMA cards (NYC, LA, SF, Miami, Boston, Austin),
  each shows screen count. Click to select (multi). Live REACH counter at
  the bottom showing total selected screens. Hardcoded "Frequency: 1 every
  5 min" line.
- **Step 3 — Schedule**: two date pickers (start, end). Validation
  messages.
- **Step 4 — Budget** (calculator, server-derived): table of derived
  numbers (Screens × Days × Plays/day, Total, Protocol fee 2.5%, Total to
  escrow). Shows wallet balance. Disables Next + shows error if
  insufficient.
- **Step 5 — Review**: read-only summary of all prior steps + name input +
  big "Confirm & Fund" button. Stages during fund:
  `Creating wallet… → Sign in popup → Settling…` → success state with
  Solscan tx links (funding tx + protocol fee tx).
- **Back button** on every step except Step 1.
- **Success state** (after fund completes): green checkmark, "Campaign
  live" text, two Solscan links (funding + fee), "Done" button to close
  modal.

## Data shapes

(So the layouts are buildable from real API output.)

```ts
WalletInfo:        { wallet_address: string; usdc_balance: number }

CampaignSummary:   {
  id, name, status, budget, spent, remaining, wallet_address,
  target_dmas?: string[], start_date?, end_date?,
  protocol_fee_amount?, protocol_fee_tx_hash?
}

CampaignStats:     CampaignSummary + {
  total_plays, cpm_price,
  recent_settlements: SettlementSummary[]
}

SettlementSummary: {
  id, nonce, publisher_wallet, amount_usdc, tx_hash,
  solscan_url, status, created_at
}

Quote:             {
  screens, plays_per_screen_per_day, days, total_plays,
  cpm_price, total_usdc, protocol_fee_pct,
  protocol_fee_usdc, total_to_escrow_usdc
}

MarketInfo:        { dma: string, display_count: number }

Campaign statuses: "draft" | "active" | "paused" | "completed" | "refunded" | "expired"
```

## Aesthetic guardrails

- Dark theme. Existing palette is bg `#0d0d10`-ish, text `#f5f5f7`-ish,
  accent indigo/purple. Open to refining.
- Sharp typography (Inter / SF Pro / Geist).
- Generous whitespace, ~8px spacing scale.
- Mono for hashes, addresses, amounts.
- Avoid corporate-blue / stocky illustrations / emojis-as-UI.

## Deliverables expected

Mockups (HTML+CSS or React JSX in Claude artifacts) for:

- Header (collapsed + expanded chip states)
- Overview tab
- Campaigns tab (collapsed list + one card expanded)
- Modal wizard at each of the 5 steps
- Key empty states
- Success state after fund completes
