from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..schemas import HealthResponse

router = APIRouter(tags=["health"])


class AutoPlayStatus(BaseModel):
    enabled: bool
    interval_seconds: int


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.environment,
    )


@router.get("/api/auto-play-status", response_model=AutoPlayStatus)
def auto_play_status(settings: Settings = Depends(get_settings)) -> AutoPlayStatus:
    """Public read-only flag so the dashboard can show an 'auto-simulating' badge.

    Disclosing the interval is harmless — anyone with access to the dashboard
    already sees plays happening in the settlements list.
    """
    return AutoPlayStatus(
        enabled=settings.auto_play_enabled,
        interval_seconds=settings.auto_play_interval_seconds,
    )
