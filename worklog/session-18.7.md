# Session 18.7 — Responsive design pass + creative auto-resize + active-campaign shine ✅

**Date:** 2026-05-03

Three things shipped together in one frontend pass: (a) the responsive design pass scoped in PLAN.md, (b) client-side image normalization so judges can upload any aspect ratio (NOT in the original 18.7 scope, but added when we realized the strict 1920×1080 reject would bounce demo reviewers who throw a phone screenshot at it), and (c) a subtle shine sweep on the gradient progress bar for active campaigns (eye-candy, requested mid-session).

**Sequencing note:** PLAN.md said "don't start until faucet rate-limit (Session 19) is shipped." User explicitly overrode that ordering — wanted the responsive work first because it's user-facing demo polish. Faucet rate-limit still pending; tracked in Session 19. No regression risk in this swap (responsive changes are CSS / className only, no backend touch).

## What shipped

### Responsive system (`frontend/src/styles/tokens.css`)

- **Three breakpoints**: mobile `< 640px`, tablet `640–1023px`, desktop `≥ 1024px` (current design unchanged).
- **`x-page` container** replaces ad-hoc `padding: 32px 28px; maxWidth: 1200; marginInline: auto` repeated across Overview / Campaigns / Empty / Skeleton. Tightens to `28px 22px` at tablet, `20px 16px` at mobile.
- **Inline-style overrides via `!important`**. The dashboard's grids are inline-styled (`gridTemplateColumns: "repeat(N, 1fr)"`), and inline styles always win over class selectors. Solution: utility classes that re-set `grid-template-columns` with `!important` only inside `@media` rules — desktop keeps its inline grid untouched, smaller breakpoints override. Cleaner than restructuring every grid into CSS classes:
  - `x-grid-md-3` / `x-grid-md-2` / `x-grid-md-1` — tablet collapses
  - `x-grid-sm-2` / `x-grid-sm-1` — mobile collapses
  - `x-flex-sm-col` — flex row → column on mobile
  - `x-hide-sm` — display: none on mobile
- **Bar padding** (`x-bar-pad`) for AppHeader / TabRow → 16px horizontal on mobile.
- **Map height** override → 200px on mobile (display-only, no interaction concern).
- **Activity / settlement table column-hide rules** (see findings below for why this replaced the first attempt).

### Per-page changes

- **Login** — verified at 375px. Already a centered card with `maxWidth: 420`, just works.
- **AppHeader** (`components/AppHeader.tsx`) — `x-bar-pad` + `x-hide-sm` on the "DOOH ad network" subtitle and the "Solana · devnet" badge. Logo + wallet chip stay on row 1 at all sizes.
- **TabRow** (`components/TabRow.tsx`) — `x-bar-pad`. Tabs already small, "+ New campaign" fits.
- **Overview** (`pages/Overview.tsx`) —
  - `x-page` wrapper.
  - 4-col stat grid → 2-col tablet, 1-col mobile (`x-grid-md-2 x-grid-sm-1`).
  - Status breakdown row (5-cell flex with vertical dividers) → wraps to 2x3 on mobile via `x-status-row` rule (swaps right-borders to bottom-borders so dividers still read).
  - Header row (Overview title + auto-simulating badge) → `x-flex-sm-col` so the auto-play indicator drops below the title on mobile.
  - Empty state's 3-col how-it-works grid → 1-col mobile.
  - Recent-activity table (5 columns) → drops DMA + Tx columns on mobile (see findings).
- **Campaigns** (`pages/Campaigns.tsx`) — `x-page` wrappers on success / loading / error / empty. List was already vertical so no grid collapse needed.
- **CampaignCard** (`components/CampaignCard.tsx`) —
  - **Collapsed row** (`40px 1fr 220px 24px`) → `x-camp-collapsed` uses grid-areas to put progress on a second row spanning the width and hide the chevron at mobile (chevron is redundant when the whole card is the click target).
  - **Expanded header** (`64px 1fr auto`) → `x-camp-expanded-head` pushes the action button group (Simulate / Pause / collapse) to a separate row below the thumb + name on mobile.
  - **Title and wallet rows** (inside info cell) → added `flexWrap: "wrap"` + `whiteSpace: "nowrap"` on the meta items so things break cleanly between elements, not mid-string. Pre-fix screenshot showed "· 1 day" wrapping to "· 1 / day" — this fixed it.
  - **6-col stats grid** → 3-col tablet, 2-col mobile.
  - **Targeting + last-play** (1fr 1fr) → 1-col mobile.
  - **Recent-settlements table** (6 columns) → drops Nonce + Publisher columns on mobile, keeps When / DMA / Amount / Tx.
