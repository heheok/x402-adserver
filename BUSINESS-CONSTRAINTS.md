# Business Constraints & Requirements

Business-facing reference for constraints, unit economics, and open decisions
that affect commercial/product conversations. Kept intentionally separate
from engineering docs so it can be read without code context.

Pairs with `BACKGROUND-INFORMATION.md` (product spec + architectural rationale)
and `PLAN.md` (engineering roadmap + open decisions). When figures here disagree
with those, treat `PLAN.md` as truth and flag the drift.

Last reviewed: 2026-04-24.

---

## 1. What the system is

A programmatic ad server for Digital Out of Home (DOOH) advertising with
per-impression on-chain settlement on Solana.

Three parties: **advertisers** (fund campaigns in USDC), **publishers** (DOOH
screen operators, already integrated via OpenRTB-lite), and **us** (the ad
server — matches bids, validates proof-of-play, settles payments).

Pitch: replaces the 60–90 day DOOH payment clearing cycle with sub-second
on-chain settlement. See `BACKGROUND-INFORMATION.md §Background` for full
narrative.

---

## 2. Unit economics (mainnet-equivalent)

Figures assume SOL at ~$200 and a CPM-pricing model. The hackathon runs on
Solana devnet where on-chain cost is $0.

| Cost line                             | Per event           | Who pays today   | Notes |
|---------------------------------------|---------------------|------------------|-------|
| New-campaign wallet setup             | ~0.002 SOL (~$0.40) | **Treasury (us)**| ATA rent. One-time per campaign. Recoverable only if the wallet is closed — Privy does not support wallet deletion, so in practice this is permanent cost. |
| Campaign wallet SOL seed for gas      | ~0.008 SOL (~$1.60) | **Treasury (us)**| Stranded in the campaign wallet after refund. Sized at ~2,000 txs worth of fees to cover an entire campaign's lifetime. |
| Per-play settlement fee               | ~5,000 lamports (~$0.001) | **Treasury (us)** | Deducted from the campaign wallet's SOL balance; covered by the seed above. |
| Refund fee                            | ~5,000 lamports (~$0.001) | **Treasury (us)** | Same pool. |
| Per-play USDC payout to publisher     | `CPM / 1000`        | **Advertiser**   | E.g. a $12.50 CPM → $0.0125 per play. This is revenue flowing through, not a cost. |
| x402 facilitator fee                  | $0 on `x402.org`    | —                | Free today on the hackathon facilitator. CDP facilitator has a free tier of 1,000 tx/month, then their pricing. |
| Protocol fee (revenue, upfront)       | 2.5% of campaign total | **Advertiser** | Charged upfront — `total to escrow = budget + fee`. After x402 settle pulls `budget+fee` into the campaign wallet, an immediate Privy transfer moves the 2.5% from the campaign wallet to a dedicated `PROTOCOL_REVENUE_WALLET` (separate from treasury). Non-refundable — refund only returns `budget - spent`, fee is gone. New `Campaign.protocol_fee_amount` column tracks it. Decided 2026-04-24, see §6. |

**Bottom line per campaign:** ~$2 of fixed overhead + ~$0.001 per play
absorbed by us; advertiser pays campaign budget + 2.5% protocol fee on top.
On devnet this is free, on mainnet the protocol fee is our revenue.

**Abandoned-draft cost:** every campaign that hits `draft` and is never funded
still cost us ~$0.40 of ATA rent. Something to monitor for fraud / spam / real
user abandonment rates.

---

## 3. Upstream-imposed limits

Things we can't negotiate because they live in vendor policy.

### Circle (devnet USDC faucet)
- **20 USDC per 2 hours per address**. Only relevant on devnet — our treasury
  tops up from this, advertisers never see it. Means our treasury can serve
  at most 200 advertisers per 2h window at the current 0.1 USDC demo faucet
  amount. Hackathon-only concern; goes away on mainnet (advertisers bring
  their own USDC).
