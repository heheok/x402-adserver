# Session 13 — Wizard shell + creative image upload (Feature 1) ✅

**Date:** 2026-04-27

## Checklist

- [x] Refactor `CreateCampaignForm.tsx` into a wizard shell with step indicator + back/next; closing the modal discards state (no draft persistence between steps)
- [x] **Step 1 — Image**: file picker (JPG/PNG only), client-side validation via `Image()` constructor (must be exactly 1920×1080), preview thumbnail, **auto-upload-on-pick** (improved over the original "upload-on-next" wording — see findings) with progress bar
- [x] Backend: `POST /api/creatives` (multipart, advertiser-authed). Re-validates with Pillow (don't trust browser). Uploads to `gs://x402-adserver-creatives/creatives/{uuid}.{ext}`. Returns `{creative_id, creative_url, width, height, format}`.
- [x] Bucket setup: uniform bucket-level access + `allUsers:objectViewer`
- [x] Service account JSON in `backend/.secrets/gcs-creatives-sa.json` (gitignored), mounted into the container at `/app/.secrets/` read-only via `docker-compose.yml`. Workload Identity deferred to Session 18 deploy.
- [x] Dropped `creative_url` and `creative_id` text inputs from the form — wizard threads them down to step 2 from upload state
- [x] No schema change to `models.Campaign` — existing `creative_url` + `creative_id` columns receive the upload result on submit

**Exit criteria met (2026-04-27):** uploaded a 1920×1080 JPG via the dashboard, wizard advanced to step 2 showing the thumbnail, returned URL opens publicly in a browser, campaign funded successfully through the full x402 flow with the GCS URL persisted on the row.

**Findings worth keeping:**

- **Auto-upload UX:** the original plan said "upload-on-next" — what shipped is "upload immediately on valid pick". The user already chose the file; a second confirmation click was friction. axios `onUploadProgress` gave a free progress bar (reuses the existing `.bar` class from CampaignCard). On localhost devnet uploads finish in one frame, so the bar usually flashes through to "Validating on server…" while Pillow + GCS finish.
- **Pillow `verify()` quirk:** `Image.verify()` invalidates the image instance, so we open the bytes twice — once for `verify()`, once for `.size`. Safe and cheap for 5MB max images. Documented inline in `routers/creatives.py`.
- **MIME spoofing:** browser-supplied `Content-Type` is not trusted on the server. Pillow's auto-detected `img.format` is the real check; the upload's MIME is only used to pick the URL extension. Both client and server enforce 1920×1080 + 5MB.
- **docker-compose mount:** `./backend/.secrets:/app/.secrets:ro` — `:ro` so a compromised app process can't overwrite credentials. Path inside the container is what `GCS_CREDENTIALS_JSON` points at.
- **Wizard structure:** `CreateCampaignForm.tsx` is now a thin shell that renders one of `wizard/Step{Image,Details}.tsx`. STEPS array drives the breadcrumb. Sessions 14 + 15 will add `StepTargeting`, `StepSchedule`, `StepCalculator`, and rename `StepDetails` → `StepReview`. Closing the New-campaign panel unmounts the wizard so all state (including in-flight upload) is discarded — matches the "no draft persistence" requirement.

**RUNBOOK additions:** new "Creative uploads (GCS)" section with the one-time provisioning CMD commands, `.env` lines, sanity-check curl, and SA-key rotation steps.

## Work log entry

- **2026-04-27 (Session 13):** Wizard shell + creative upload (Feature 1) shipped. Backend: new `app/services/gcs.py` (lazy storage client; service-account creds loaded from `GCS_CREDENTIALS_JSON` path, cached via `functools.lru_cache`) + `app/routers/creatives.py` (`POST /api/creatives`, advertiser-authed multipart, re-validates dimensions + format with Pillow, rejects non-JPG/PNG and non-1920×1080, 5 MB ceiling — all via `creative_*` settings on the config). Wired into `app.main`. New deps: `Pillow`, `google-cloud-storage`, `python-multipart`. Frontend: `CreateCampaignForm.tsx` rebuilt as a thin wizard shell that delegates to `components/wizard/StepImage.tsx` + `StepDetails.tsx`; STEPS array drives the breadcrumb so future sessions just append. StepImage validates with the browser's `Image()` decoder before upload, then auto-uploads (no separate confirm-click) with an axios `onUploadProgress`-driven progress bar reusing the existing `.bar` styles. StepDetails is the previous fund flow with the creative thumbnail rendered above + a "Back" button. GCP setup: project `x402-494608`, bucket `gs://x402-adserver-creatives` (UBLA + `allUsers:objectViewer`), dedicated service account `x402-creatives-uploader` bound to `roles/storage.objectCreator` on the bucket only (least privilege). SA JSON lives at `backend/.secrets/gcs-creatives-sa.json` (gitignored), mounted into the container `:ro`. End-to-end: upload → preview → fund flow runs unchanged. **Skipped this session per business constraints §7.16:** content moderation — pre-mainnet blocker, out of scope for hackathon.
