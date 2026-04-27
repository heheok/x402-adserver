from __future__ import annotations

import io
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..dependencies import AdvertiserIdentity, require_advertiser
from ..services.gcs import GCSError, upload_public_object

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


@router.post("", response_model=CreativeUploadResponse)
async def upload_creative(
    file: UploadFile = File(...),
    advertiser: AdvertiserIdentity = Depends(require_advertiser),
    settings: Settings = Depends(get_settings),
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
    try:
        url = upload_public_object(
            object_name=object_name,
            data=data,
            content_type=_PILLOW_FORMAT_TO_CONTENT_TYPE[pillow_format],
        )
    except GCSError as e:
        logger.exception(
            "GCS upload failed advertiser=%s object=%s", advertiser.user_id, object_name
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"creative upload failed: {e}",
        ) from e

    logger.info(
        "creative uploaded advertiser=%s url=%s size=%d %dx%d",
        advertiser.user_id,
        url,
        len(data),
        width,
        height,
    )
    return CreativeUploadResponse(
        creative_id=creative_id,
        creative_url=url,
        width=width,
        height=height,
        format=pillow_format,
    )
