from fastapi import APIRouter, Depends

from ..dependencies import AdvertiserIdentity, require_advertiser
from ..schemas import MarketInfo
from ..services.venues import get_venues_index

router = APIRouter(prefix="/api", tags=["markets"])


@router.get("/markets", response_model=list[MarketInfo])
def list_markets(
    _advertiser: AdvertiserIdentity = Depends(require_advertiser),
) -> list[MarketInfo]:
    """Per-DMA display counts for the wizard targeting step.

    Authed because in production with multiple publishers this exposes
    inventory composition (see `BUSINESS-CONSTRAINTS.md §inventory transparency`).
    """
    index = get_venues_index()
    return [
        MarketInfo(dma=label, display_count=index.display_count_by_label(label))
        for label in index.known_dmas()
    ]