- **Programmatic `/v1/faucet/drips` is gated (verified 2026-04-24).** Sandbox
  API keys cannot call the drips endpoint — `POST api.circle.com/v1/faucet/drips`
  with a `TEST_API_KEY:...` bearer returns `403 {"code":3,"message":"Forbidden"}`.
  The docs line *"Calling the /v1/faucet/drips API requires upgrading to
  mainnet"* maps to a real account-level KYC/business-verification gate. We
  have not pursued the upgrade for the hackathon. **Workaround in use:** N
  helper Privy server wallets bootstrapped alongside treasury, each
  individually claims 20 USDC every 2h via the public web faucet at
  `faucet.circle.com` (manual, captcha-gated — cannot be safely automated),
  then `scripts/sweep_helpers.py` consolidates to treasury. With 3 helpers +
  once-daily clicks the treasury earns ~60 USDC/day; with twice-daily ~120
  USDC/day. Mainnet has no equivalent — this entire problem disappears once
  advertisers bring their own USDC. Tracked as Session 12.

### Privy
- **No wallet deletion.** Every campaign wallet we create lives forever. ATA
  rent and any stranded SOL cannot be reclaimed. Operationally: the Privy
  dashboard will accumulate clutter; economically: this caps the value of
  ever "cleaning up" old campaigns.
- **Plan-gated features** that we are still evaluating for mainnet:
  - Fee sponsorship via `sponsor: true` — would eliminate the SOL seed and
    stranded-dust cost above. See §6.
- **Privy availability impact, by environment:**
  - *Hackathon demo:* our React dashboard uses Privy embedded wallets and
    Privy-issued JWTs. Privy down = judges can't log in or use the demo.
  - *Production:* advertiser auth is API-key-based (§5) — Privy down does
    **not** affect advertiser API access. Privy is still load-bearing for
    (a) campaign wallet creation via `/api/campaigns`, and (b) every
    settlement and refund (Privy signs the Solana tx). So a Privy outage
    stalls all new campaigns and all per-play settlements, but does not
    lock advertisers out of the API surface itself.
- **No SLA commitments from Privy.** Availability is their problem; we have
  no contractual guarantees.
- **`reference_id` is NOT strict pre-broadcast idempotency (verified
  2026-04-22, re-confirmed in production 2026-04-29).** Passing the same
  `reference_id` twice does not prevent the second tx from being broadcast
  on chain — Privy broadcasts, *then* rejects the duplicate at record time
  with `invalid_data` "reference_id already exists". Implication: retrying
  a failed `signAndSendTransaction` with the same `reference_id` can produce
  a **real duplicate on-chain transfer**, not a safe idempotent replay.
  Our current retry loop in `services/privy.sign_and_send_solana` is narrow
  enough (only retries on `transaction_broadcast_failure`, which means
  Privy explicitly told us the broadcast did not happen) that it should be
  safe, but this assumption must be re-verified before mainnet — see §7.

  **2026-04-29 production confirmation.** Session 16.8's `batch_settler`
  initially used a deterministic `reference_id = f"batch-{campaign[:8]}-{first_nonce[:8]}"`
  for restart-safety. Auto-play nonces are `f"auto-{32 hex}"`, so
  `first_nonce[:8]` = `"auto-"` + 3 hex chars = only 4096 unique values.
  After ~64 batches per campaign, birthday collisions made same-prefix
  ref_ids near-certain. Privy returned 400 `"already exists"` on collisions,
  but **the colliding tx had already broadcast and paid the publisher** —
  exactly as §3 predicts. Our compensation path then marked rows FAILED
  and decremented `spent`, creating publisher-MORE / campaign-DRIFT in
  the same shape as Session 16.6's RPC-blindness bug. Lesson: the §3
  rule "use unique suffixes per call" applies to ALL Privy ref_ids, not
  just retries. Fix shipped in Session 16.8 uses the full nonce, plus
  treats 5xx + "already exists" 400 as post-broadcast-uncertain (leave
  pending instead of compensating).