- **CampaignWizard** —
  - `Modal.tsx` step dots → `x-hide-sm` on the step labels (the numbered dots stay, labels disappear). Five labeled steps don't fit at 375px.
  - `StepImage.tsx` preview row → `x-img-preview` wraps so thumb + close button stay on row 1, content (filename + chips + progress bar) drops to a full-width row 2 at mobile. Original 96px thumb + 28px close + gaps left only ~120px for content, which crushed the chip row.
  - `StepTargeting.tsx` market grid → 3-col → 2-col mobile.
  - `StepSchedule.tsx` `1fr 24px 1fr` → stacks via `x-sched-grid` (arrow icon hides).
  - `StepReview.tsx` ReviewRow `160px 1fr` → stacks with value left-aligned via `x-review-row`. SuccessTx 2-col grid → 1-col mobile.

### Creative auto-resize (`components/wizard/StepImage.tsx`)

Original gate hard-rejected anything that wasn't exactly 1920×1080. **That doesn't survive demo day** — judges will throw phone screenshots / random web images at it. Replaced with client-side canvas normalization:

- Accept any JPG/PNG up to 15 MB (was 5 MB; bumped because the 5 MB cap was sized for the pre-normalized strict-1920×1080 input, and modern phone photos run 3-8 MB).
- `normalizeTo1920x1080()` reads the image, draws onto a 1920×1080 canvas with **scale-to-fit + black letterbox/pillarbox** (preserves the original creative; no crop / no aspect mangling), re-encodes as JPEG @ 0.92 quality. Output is typically 200-500 KB regardless of input size.
- Filename stem preserved (`vacation.png` → uploads as `vacation.jpg`).
- UI shows a blue **`✓ resized`** chip next to **`✓ format ok`** when normalization happened, with `title="Auto-resized for 1920×1080 DOOH screens"` for tap-and-hold context.
- Backend's existing 1920×1080 + 5 MB caps stay in place as defense-in-depth and are now always satisfied.

### Active-campaign shine (`components/ui/Progress.tsx` + `tokens.css`)

Eye-candy on the gradient progress bar to signal liveness. New `shine?: boolean` prop on `Progress`; CSS class `x-progress-shine` adds an `::after` pseudo-element with a translucent white linear-gradient that translates across the filled portion. Animation timing uses paired keyframe stops (`0%, 35%` held off-screen-left, `75%, 100%` held off-screen-right) so most of the 3.6s cycle is dead-time — reads as ambient, not busy. `pointer-events: none` so the sweep doesn't block clicks. Wired at both `CampaignCard` call sites with `shine={campaign.status === "active" && pct > 0}` so paused / draft / completed / refunded bars stay quiet, and zero-progress active campaigns don't emit a phantom sweep over an empty track.

## Findings worth keeping

