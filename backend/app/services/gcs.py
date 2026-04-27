from __future__ import annotations

import logging
from functools import lru_cache

from google.cloud import storage
from google.oauth2 import service_account

from ..config import get_settings

logger = logging.getLogger(__name__)


class GCSError(RuntimeError):
    pass


@lru_cache
def _client() -> storage.Client:
    settings = get_settings()
    if not settings.gcs_credentials_json:
        raise GCSError(
            "GCS_CREDENTIALS_JSON not configured — see backend/.env.example"
        )
    creds = service_account.Credentials.from_service_account_file(
        settings.gcs_credentials_json
    )
    return storage.Client(credentials=creds, project=creds.project_id)


def upload_public_object(
    *,
    object_name: str,
    data: bytes,
    content_type: str,
) -> str:
    """Upload `data` as a publicly-readable object and return its URL.

    Bucket is configured at provisioning time with allUsers:objectViewer +
    uniform bucket-level access, so we don't set per-object ACLs here.
    """
    settings = get_settings()
    if not settings.gcs_bucket_name:
        raise GCSError("GCS_BUCKET_NAME not configured")

    bucket = _client().bucket(settings.gcs_bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_string(data, content_type=content_type)
    return f"https://storage.googleapis.com/{settings.gcs_bucket_name}/{object_name}"