### x402 protocol — facilitator
- We use `https://x402.org/facilitator` (free, no API keys) for the advertiser
  payment leg. It is a third-party service we do not control. If it goes
  down, new campaigns cannot be funded (`POST /api/campaigns` fails).
  Settled campaigns continue to serve and settle normally because facilitator
  is not in the per-play path.
- Alternative: Coinbase Developer Platform (CDP) facilitator. Requires API
  keys, 1k free tx/month, then paid.

---

## 4. Protocol constraint: x402 `exact` vs `upto` on Solana

The x402 protocol has two payment schemes:

- **`exact`** — advertiser prepays the full campaign budget upfront into a
  dedicated campaign wallet; unspent budget is refunded. **This is what we
  use today.**
- **`upto`** — advertiser signs an authorization that caps total spend and
  expiry; the facilitator draws per-play directly from the advertiser's
  wallet. No prepay, no separate campaign wallet, no refund.

**Current status (verified 2026-04-21):** `upto` is not available on Solana.
Coinbase's reference implementation and the public `@x402/svm` package only
support `exact` on Solana. Engineering verified by direct file listing — no
`scheme_upto_svm.md` spec and no SVM `upto` implementation exists in the
Coinbase repo.

**What unlocks when `upto` ships on Solana** (no ETA):
- Entire SOL-subsidy category (§2) goes away — no campaign wallets, no ATA
  rent, no gas seed.
- Refund endpoint goes away — expiry replaces it.
- Advertiser-funding UX gets better — one signature, no prepay lockup.
- Engineering estimate: 2–3 sessions to migrate; ~75% of the codebase is
  untouched.
- Re-check trigger: `github.com/coinbase/x402/tree/main/specs/schemes/upto/`
  for a `scheme_upto_svm.md` file. See `PLAN.md §Protocol notes` for the
  detailed migration sketch.

**What to communicate externally:** our prepay-and-refund model is a temporary
constraint of the protocol on Solana, not a product choice. Expect it to
become authorization-based within 6–12 months of Solana support shipping.

---

## 5. UX constraints advertisers will feel

### Demo vs production — what we build, what the advertiser brings

The hackathon dashboard is a **demo prop**, not a product we ship. In
production the advertiser is a third-party ad-tech platform (a DSP, an
agency's programmatic tool, a brand's in-house campaign manager) that
integrates our API from their own stack. We do not build, operate, or
support an advertiser-facing UI in production.

| Piece                  | Hackathon demo                                                  | Production                                                                              |
|------------------------|-----------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| Advertiser UI          | Our React dashboard (a prop)                                    | **Advertiser's own platform.** Not our concern.                                         |
| Advertiser auth        | Privy JWT (email login → JWKS-verified bearer)                  | **API key in `X-API-Key` header.** Issued, rotated, and revoked by us. See §7 blocker.  |
| Advertiser wallet      | Privy embedded wallet (we create on signup)                     | **Advertiser brings their own.** Privy, custodial, Phantom, hardware — we don't care.  |
| Funding advertiser USDC| "Get test USDC" button → treasury faucet (`POST /api/faucet`)   | **Advertiser tops up themselves** via exchange, treasury, whatever. `/api/faucet` does not exist in production. |
| Campaign wallet        | Privy server wallet we create                                   | Same — Privy server wallet we create. Unchanged.                                        |
| SOL for gas            | Treasury seeds campaign wallet (§2)                             | Same — treasury seeds campaign wallet (pending §6 decision). Unchanged.                 |
| x402 payment signing   | Our dashboard signs via Privy React SDK + `x402-solana/client`  | **Advertiser's platform signs** with whatever wallet stack they have. Our API just expects a valid x402 payload. |
| Refund destination     | Their embedded wallet address (we know it — we made it)         | **Address the advertiser registered with us at onboarding or campaign creation.**       |

### Other UX rules that apply in both environments

