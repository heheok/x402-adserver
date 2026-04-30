# Session 14 — DMA targeting + scheduling (Features 2 + 3 + 4) ✅

**Date:** 2026-04-27

## Checklist

- [x] Mongo export → `backend/data/venues.json` (gitignored; user supplies on each dev environment. 622 rows, 612 with valid DMAs across the 6 target markets)
- [x] DMA name canonicalization: lowercase Mongo codes → display labels (`ny`/`la`/`sf`/`mia`/`bos`/`aus` → `New York`/`Los Angeles`/`San Francisco`/`Miami`/`Boston`/`Austin`)
- [x] `Campaign.target_dmas` JSON column (nullable on the column for the dev-SQLite ALTER, mandatory ≥1 in `CreateCampaignRequest`)
- [x] `Campaign.start_date`, `Campaign.end_date` Date columns (UTC midnight, day-only)
- [x] In-memory venues index (`services/venues.VenuesIndex`) — `dma → device_id[]`, `device_id → dma`, `display_counts`, `pick_random_device(labels)`
- [x] `GET /api/markets` (Privy-authed) → `[{dma, display_count}, …]`
- [x] `/bid` filter: requires `imp.ext.device_id`; resolves to DMA via index; FIFO gains target_dmas membership + schedule window check; lazy-flips `active`→`expired` when `end_date < today`
- [x] Auto-play + simulate-play pick a campaign first, then a random device whose DMA matches; both also enforce the schedule window
- [x] `CampaignStatus.EXPIRED` added; refund button accepts it; double-refund guard already covers it
- [x] Wizard Step 2 — Targeting (DMA cards w/ live REACH + hardcoded frequency line)
- [x] Wizard Step 3 — Schedule (native date pickers, today-min, end ≥ start)

**Exit criteria met (2026-04-27):** E2E (`scripts/e2e_demo.py`) → 13/13 on real devnet with the new bid contract (campaigns target `San Francisco`, bid payload carries `imp.ext.device_id` from venues.json). OpenAPI shows `target_dmas`/`start_date`/`end_date` on `CreateCampaignRequest` + `CampaignSummary` and `MarketInfo` on `/api/markets`. Frontend `tsc --noEmit` clean. `expired` flip + refund verified by inspection of the `_pick_campaign` sweep path.

**Findings worth keeping:**

- **Mongo type mismatch on the join.** `screens.companyId` is a string, `companies._id` is an ObjectId. Compass `$lookup` with plain `localField`/`foreignField` returned zero matches. Fix: rewrite as `let` + `pipeline` with `$expr: { $eq: [ { $toString: "$_id" }, "$$cid" ] }`. The aggregation lives in PLAN session prompt history — re-derive from there if a future export needs to be refreshed.
- **DMA codes are Mongo lowercase short forms** (`ny`, `mia`, `aus`), not full names. `services/venues.DMA_LABELS` is the single canonicalization map; the wizard, `/api/markets`, `Campaign.target_dmas`, and the `/bid` filter all use the display labels (`"New York"`, …) so the user never sees the raw codes. 10 admin/test rows have empty `dma` (e.g. venue_name `"root"`, `"shaw"`) and are dropped at load time with an info log.
- **Docker volume swap.** The dev SQLite DB used to live in a named `backend_data` volume. Bind-mounted `./backend/data:/app/data` so the user-supplied `venues.json` is visible inside the container alongside the dev DB. The whole `backend/data/` dir stays gitignored — `venues.json` is publisher-private inventory data (specific venue names + addresses), not safe to commit. Existing DB was preserved via `docker cp` before the swap; no data loss. **For deployments + onboarding new dev environments**, the venues file must be re-provisioned per Compass-export instructions captured in this session's prompt history (Mongo `$lookup` with `let` + `pipeline` to handle the string/ObjectId join).
- **Dev-only column add for SQLite.** `create_all` is no-op on existing tables. Added `_dev_alter_table_for_existing_sqlite()` in `database.py` that runs after `create_all`, reads `PRAGMA table_info(campaigns)`, and `ALTER TABLE` for any missing columns. SQLite-only, idempotent, drop-able when we move to Postgres + Alembic in Session 17. Without this, every column-adding session would force a volume reset.
- **Auto-play vs E2E timing.** The lifespan launches the auto-play loop unconditionally (gated on `AUTO_PLAY_ENABLED` inside the loop). When the user has the flag enabled in `.env`, `docker compose run` for the e2e starts a fresh container whose lifespan also runs the loop; if it ticks during the e2e's bid → proof retry window (~7s of Privy backoff for a fresh ATA), the test campaign gets a phantom play and `spent` doubles. Fix: `os.environ["AUTO_PLAY_ENABLED"] = "false"` at the top of `scripts/e2e_demo.py` — pydantic-settings precedence is process-env over `.env` file, so this lands before `get_settings()` is called.
- **Venue name is publisher-private.** `pick_random_device` returns `{device_id, venue_name, dma}` for server-side logging (auto-play prints which venue settled), but `SimulatePlayResponse` only exposes `dma` to the dashboard. `venue_name` identifies a specific publisher partner ("2211 Club, LLC") and isn't safe to surface to advertisers — comment in `schemas.SimulatePlayResponse` calls this out so a future change doesn't accidentally leak it.
- **`/bid` lazy expired flip.** Rather than a periodic sweep job, `_pick_campaign` walks active campaigns once per bid; any with `end_date < today` get flipped to `EXPIRED` in the same pass. Cheap because the candidate list is small (single-digit campaigns at demo scale) and avoids a separate cron. If the campaign list grows, a daily background sweep is the obvious next step.
- **Refund now accepts `expired`.** The existing refund flow already declined `active` (must pause first) and `refunded` (already done). Added `EXPIRED` to the allowed-source set; `canRefund` on `CampaignCard` mirrors it. Same on-chain path as completed/paused refunds — campaign-wallet→advertiser-wallet USDC transfer signed by the campaign's Privy server wallet.

