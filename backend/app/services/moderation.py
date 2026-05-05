"""Vertex AI content moderation for ad creatives (Session 19.5).

Calls Gemini 2.5 Flash with structured output to classify uploaded creatives
against a three-tier policy (auto-reject / review / approve). Returns a typed
verdict the router maps to HTTP status + DB persistence.

Auth: dedicated SA `x402-moderation-classifier` (least privilege —
roles/aiplatform.user only). SA key path comes from `moderation_credentials_json`
in settings; same `:ro` mount pattern as `services/gcs.py`.

If `MODERATION_ENABLED=false` the router never calls into here. We *also*
provide a `disabled_verdict()` shortcut so unit tests + e2e_demo can wire the
short-circuit at the call site without importing the SDK.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

from google import genai
from google.genai import types
from google.oauth2 import service_account
from pydantic import BaseModel, Field

from ..config import get_settings

logger = logging.getLogger(__name__)


class ModerationError(RuntimeError):
    pass


Verdict = Literal["approve", "review", "reject"]


class ModerationVerdict(BaseModel):
    """Structured response schema. Gemini fills these fields directly via
    response_schema; we never parse free-form text."""

    verdict: Verdict = Field(
        description=(
            "approve = clean, ship to GCS and let the campaign launch. "
            "review = upload to GCS but flag for human review (Tier 2 categories). "
            "reject = block the upload, do not write to GCS (Tier 1 / Tier 3)."
        )
    )
    categories_flagged: list[str] = Field(
        default_factory=list,
        description=(
            "Short slugs identifying which policy categories triggered. "
            "Examples: nsfw, violence, weapons, hate, illegal_drugs, scam, "
            "deceptive_ui, alcohol, tobacco, gambling, political, religious, "
            "competitor_crypto_brand, blank_image, unreadable, accidental_screenshot, "
            "ip_infringement, qr_code. Empty for approve verdicts."
        ),
    )
    reasons: list[str] = Field(
        default_factory=list,
        description=(
            "1-3 short natural-language reasons. Surfaced to the advertiser on "
            "reject (422 response) and to admins via list_pending_moderation."
        ),
    )
    confidence: float = Field(
        ge=0, le=1, description="Model self-reported confidence in the verdict."
    )


SYSTEM_PROMPT = """You are a content moderator for a digital out-of-home (DOOH)
advertising platform. Ads are displayed on screens placed in cafes, bars, and
restaurants — a mixed-audience public setting. The platform pays publishers in
USDC on Solana via the x402 payment protocol; advertisers are typically
crypto-native businesses.

Classify each uploaded creative against the policy below and return a
structured verdict.

# Tier 1 — REJECT (no ambiguity)
- Sexual / adult / nudity content
- Graphic violence, gore, weapons (especially firearms / knives presented as
  weapons rather than tools)
- Hate symbols, slurs, extremist iconography
- Illegal drugs (cocaine, meth, heroin imagery — alcohol/tobacco/cannabis are
  Tier 2, not Tier 1)
- Self-harm / suicide imagery
- Minors depicted in adult, sexual, or harmful contexts
- Crypto-scam patterns: "guaranteed 100x", "free SOL", "free USDC", fake
  giveaways, fake celebrity endorsements (especially Elon Musk / Vitalik Buterin
  in a giveaway context), fake countdown urgency, phishing-style
  "your wallet is compromised" messaging, fake airdrop claims
- Deceptive UI mimicry: looks like a system dialog, fake error message, fake
  "you won" popup, anything that tries to trick the viewer into thinking it's
  not an ad

# Tier 3 — REJECT (quality / sanity)
- Solid single-color image with no visible content (likely a broken upload).
  IMPORTANT: a minimalist ad with a single bold headline on a colored
  background is NOT a Tier 3 reject — minimalism is a valid design choice.
  Reject only if there is genuinely no readable content at all.
- Genuinely illegible text — would be unreadable at 5 feet from a 1080p
  screen. Headlines at 100px+ on a contrasting background are readable;
  do NOT flag a clear minimalist headline as unreadable.
- QR codes (block entirely for v1 — destination is unverifiable)
- Obvious accidental screenshot: chat window, error dialog, IDE, file picker,
  or other content clearly not intended as an advertisement
- IP infringement: copyrighted characters used without authorization (Disney,
  Marvel, Nintendo, etc.), unauthorized brand mimicry

# Tier 2 — REVIEW (legal but venue-dependent or sensitive)
- Alcohol, tobacco, vaping, cannabis (legal but venue-dependent — fine in bars,
  not in coffee shops near schools)
- Gambling / sportsbook / casino
- Pharmaceutical or health claims ("cure", "lose 30 lbs in a week",
  prescription drugs)
- Political / electoral / religious content
- Firearms in a non-violent context (range advertising, sporting goods)
- Competitor crypto brand prominence: ads heavily featuring other L1 chains
  (Ethereum, Bitcoin, Sui, Aptos, etc.) or competitor ad protocols. A small
  mention is fine; ad-as-promotion-of-the-competitor is not.

# Output rules
- Default to **approve** if nothing in the image triggers a policy.
- Use **reject** for any Tier 1 or Tier 3 match, no matter how small.
- Use **review** for Tier 2 matches when the image is otherwise clean.
- If you see BOTH a Tier 1/3 reason AND a Tier 2 reason, the verdict is reject.
- categories_flagged must be empty for approve.
- reasons should be 1–3 short, specific phrases the advertiser can act on.
  ("Image contains visible firearms" — not "this image is bad").
- confidence is your own calibration: 0.95+ for clear-cut, 0.6–0.8 for borderline.
"""


@lru_cache
def _client() -> genai.Client:
    settings = get_settings()
    if not settings.vertex_project_id:
        raise ModerationError("VERTEX_PROJECT_ID not configured")
    if not settings.moderation_credentials_json:
        raise ModerationError("MODERATION_CREDENTIALS_JSON not configured")
    creds = service_account.Credentials.from_service_account_file(
        settings.moderation_credentials_json,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return genai.Client(
        vertexai=True,
        project=settings.vertex_project_id,
        location=settings.vertex_location,
        credentials=creds,
    )


def disabled_verdict() -> ModerationVerdict:
    """Short-circuit return when MODERATION_ENABLED=false. Lets callers
    avoid an SDK import path entirely in the disabled case."""
    return ModerationVerdict(
        verdict="approve",
        categories_flagged=[],
        reasons=["moderation disabled"],
        confidence=1.0,
    )


def classify(*, image_bytes: bytes, mime_type: str) -> ModerationVerdict:
    """Classify a creative image against the three-tier policy.

    Raises ModerationError on persistent SDK failure. Caller decides whether
    to fail the upload (strict) or fall back to a "review" verdict (permissive).
    """
    settings = get_settings()
    client = _client()
    try:
        response = client.models.generate_content(
            model=settings.moderation_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                "Classify this ad creative against the three-tier policy.",
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=ModerationVerdict,
                temperature=0,
            ),
        )
    except Exception as e:
        # SDK exceptions don't share a common base; log and re-raise as ours.
        raise ModerationError(f"vertex generate_content failed: {e}") from e

    parsed = response.parsed
    if not isinstance(parsed, ModerationVerdict):
        # Fallback: SDK didn't hydrate; try the raw text.
        try:
            parsed = ModerationVerdict.model_validate_json(response.text or "")
        except Exception as e:
            raise ModerationError(
                f"vertex returned unparseable response: {response.text!r}"
            ) from e

    return parsed