- **No SOL in the advertiser flow.** Neither the advertiser's wallet nor the
  campaign wallet needs SOL from the advertiser's perspective — we handle
  gas (see §2 and §6). This is a deliberate product choice; pushing SOL onto
  the advertiser's flow is the biggest UX landmine on Solana for Web2 users.
- **Campaign lifecycle is linear:** draft → funded → active → (paused) → (completed) →
  (refunded). Refund requires pause first. Once refunded, a campaign is
  immutable.
- **No refund before pause.** Advertisers who want to reclaim unspent budget
  must pause the campaign first. Enforced by the API.

### Refund-address trust

In production, the refund destination is an address the advertiser gave us —
either at onboarding or at campaign creation. We can verify it's a
syntactically-valid Solana address; we **cannot** verify the advertiser owns
it. If they give us the wrong address (typo, swap, or malicious insider
swapping the advertiser's registered address), refunds go to that address
and on-chain finality makes them irrevocable.

Mitigations worth considering before mainnet: (a) require a signed
challenge from the refund address at registration to prove ownership,
(b) lock the refund address per-campaign at creation time so it can't be
swapped between funding and refund, (c) add a dispute/challenge window
before refund execution. None are built today.

### Endpoints that only exist in the demo

- `POST /api/faucet` — treasury faucet. Demo only. Never ships to production.
- The entire React dashboard. Demo only. Never ships to production.

Everything else in the API (`/bid`, `/proof`, `/api/campaigns*`, `/api/wallet`)
is the production surface.

### Creative hosting (added 2026-04-24)

In the demo, advertisers upload a campaign image via the wizard; the file
lands in `gs://x402-adserver-creatives/creatives/{uuid}.{ext}` with
public-read access (`allUsers:objectViewer`). The campaign's `creative_url`
column points at that GCS object.

**This endpoint exists in production too** — third-party advertisers will
need somewhere to put creatives the publisher can fetch and play, so
creative hosting is not strictly demo-only. Implications:

- We are now in the loop on creative content. A third party could upload
  anything — illegal, infringing, malicious — and our public bucket serves
  it on partner publisher screens.
- Bucket is intentionally public-read. Locking creatives behind signed URLs
  is doable but imposes auth coupling on the publisher network we don't
  want to introduce today.
- Upload constraints enforced: JPG/PNG only, exactly 1920×1080, max ~5 MB.
  Validated client-side AND server-side (Pillow). Browsers can be bypassed;
  trust nothing from the client.
- Pre-mainnet content moderation is a real blocker (§7.16).

### Inventory transparency (added 2026-04-24)

`GET /api/markets` (advertiser-authed) returns per-DMA display counts
derived from `backend/data/venues.json` (a flattened export of the
publisher's `companies` + `screens` Mongo collections). Today this is the 6
DMAs of our single demo publisher (NY / LA / SF / Miami / Austin / Boston).

In production with multiple publishers this means every authenticated
advertiser can read every publisher's inventory composition (size, by
market). Probably not a competitive risk — these counts are advertised
publicly by panel operators anyway — but worth knowing before onboarding
the first publisher who treats inventory size as proprietary.

---

## 6. Risk-owned decisions (still open)

Tracked canonically in `PLAN.md §Open decisions still to resolve`. Listed
here with business framing.

### SOL gas subsidy model (raised 2026-04-22)
- **What:** whether we continue subsidizing ~$2/campaign of SOL from treasury
  on mainnet, or switch to a different model.
- **Options:**
  - (A) Privy fee sponsorship (`sponsor: true`) — Privy pays the SOL fee and
    invoices us in fiat. Needs Privy plan that supports it. Cleanest answer.
    One-line code change.
  - (B) Keep subsidizing. Price the $2 + $0.001/play into our CPM margin.
    Simplest, but abandoned drafts cost us real money.
  - (C) Charge the advertiser SOL via a second x402 handshake. Blocked by
    the "recursive gas" problem: advertiser's embedded wallet also starts
    with 0 SOL, so we'd have to bootstrap theirs too. Not recommended.
- **Decide by:** before Session 13 (GCP deploy) at the latest. Before mainnet
  non-negotiable.
- **Externally:** until decided, any conversation about "cost per campaign"
  on mainnet should use the (B) figure ($2 + $0.001/play).

### Campaign-api vs ad-server split (raised 2026-04-21)
- **What:** whether the campaign-management API (create, stats, pause,
  refund) lives in the same service as the bid/proof hot path, or is split
  into a separate service.
- **Why it matters:** the bid path has a <500ms latency target. A split that
  forces a network hop on every bid kills it.
- **Recommendation:** shared DB, two FastAPI apps in the same process (~1
  session of work). Deferred until we have pressure to decouple.

### Faucet rate limiting
- **What:** today `/api/faucet` will serve as often as called. Needs a
  per-user per-hour cap before we demo publicly to prevent treasury drain.
- **Status:** noted as a Session 2 leftover, currently not gated.

### Demo CPM lock (decided 2026-04-24)
- **What:** demo CPM is fixed at **$0.50** ($0.0005/play, 500 base units of
  USDC) via `DEMO_CPM` env var, with no UI lever for advertisers.
- **Why:** chosen so the most expensive demo configuration fits inside the
  20 USDC / 2h Circle faucet ceiling. Full-fat selection (all 6 DMAs × 7
  days) lands at ~$232 to escrow at this rate — not affordable on a single
  faucet hit, so advertisers will naturally select a subset. Typical demo
  flow (1–3 DMAs × 2–7 days) lands at $15–$20, fundable from 1–2 faucet
  pulls.
- **External-facing:** real-world DOOH CPMs are $5–$100. When discussing
  pricing publicly, do **NOT** cite $0.50 as our rate — it's a faucet-driven
  artifact of the devnet demo, not a price point.
- **Re-evaluate:** when migrating to mainnet, replace `DEMO_CPM` env with
  either a per-publisher floor or a true bid-up auction model.

### Protocol fee model (decided 2026-04-24)
- **Rate:** 2.5% of the campaign total (`fee = budget × 0.025`), charged
  upfront. Advertiser pays `budget + fee` into the campaign wallet at
  funding time; an immediate Privy transfer moves the fee from the campaign
  wallet to a dedicated `PROTOCOL_REVENUE_WALLET` (its own Privy server
  wallet, separate from treasury).
- **Why upfront, not per-play:** simpler — one fee transfer per campaign, not
  per play. Doubling on-chain ops at every settlement isn't worth the
  marginal accounting honesty.
- **Why a separate wallet from treasury:** treasury = faucet source;
  protocol-revenue = fee sink. Cleaner narrative + cleaner accounting.
  Solscan shows two distinct addresses doing two distinct jobs.
- **Recoverability:** protocol fee is **non-refundable**. Refund only
  returns `budget - spent` from the campaign wallet, not the fee.
  Advertiser-facing UX must make this clear at the calculator step.
- **Schema:** new `Campaign.protocol_fee_amount` column tracks the fee taken
  on each campaign for clean reconciliation.

---

## 7. Mainnet go-live blockers

What must be decided/built before we can ship to real money. (Hackathon
submission goes to devnet only; this list matters only when we're ready to
commercialize.)

1. **SOL subsidy decision.** §6.A preferred.
2. **Advertiser API-key auth infrastructure.** Decided: production
   advertisers authenticate via API key (in `X-API-Key` header), not Privy
   JWT. We cannot require third-party ad-tech platforms to adopt Privy.
   What we need to build:
    - Per-advertiser API key issuance + hashed storage
    - Key rotation flow (old key works for a grace window, new key active)
    - Revocation flow (compromised key → immediate invalidation)
    - An `advertisers` table with `id`, `name`, `refund_wallet_address`,
      `created_at`, `status`
    - A new `require_advertiser_api_key` dependency to replace
      `require_advertiser` on all `/api/campaigns*` and `/api/wallet` routes
      in the production build
    - Onboarding UX (how does a new advertiser request a key — portal,
      manual, both)
    - Keep `require_advertiser` (Privy JWT) available as a dev/demo-only
      path for our internal dashboard
   Estimated ~1–2 engineering sessions. Must land before any third-party
   integration.
3. **Trustless custody upgrade (conditional — decide based on TVL and
   counterparty trust).** Today Privy + us jointly control campaign wallets.
   Fine for closed beta with trusted counterparties; problematic once you're
   holding meaningful TVL from strangers. The production roadmap replaces
   Privy server wallets with an Anchor program using Program Derived
   Addresses (PDAs) for on-chain escrow — no private key anywhere, refunds
   enforced by code. Estimated 4–5 weeks of Rust/Anchor work. **Gates
   blocker #5 below** (smart contract audit only applies if we do this).
4. **Backend security review (recommended before opening to third-party
   advertisers).** Standard web-app audit — auth flows, API-key handling,
   SQL injection, privilege escalation, payment race conditions, secret
   storage in GCP. **Cost:** $5–20K, 1–2 weeks. Not as existential as a
   smart-contract audit because any finding is patchable server-side.
   Serious B2B advertisers will ask whether you've done this during
   procurement due diligence. Recommend at least one pass before public
   onboarding; optional for closed beta.
5. **Solana program audit (conditional on blocker #3).** Only applies *if*
   we ship the Anchor upgrade. On-chain code is effectively immutable
   once deployed and directly controls funds, so audit quality matters.
   Market rates (scope = simple escrow program, 2026 calibration):

   | Path                                               | Cost                     | Time     |
   |----------------------------------------------------|--------------------------|----------|
   | Top-tier firm (OtterSec, Halborn, Zellic, ToB)     | $40–80K                  | 4–8 wks  |
   | Mid-tier / specialist solo auditor                 | $15–35K                  | 3–5 wks  |
   | Audit contest (Code4rena, Sherlock, Cantina)       | $10–30K prize pool       | 1–3 wks  |
   | Internal review + public bug bounty (Immunefi)     | $5–10K + ongoing bounty  | Ongoing  |

   **Decision framework:** closed beta with capped TVL → internal review +
   bounty is defensible. Public mainnet with strangers → mid-tier or above.
   High TVL → top-tier is table stakes. If we stay on Privy server wallets
   (skip blocker #3), this item does not apply at all.
6. **Refund-address ownership verification.** See §5 — today we trust the
   address the advertiser gave us. Options: signed challenge at
   registration; lock-at-creation-time; dispute window. Pick one before
   mainnet.
7. **Rate limiting & abuse.** Faucet limiting (§6), per-advertiser bid-rate
   caps, publisher API-key revocation flow, advertiser API-key rate limits.
8. **Dispute resolution.** Today, `POST /proof` is the final word. Real
   advertisers will want a window to challenge fraudulent proofs. Not on the
   hackathon roadmap.
9. **Hardware attestation for proof-of-play.** TPM-signed proofs from the
   display device, not just publisher say-so. Reduces fraud at source.
10. **Multisig oracle.** Ad server signature alone is not sufficient for
    high-value campaigns. 2-of-3 multisig (us + independent verifier +
    arbitrator) before mainnet.
11. **CPM-to-USDC FX assumption.** Currently 1:1 peg assumed ("CPM $12.50"
    becomes "0.0125 USDC/play"). True for USDC, but if advertisers want to
    be billed in other fiat, FX layer needed.
12. **JWT server secret rotation.** `proof_context` tokens are signed with a
    server secret. Rotating this secret invalidates every in-flight
    proof_context. Needs a dual-secret-acceptance window for zero-downtime
    rotation.
13. **Privy plan upgrade.** Currently on the free/starter plan. Mainnet
    traffic + fee sponsorship likely requires an upgrade. Negotiate before
    commit.
14. **Retry safety for non-idempotent on-chain operations.** Tied to the
    Privy `reference_id` quirk documented in §3 — duplicate `reference_id`
    does not prevent Privy from broadcasting a duplicate tx, so naive
    "same reference_id on retry" is double-spend-unsafe. Before mainnet we
    need ONE of:
    - (A) Confirmation from Privy that pre-broadcast idempotency will be
      added (ask + get it in writing for our plan)
    - (B) Our own pre-flight check before every retry: query Solana via
      `getSignaturesForAddress` on the source wallet for a tx with our
      known signature / reference tag within the last N blocks, and only
      retry if nothing shows up
    - (C) Policy decision: no automatic retry on any wallet-moving call
      (faucet / settlement / refund / campaign fund). Surface the failure
      to the caller and let them re-initiate with a fresh key.
    The existing `sign_and_send_solana` retry loop is narrow enough to
    likely still be safe (retries only on `transaction_broadcast_failure`,
    which Privy only returns when broadcast did not happen), but that
    narrow safety has to be re-audited when Privy's API ships changes.
15. **Concurrency correctness on `/bid` + `/proof`.** Two known races exist
    today and are accepted for the hackathon scale (one concurrent user). See
    `PLAN.md → "Must-fix before mainnet"` for full detail and proposed fixes:
    - **Budget overcommit at `/bid`**: we mint unbounded `proof_context` JWTs
      against the same campaign with no reservation. With real publisher
      concurrency, extras get rejected at settle time as "insufficient budget"
      and pile up failed settlement rows.
    - **Read-modify-write race on `campaigns.spent`** in the settlement
      pipeline: two concurrent `/proof` calls on the same campaign can both
      pass the budget guard, both increment, and last-write-wins — recording
      one debit while broadcasting two on-chain transfers. This is a silent
      campaign-wallet over-drain.
    Both fixes are engineering-only (single atomic UPDATE with guard clause +
    a `pending_bids` table or `reserved` column), ~1 session combined. Must
    land before multi-worker deployment or any third-party publisher access.
16. **Creative content moderation.** Once advertisers can upload creatives
    to our public GCS bucket (§5 Creative hosting), we are responsible for
    what gets served on partner publisher screens. Today: zero filtering
    beyond MIME + dimension validation. Pre-mainnet, at minimum: an
    NSFW/safety classifier on upload (Sightengine, AWS Rekognition Content
    Moderation, or similar managed API), a manual review queue for flagged
    items, and a takedown path for post-publication complaints. Ideally
    per-publisher brand-safety rules layered on top. Cost depends on
    managed-API choice — back-of-envelope $0.001–$0.005 per upload at
    Rekognition/Sightengine pricing, manageable.

---

## 8. Single source of truth — where engineers keep this current

- Unit economics in §2 are derived from `app/routers/campaigns.py` (SOL seed
  amount) and standard Solana fees. If the seed changes, update §2.
- Upstream policy (§3) is checked against vendor docs at review time —
  update the "last reviewed" date at the top of this file.
- Protocol status (§4) is re-checked against the Coinbase x402 repo; the
  re-check trigger is in `PLAN.md §Protocol notes`.
- Open decisions (§6) must match `PLAN.md §Open decisions still to resolve`.
  If they disagree, `PLAN.md` wins — this file tracks business framing,
  `PLAN.md` tracks engineering state.
- Mainnet blockers (§7) are derived from `BACKGROUND-INFORMATION.md
  §Production Roadmap`; business-facing items (cost, SLA) live here,
  engineering items live there.

### Known drift from `BACKGROUND-INFORMATION.md`

- §Auth says *"For production: advertiser's own platform authenticates via
  Privy **or** API key."* **This ambiguity is resolved: production uses API
  key.** `BACKGROUND-INFORMATION.md` is treated as a read-only spec
  reference; the resolved decision lives here (§5 + §7.2) and in `PLAN.md`.
