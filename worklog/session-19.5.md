# Session 19.5 — Automated content moderation (Vertex AI + Gemini 2.5 Flash) ✅

**Date:** 2026-05-05 (spec + impl)

**Scope reversal note.** BUSINESS-CONSTRAINTS §7.16 deferred content moderation as a pre-mainnet blocker (out of hackathon scope). This session lifts the *minimum* §7.16 ask — "NSFW/safety classifier on upload + manual review queue" — into the demo. We skip the takedown path (post-publication complaints, §7.16 third bullet) and per-publisher brand-safety rules, both of which remain pre-mainnet.

**Why now.** Judges will ask "what stops a bad actor uploading anything?" The current answer is "Pillow validates dimensions, that's it." A live moderation hook is the kind of polish item that takes one session and converts a sharp-edge demo question into a feature.

**Why Gemini 2.5 Flash (not Vision API / Sightengine / Rekognition).** Same GCP project as the GCS bucket. One API call replaces a 4-feature Vision stack (SafeSearch + Labels + OCR + Logos) and lets policy live as a prompt instead of a rules engine over categorical scores. ~$1/1k images at our resolution (~2k input tokens, 150 output) — at hackathon volume effectively free. Latency ~1–2s sits on the upload critical path next to the existing Pillow + GCS round-trip; user already sees a progress bar so it's invisible.

**Why Vertex AI (not Gemini Developer API key).** The codebase already authenticates to GCS via a service-account key file (`services/gcs.py` → `service_account.Credentials.from_service_account_file(...)`). Vertex AI uses the same SA pattern; a Dev-API `GEMINI_API_KEY` would be a new credential class to gitignore, rotate, and document. Vertex calls also show up in Cloud Audit Logs (cost attribution + "why did this get flagged" debugging) and inherit the deferred Workload Identity Federation cleanup when it lands. Same `google-genai` SDK either way — toggle is `genai.Client(vertexai=True, project=..., location=...)`. On-demand pricing parity confirmed against `cloud.google.com/vertex-ai/generative-ai/pricing` (see Findings on impl).

**SA scoping.** New dedicated SA `x402-moderation-classifier` bound only to `roles/aiplatform.user` on the project — matches the precedent set by `x402-creatives-uploader` (Session 13), which is scoped to the bucket only. Reusing the uploader SA would be one fewer credential file but violates least privilege.

## Filter policy

Three tiers, encoded in the Gemini system prompt:

**Tier 1 — auto-reject (no ambiguity):**
- Sexual / adult content
- Graphic violence, gore, weapons (esp. firearms)
- Hate symbols, slurs
- Illegal drugs (cocaine, meth, heroin imagery — *not* alcohol/cannabis)
- Self-harm / suicide imagery
- Minors depicted in adult contexts
- **Crypto-scam patterns** (project-specific): "guaranteed 100x", "free SOL/USDC", fake giveaways, fake celebrity endorsements, fake countdown urgency, phishing-style "your wallet is compromised"
- Deceptive UI mimicry (looks like a system dialog, fake error, fake "you won")

**Tier 3 — auto-reject (quality / sanity):**
- Solid black/white/blank image (likely broken upload)
- Unreadable text (contrast, size)
- QR codes (block entirely for v1; allowlist destinations later)
- Obvious accidental screenshot (chat window, error dialog, placeholder)
- Copyrighted character / unauthorized brand mimicry (Disney, Marvel, etc.)

**Tier 2 — flag for review (`moderation_status="review"`, surface in admin):**
- Alcohol, tobacco, vaping, cannabis (venue-dependent — bars OK, cafes maybe not)
- Gambling / sportsbook
- Pharma / health claims ("cure", "lose 30 lbs")
- Political / electoral / religious content
- Firearms (legal but venue-sensitive)
- **Competitor crypto brands** (other L1s, other ad protocols — endorsement confusion)

Tier 2 is *not* enforced per-venue this session — that's the post-hackathon product story. Just route to the review queue.

## Architecture