**Demo publisher inventory** (`backend/data/venues.json`, exported 2026-04-27):

| DMA           | Code | Screens |
| ------------- | ---- | ------- |
| New York      | ny   | 198     |
| Los Angeles   | la   | 160     |
| San Francisco | sf   | 115     |
| Miami         | mia  | 51      |
| Boston        | bos  | 48      |
| Austin        | aus  | 40      |
| **Total**     |      | **612** |

10 rows skipped at load (admin/test entries with empty `market`).

## Work log entry

- **2026-04-27 (Session 14):** DMA targeting + scheduling shipped. Backend: `services/venues.py` loads `backend/data/venues.json` (gitignored, user-supplied) into an in-memory index — `dma → device_id[]`, `device_id → dma`, `display_counts`, `pick_random_device(labels)`. `DMA_LABELS` map canonicalizes Mongo codes (`ny`/`la`/`sf`/`mia`/`bos`/`aus`) to display labels. `Campaign.target_dmas` (JSON), `start_date`, `end_date` (Date) added; dev-only `_dev_alter_table_for_existing_sqlite()` in `database.py` ALTERs existing tables idempotently so column adds don't force a volume reset. New `routers/markets.py` exposes `GET /api/markets` (Privy-authed). `/bid` now requires `imp.ext.device_id`, resolves DMA via the index, filters FIFO candidates by `target_dmas` + schedule window, and lazy-flips `active`→`expired` for any campaign whose `end_date < today` while iterating. `CampaignStatus.EXPIRED` added; refund accepts it. Auto-play + `simulate-play` enforce the schedule window and pick a random device whose DMA matches the campaign's targeting; auto-play logs include venue name for ops debugging but `SimulatePlayResponse` exposes only `dma` to the dashboard (venue identifies a specific publisher partner — not safe to leak). Frontend: 4-step wizard now (`StepImage` → `StepTargeting` → `StepSchedule` → `StepDetails`); StepTargeting renders the 6 DMA cards with click-to-toggle, live REACH = sum of selected display counts, hardcoded "1 every 5 min" line; StepSchedule has native date inputs with today-min validation. `CampaignCard` shows targeting + schedule in the expanded detail and surfaces the DMA on the last-play indicator. `CreateCampaignRequest` validator rejects unknown DMAs, dups, past start dates, and end before start. Docker volume swap: bind-mount `./backend/data:/app/data` so the venues file is visible inside the container; existing DB preserved via `docker cp`. E2E (`scripts/e2e_demo.py`) updated to send `device_id` from the venues index and create campaigns targeting `San Francisco`; force-disables `AUTO_PLAY_ENABLED` at the top of the file because the lifespan loop ticks during the e2e's bid → proof retry window and double-counts `spent` otherwise. 13/13 on real devnet.
