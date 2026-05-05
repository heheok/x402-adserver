from __future__ import annotations

import io
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..dependencies import AdvertiserIdentity, require_advertiser
from ..models import Moderation, ModerationVerdict
from ..services.gcs import GCSError, upload_public_object
from ..services.moderation import (
    ModerationError,
    classify,
    disabled_verdict,
)
from ..services.moderation import ModerationVerdict as VerdictModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/creatives", tags=["creatives"])

# JPG/PNG only — must match the Image() validation in the wizard. Browsers can
# spoof Content-Type, so the real check is Pillow's identification of the
# decoded bytes (settings.creative_required_*). Mapping is just for the URL ext.
_PILLOW_FORMAT_TO_EXT = {"JPEG": "jpg", "PNG": "png"}
_PILLOW_FORMAT_TO_CONTENT_TYPE = {"JPEG": "image/jpeg", "PNG": "image/png"}


class CreativeUploadResponse(BaseModel):
    creative_id: str
    creative_url: str
    width: int
    height: int
    format: str
    # Session 19.5: present on every successful response. "approve" = clean,
    # "review" = uploaded to GCS but flagged in moderations table for admin.
    # "reject" never reaches here — those raise 422 with structured detail.
    moderation_status: str = "approve"
    moderation_categories: list[str] = []
    moderation_reasons: list[str] = []


def _moderate(*, image_bytes: bytes, mime_type: str) -> VerdictModel:
    """Wraps the Vertex call with the env short-circuit + a fail-permissive
    fallback. If MODERATION_ENABLED=false → instant approve. If the Vertex
    call raises → log + return a synthetic 'review' verdict so the upload
    isn't blocked by transient SDK issues but admins still see the row."""
    settings = get_settings()
    if not settings.moderation_enabled:
        return disabled_verdict()
    try:
        return classify(image_bytes=image_bytes, mime_type=mime_type)
    except ModerationError as e:
        logger.warning("moderation classify failed, falling back to review: %s", e)
        return VerdictModel(
            verdict="review",
            categories_flagged=["moderation_unavailable"],
            reasons=[f"classifier failed: {e}"],
            confidence=0.0,
        )


@router.post("", response_model=CreativeUploadResponse)
async def upload_creative(
    file: UploadFile = File(...),
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> CreativeUploadResponse:
    data = await file.read()
    if len(data) > settings.creative_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"file exceeds {settings.creative_max_bytes // (1024 * 1024)} MB limit",
        )

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()  # cheap structural check
        with Image.open(io.BytesIO(data)) as img:
            # verify() invalidates the image instance; reopen for dimensions.
            pillow_format = img.format or ""
            width, height = img.size
    except (UnidentifiedImageError, OSError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="not a valid image file",
        ) from e

    if pillow_format not in _PILLOW_FORMAT_TO_EXT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"only JPG/PNG accepted (got {pillow_format or 'unknown'})",
        )
    if (width, height) != (
        settings.creative_required_width,
        settings.creative_required_height,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"image must be exactly {settings.creative_required_width}"
                f"x{settings.creative_required_height}px (got {width}x{height})"
            ),
        )

    creative_id = uuid4().hex
    ext = _PILLOW_FORMAT_TO_EXT[pillow_format]
    object_name = f"creatives/{creative_id}.{ext}"
    mime_type = _PILLOW_FORMAT_TO_CONTENT_TYPE[pillow_format]

    verdict = _moderate(image_bytes=data, mime_type=mime_type)

    if verdict.verdict == "reject":
        # Persist the audit row with empty creative_url — the GCS object was
        # never written. Then 422 with structured reasons the frontend renders.
        db.add(
            Moderation(
                creative_id=creative_id,
                creative_url="",
                advertiser_id=advertiser.user_id,
                verdict=ModerationVerdict.REJECT.value,
                categories_flagged=list(verdict.categories_flagged),
                reasons=list(verdict.reasons),
                confidence=verdict.confidence,
            )
        )
        db.commit()
        logger.info(
            "creative rejected advertiser=%s creative_id=%s categories=%s",
            advertiser.user_id,
            creative_id,
            verdict.categories_flagged,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "moderation_rejected",
                "message": "Creative rejected by content moderation.",
                "categories_flagged": list(verdict.categories_flagged),
                "reasons": list(verdict.reasons),
            },
        )

    # approve OR review — both upload to GCS.
    try:
        url = upload_public_object(
            object_name=object_name,
            data=data,
            content_type=mime_type,
        )
    except GCSError as e:
        logger.exception(
            "GCS upload failed advertiser=%s object=%s", advertiser.user_id, object_name
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"creative upload failed: {e}",
        ) from e

    persisted_verdict = (
        ModerationVerdict.REVIEW.value
        if verdict.verdict == "review"
        else ModerationVerdict.APPROVE.value
    )
    db.add(
        Moderation(
            creative_id=creative_id,
            creative_url=url,
            advertiser_id=advertiser.user_id,
            verdict=persisted_verdict,
            categories_flagged=list(verdict.categories_flagged),
            reasons=list(verdict.reasons),
            confidence=verdict.confidence,
        )
    )
    db.commit()

    logger.info(
        "creative uploaded advertiser=%s url=%s size=%d %dx%d verdict=%s",
        advertiser.user_id,
        url,
        len(data),
        width,
        height,
        persisted_verdict,
    )
    return CreativeUploadResponse(
        creative_id=creative_id,
        creative_url=url,
        width=width,
        height=height,
        format=pillow_format,
        moderation_status=persisted_verdict,
        moderation_categories=list(verdict.categories_flagged),
        moderation_reasons=list(verdict.reasons),
    )