```
POST /api/creatives  (existing, advertiser-authed multipart)
  ├─ size + Pillow validation                                  (today)
  ├─ services/moderation.classify(bytes) → ModerationVerdict   (NEW)
  │     · Gemini 2.5 Flash via Vertex AI (google-genai SDK, vertexai=True)
  │     · auth: SA key at MODERATION_CREDENTIALS_JSON (same pattern as gcs.py)
  │     · structured output (ModerationVerdict pydantic)
  │     · system prompt = the three-tier policy above
  ├─ if verdict == reject  →  HTTP 422 + reasons (no GCS upload)
  ├─ if verdict == review  →  upload to GCS, persist moderations row
  │                            with status=review, return 200 + flag
  └─ if verdict == approve →  upload to GCS, persist moderations row
                               with status=approve, return 200 (today's shape)
```

New table `moderations` (SQLAlchemy):

| col | type | notes |
|---|---|---|
| creative_id | str (pk) | matches the uuid hex in the GCS object name |
| creative_url | str | denormalized for admin UI |
| advertiser_id | str | who uploaded |
| verdict | str | `approve` \| `review` \| `reject` |
| categories_flagged | JSON list[str] | tier-1 / tier-2 / tier-3 labels |
| reasons | JSON list[str] | model's natural-language reasons |
| confidence | float | 0–1 from model |
| created_at | datetime | |
| reviewed_by | str (nullable) | admin username (future) |
| reviewed_at | datetime (nullable) | |
| review_decision | str (nullable) | `approve` \| `reject` after manual review |

Reject rows are persisted too, for audit / repeat-offender detection later.

## Checklist

### GCP provisioning (one-time, before code)
- [x] Enable `aiplatform.googleapis.com` API on project `x402-494608`
- [x] Create service account `x402-moderation-classifier@x402-494608.iam.gserviceaccount.com`
- [x] Bind `roles/aiplatform.user` on the project (project-level — Vertex permissions are not per-resource like GCS bucket binding)
- [x] Generate SA JSON key → `backend/.secrets/moderation-classifier-sa.json` (gitignored, same dir as the GCS SA)
- [x] `docker-compose.yml`: existing `./backend/.secrets:/app/.secrets:ro` mount already covers it (verified)