- **Wide tables on narrow viewports — column-hide beats horizontal scroll.** First implementation wrapped the activity / settlements tables in `.x-tbl-scroll` with `min-width: 720px` on the inner grid, so they'd scroll horizontally below desktop. User flagged the inner scrollbar as ugly even at tablet (768) where the natural width would actually fit, because the `min-width: 720` forced overflow needlessly. Fix: drop the wrapper and the min-width rule entirely; instead, hide secondary columns at `< 640px` only via nth-child selectors. Activity drops DMA + Tx, settlements drop Nonce + Publisher. Tablet shows the full grid (it fits without forcing). Cleaner result, fewer DOM nodes, and tap targets on remaining rows aren't fighting a horizontal scroll gesture.
- **Inline-style grids + `!important` is the right move.** The dashboard is built primarily with React inline styles. Restructuring every grid into CSS classes for responsive support would have been a multi-session refactor and risked regressions. `!important` overrides scoped to `@media (max-width: …)` blocks let the inline desktop layout stay the source of truth and only bend at smaller breakpoints. Trick is to be disciplined about *only* using `!important` inside media queries — never in the base utility — so desktop behavior is never affected.
- **`flex-wrap: wrap` + `whiteSpace: "nowrap"` on meta items beats breaking flex rows into columns.** The CampaignCard expanded header's title row (name + status badge + "· N days") wrapped weirdly at first ("· 1 day" broke between "1" and "day"). Adding `flex-wrap: wrap` to the parent and `white-space: nowrap` on the badge / days span lets each *element* break to a new line as a unit, never mid-string. Pattern reusable for any horizontal label rows that need to survive narrow viewports without restructuring into a column.
- **Don't restack what already wraps.** First instinct on the CampaignCard expanded header's action button group was to stack via `flex-direction: column` on mobile. Wrong direction — the actions row already had `flex-wrap: wrap` and `justify-content: flex-end`. The issue was that they consumed too much horizontal space in the *grid* row (`64px 1fr auto`), squeezing the middle 1fr column. Real fix: restructure the parent grid (`x-camp-expanded-head`) so actions become a full-width second row at mobile via `grid-template-areas`. The actions-row's own internal flex is already fine.
- **Canvas `imageSmoothingQuality: "high"` matters for downscale.** With it, a 4032×3024 phone photo downscales to 1920×1080 cleanly. Without it, browsers use bilinear by default and the result has visible aliasing on text-heavy creatives. Cost is negligible (sub-100ms even on big inputs).
- **Filename ergonomics in re-encode.** Initial impl passed the canvas blob to upload as `creative.jpg`. User-facing UX broke: someone uploads `MyAwesomeAd_v3.png`, sees `creative.jpg` in the preview. Fix: keep the user's filename stem, only swap the extension to match the new MIME type. Display layer separately tracks `originalName` so the chip row shows what the user uploaded, while the `File` object handed to FormData is the renamed `.jpg`.
- **Progress shine over a low-pct active bar would look weirdly empty.** Gating `shine={... && pct > 0}` avoids a phantom ::after sweep across a 0%-wide fill div (still 0px wide, so the pseudo-element is also 0px — visually nothing — but conceptually misleading and a tiny perf nit on every active card).

## Acceptance

- tsc `--noEmit` clean.
- Smoke-tested in Chrome devtools device toolbar at 375 / 768 / 1280:
  - Login: card centered, no overflow.
  - AppHeader: subtitle + devnet badge hidden on mobile, present on tablet+.
  - Overview stats: 4-col → 2-col → 1-col.
  - Recent activity: 5 cols at tablet+ desktop, 3 cols (When / Campaign / Amount) on mobile.
  - Campaign card collapsed: 4-col → 2-row mobile (thumb+info / progress).
  - Campaign card expanded: header restacks, stats grid 6→3→2, settlement table 6→4 cols on mobile.
  - Wizard 5 steps: step labels hide on mobile, all forms stack cleanly.
  - StepImage: drop a non-1920×1080 image → resized chip appears, preview shows letterboxed result.
- Active campaign progress bar shows the slow shine sweep; paused campaign bar is quiet.

## Out-of-scope items removed from PLAN.md per-page list

- **"Live activity map (Overview)"** — there's no live activity map on Overview; the map only lives inside the expanded CampaignCard. PLAN.md's per-page list had this as a separate item, but it's covered by the CampaignCard expanded responsive work + `tokens.css` `.x-map { height: 200px }` mobile rule. No new code needed for it.

## Follow-ups (not blockers)

- **Smoke test on a real iPhone.** Chrome devtools simulation is good but not pixel-perfect for tap targets / safe areas. Worth doing once on a phone before submission if there's time.
- **WalletChip dropdown panel width** is hardcoded `width: 320`. On a hypothetical 320px viewport (older iPhone SE), the panel would clip. Plan target was `< 640` with 375 as the typical mobile, so this isn't blocking — but if anyone reports it, switch the panel to `max-width: calc(100vw - 32px)`.
- **Step labels "Creative", "Targeting"…** are completely hidden at mobile (only the numbered dots remain). If users find that too cryptic on phones, we could re-add the active-step's label below the dot row.