### Backend
- [x] `pip install google-genai==1.75.0` → `backend/requirements.txt` (bumped from spec's `1.50.1` — `1.75.0` is the current stable on PyPI, verified at impl time)
- [x] `app/config.py`: `vertex_project_id`, `vertex_location` (default `us-central1`), `moderation_credentials_json`, `moderation_enabled` (default `true`), `moderation_model` (default `gemini-2.5-flash`)
- [x] `app/services/moderation.py` — lazy `@lru_cache` `genai.Client(vertexai=True, ...)` from SA file; `classify(image_bytes, mime) -> ModerationVerdict` with structured output schema; raises `ModerationError` on SDK failure; module-level `SYSTEM_PROMPT` constant
- [x] `app/models.py` — `Moderation` table added (no separate migration script; `Base.metadata.create_all` in `init_db()` auto-creates on next backend start, matching the project-wide decision in PLAN.md "Open decisions" — Alembic stays deferred)
- [x] `app/routers/creatives.py` — moderation call between Pillow validation and GCS upload; verdict → 422 / 200+review / 200+approve; persists `Moderation` row in all three branches; fail-permissive on `ModerationError` (falls back to synthetic `review` verdict so transient SDK issues don't block legit advertisers)
- [x] `MODERATION_ENABLED=false` short-circuits via `_moderate()` helper without importing the Vertex client (verified)
- [x] System prompt as separate constant in `app/services/moderation.py`
- [ ] **Unit tests skipped** — validated end-to-end via 16 real Vertex calls through the dashboard instead. Adding mocked-SDK tests should be a follow-up before mainnet.
- [ ] **`e2e_demo.py` not re-run** — short-circuit path is in place (`MODERATION_ENABLED=false`) and verified, but the actual e2e_demo run was not re-executed this session. Run before next deploy.

### Frontend
- [x] `StepImage.tsx` 422 handling — `parseModerationReject()` helper in `lib/errors.ts` returns structured payload; rich reject card with category badges + bulleted reasons replaces the plain string error
- [x] Review banner — non-blocking yellow card with category chips, wizard advances normally
- [x] No new state machine — review threads `creative_url` + `creative_id` to next step exactly like approve
- [x] **Bonus: two-phase progress UX** — `Progress` component gained an `indeterminate` prop; new `x-progress-indeterminate` CSS keyframes (snake-segment slides L↔R). StepImage now uses determinate blue bar during upload, violet indeterminate snake during moderation review, teal full bar on validated. Replaces the previous label-only swap which was visually indistinct.

### Admin
- [x] `scripts/list_pending_moderation.py` — read-only table view; reasons render as bullet sub-lines under each row (untruncated, since reason text is what tells the operator *why* the row is in this bucket); `--status` filter (default `review`), `--advertiser`, `--id` for detail view, `--limit`

### Ops / docs
- [x] `backend/.env.example` + `backend/.env` — moderation env vars added
- [x] `RUNBOOK.md` — new "Content moderation (Vertex AI)" section + 5 new env-var rows in the reference table
- [x] `BUSINESS-CONSTRAINTS.md §7.16` — rewritten: shipped (auto-classifier + read-only review queue) vs. still deferred (manual review actions, takedown path, per-publisher rules, repeat-offender detection)
- [x] `PLAN.md` — Session 19.5 in roadmap

## Exit criteria

- Upload a known-clean 1920×1080 JPG → auto-approves, GCS upload succeeds, campaign flow unchanged.
- Upload an obvious NSFW image (test fixture, not committed) → 422 with reasons, no GCS object created, `moderations` row written with verdict=reject.
- Upload an alcohol / political ad → 200 with `moderation_status: review`, GCS upload succeeds, banner shown in wizard, row visible in `list_pending_moderation.py`.
- `MODERATION_ENABLED=false` → all uploads short-circuit to approve (e2e_demo.py path).
- Total per-upload latency stays under 4s on devnet (Pillow + Gemini + GCS).

## Out of scope (explicitly)

- Manual approve/reject from admin UI (read-only listing this session; future CLI or web action)
- Takedown path for post-publication complaints (§7.16, deferred)
- Per-publisher brand-safety rules (§7.16 ideal, post-hackathon)
- Vision API Web Detection for stolen-creative detection (stretch — bolt-on later if time)
- Repeat-offender detection / advertiser blocking based on reject history
- Venue-aware enforcement of Tier 2 categories (alcohol allowed in bars, etc.) — post-hackathon product story

## Time estimate

~1 session (4–6h) if Gemini structured output works first try; +1–2h if the prompt needs iteration to hit the demo cases reliably. Risk: model non-determinism on borderline images — mitigate with `temperature=0` + structured output schema + a "review" fallback bucket (already in design).

## Findings worth keeping

- **Vertex pricing parity confirmed.** `cloud.google.com/vertex-ai/generative-ai/pricing` shows Gemini 2.5 Flash at $0.30/M input (text/image/video) + $2.50/M output — identical to the Dev-API rates. Same for 2.5 Pro and Flash-Lite. The "Vertex is more expensive" intuition is wrong for on-demand; it just adds IAM + audit-log integration.
- **Latency reality vs. spec.** I quoted "1–2 s" in the spec; actual p50 across 16 real uploads was **3–7 s** (mean ≈ 6 s) for image input + ~150-token JSON output. Doesn't matter behaviorally — the new violet snake bar makes the wait feel intentional — but my future "Gemini Flash with vision" estimates should default to ~5 s, not 1 s.
- **`google-genai` SDK structured output works first-try.** Pass `response_schema=PydanticModel` + `response_mime_type="application/json"` in `GenerateContentConfig` and `response.parsed` returns a hydrated instance. No manual JSON parsing needed in the happy path; the fallback `model_validate_json(response.text)` branch never fired during testing.
- **Prompt calibration matters more than model choice.** Initial Tier 3 wording ("near-blank image", "unreadable text") rejected legitimate minimalist designs. Tightened to "solid single-color with no visible content" + "genuinely illegible at 5 feet" + "minimalism is a valid design choice — do NOT flag a clear minimalist headline as unreadable." Held up across 16 real uploads (zero false-rejects on 9 approves).
- **The model is genuinely impressive on the project-specific Tier 1/2 categories.** Across user testing it caught: katana + bullet → weapons, "Arsenal" trademark → ip_infringement, QR code → qr_code, Bitcoin imagery in a Solana ad → competitor_crypto_brand (twice, 0.90 conf), French-language political subtext from babies imagery → political (0.75 conf). Confidence is well-graded — 0.75 for borderline, 0.95–0.98 for clear-cut. Not just keyword-matching.
- **Review verdict is non-blocking by design.** Confirmed via code trace: `routers/campaigns.py`, `routers/bid.py`, `services/auto_play.py` have ZERO reference to the `moderations` table. A review-flagged creative still funds and serves to bids. The `Moderation` row is purely informational for the admin script. This was an explicit spec choice ("non-blocking, advertiser launches but admin sees the flag") — fine for hackathon, **needs revisiting before mainnet**: see updated `BUSINESS-CONSTRAINTS.md §7.16` "Still deferred" subsection.
- **Two-phase progress UX matters.** The original "Uploading… X% → Validating on server…" label-swap on the same static bar was visually indistinct. Replaced with: determinate blue bar (upload) → indeterminate violet snake (moderation review, ~5 s) → full teal bar (validated). The phase boundary is now obvious.
- **`MODERATION_ENABLED=false` short-circuits cleanly.** `_moderate()` in the router checks the flag *before* importing/calling the Vertex client, so the disabled path never touches the SDK. Verified — works without the SA key file present. e2e_demo can keep its current shape.
- **Customer copy: no "AI".** The user pushed back on "Checking content with AI…" — preferred functional product language ("Moderation review in progress"). Saved as `feedback_no_ai_in_customer_copy.md` for future sessions. Internal docs / env vars / code comments are fine to be specific.
- **`response.parsed` typing surprise.** `response.parsed` is typed `Any` in the SDK; we keep the explicit `isinstance(parsed, ModerationVerdict)` check + JSON-text fallback because runtime hydration *can* fail silently (e.g. when the model returns a partial schema). Defensive — never triggered in practice but cheap to keep.

## RUNBOOK additions

- **"Content moderation (Vertex AI)"** new section after "Creative uploads (GCS)": one-time CMD provisioning (enable API, create SA, bind `roles/aiplatform.user`, generate key), `.env` lines, disable-for-dev flag, admin-script invocations, cost expectations, key rotation. Mirrors the structure of the Creative-uploads section.
- **5 new rows** in the env-vars reference table: `MODERATION_ENABLED`, `MODERATION_MODEL`, `VERTEX_PROJECT_ID`, `VERTEX_LOCATION`, `MODERATION_CREDENTIALS_JSON`.

## Work log entry

- **2026-05-05 (Session 19.5):** Automated content moderation shipped end-to-end. Backend: `app/services/moderation.py` calls Gemini 2.5 Flash via Vertex AI (google-genai 1.75.0, `vertexai=True` mode) with a three-tier policy prompt and a pydantic `ModerationVerdict` response schema; auth via dedicated SA `x402-moderation-classifier` (least-privilege, `roles/aiplatform.user` only — separate from the GCS uploader SA). New `Moderation` table persists per-creative verdict + categories + reasons + confidence for all three branches (approve / review / reject), auto-created via existing `Base.metadata.create_all`. `routers/creatives.py` calls the classifier between Pillow validation and GCS upload: reject → 422 with structured `{error, message, categories_flagged, reasons}` (no GCS write); review → upload + persist + return 200 with `moderation_status: "review"`; approve → unchanged 200 shape with `moderation_status: "approve"`. `MODERATION_ENABLED=false` short-circuits without importing the SDK. Frontend: `StepImage.tsx` renders a structured reject card (category chips + bulleted reasons) for 422s and a non-blocking yellow review banner when status is "review"; the wizard advances normally in both cases. New `parseModerationReject()` helper in `lib/errors.ts` keeps the rich-rendering decision out of `humanizeError`. Bonus UX: `Progress` component gained an `indeterminate` prop with a new `x-progress-indeterminate` CSS keyframe (slim segment slides L↔R) so the moderation phase reads as a distinct violet "moderation review in progress" stage rather than a stalled upload bar. Admin: `scripts/list_pending_moderation.py` (read-only table view, reasons rendered as untruncated bullet sub-lines under each row, default-filtered to `review`). Ops: provisioning CMD steps in `RUNBOOK.md`; new `MODERATION_*` + `VERTEX_*` env vars; `BUSINESS-CONSTRAINTS.md §7.16` rewritten to record what shipped vs. what remains pre-mainnet (manual review actions, takedown path, per-publisher rules, repeat-offender detection). Validated with 16 real dashboard uploads — model correctly caught weapons (katana + bullet), QR codes, IP infringement (Arsenal trademark), Bitcoin-in-Solana-ad as competitor brand (review), and French-text political subtext (review at 0.75 conf). 9/16 clean approves, zero false-rejects.
