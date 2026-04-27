"""Publisher inventory index — backs DMA targeting.

Source: `backend/data/venues.json`, a flattened export of the demo publisher's
Mongo `screens` ⋈ `companies` collections. Each row: `{device_id, venue_id,
dma, venue_name}`. Loaded once at startup and cached for the process lifetime
— inventory snapshots don't change inside a server run, and refreshing across
runs just means redeploying the backend.

The Mongo `market` codes are short lowercase ('sf', 'ny', …); we expose them
to the dashboard as canonical display labels ('San Francisco', 'New York', …).
The map below is the single source of truth for the UI strings.

Rows with empty `dma` are filtered out at load time — the export contains
~10 admin/test screens (e.g. 'root', 'shaw') with no market assigned.
"""
from __future__ import annotations

import json
import logging
import random
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# Canonical demo market list. Keys are the Mongo codes, values the
# display labels surfaced in `/api/markets` and the wizard. Demo publisher
# operates in exactly these 6 DMAs — anything else in the export is treated
# as an unknown code and skipped (with a warning).
DMA_LABELS: dict[str, str] = {
    "ny": "New York",
    "la": "Los Angeles",
    "sf": "San Francisco",
    "mia": "Miami",
    "bos": "Boston",
    "aus": "Austin",
}


# Default location: backend/data/venues.json. Relative to the repo root the
# container `WORKDIR` (`/app`) puts us at `data/venues.json`. Tests can
# override by passing a different path to `_load_venues`.
DEFAULT_VENUES_PATH = Path("data/venues.json")


class VenuesIndex:
    """In-memory inventory lookup. Built once, read many times.

    `dma_to_devices` and `device_to_dma` are the two indexes /bid + auto-play
    use. `display_counts` powers the wizard's REACH calculation and the
    `GET /api/markets` response.
    """

    def __init__(
        self,
        dma_to_devices: dict[str, list[str]],
        device_to_dma: dict[str, str],
        display_counts: dict[str, int],
        venue_names: dict[str, str],
    ) -> None:
        self.dma_to_devices = dma_to_devices
        self.device_to_dma = device_to_dma
        self.display_counts = display_counts
        self.venue_names = venue_names

    def known_dmas(self) -> list[str]:
        """Canonical labels in a stable order matching DMA_LABELS."""
        return [
            label
            for code, label in DMA_LABELS.items()
            if code in self.display_counts and self.display_counts[code] > 0
        ]

    def display_count_by_label(self, label: str) -> int:
        for code, l in DMA_LABELS.items():
            if l == label:
                return self.display_counts.get(code, 0)
        return 0

    def label_for_device(self, device_id: str) -> str | None:
        code = self.device_to_dma.get(device_id)
        return DMA_LABELS.get(code) if code else None

    def devices_for_labels(self, labels: list[str]) -> list[str]:
        codes = {code for code, l in DMA_LABELS.items() if l in labels}
        out: list[str] = []
        for code in codes:
            out.extend(self.dma_to_devices.get(code, []))
        return out

    def pick_random_device(self, labels: list[str]) -> dict[str, str] | None:
        """Random device drawn uniformly across all DMAs in `labels`.

        Used by auto-play + simulate-play to emit a settlement that respects
        the campaign's targeting. Returns `{device_id, venue_name, dma}` or
        None if no labels resolve to any device.
        """
        devices = self.devices_for_labels(labels)
        if not devices:
            return None
        device_id = random.choice(devices)
        return {
            "device_id": device_id,
            "venue_name": self.venue_names.get(device_id, ""),
            "dma": self.label_for_device(device_id) or "",
        }


def _load_venues(path: Path) -> VenuesIndex:
    if not path.exists():
        logger.warning(
            "venues file not found at %s — DMA targeting will reject all bids",
            path,
        )
        return VenuesIndex({}, {}, {}, {})

    raw = json.loads(path.read_text(encoding="utf-8"))

    dma_to_devices: dict[str, list[str]] = defaultdict(list)
    device_to_dma: dict[str, str] = {}
    display_counts: dict[str, int] = defaultdict(int)
    venue_names: dict[str, str] = {}
    skipped_no_dma = 0
    skipped_unknown_dma = 0

    for row in raw:
        device_id = row.get("device_id")
        dma = (row.get("dma") or "").strip().lower()
        venue_name = row.get("venue_name") or ""
        if not device_id:
            continue
        if not dma:
            skipped_no_dma += 1
            continue
        if dma not in DMA_LABELS:
            skipped_unknown_dma += 1
            continue
        dma_to_devices[dma].append(device_id)
        device_to_dma[device_id] = dma
        display_counts[dma] += 1
        venue_names[device_id] = venue_name

    logger.info(
        "venues loaded: %d devices across %d DMAs (skipped: %d empty-dma, %d unknown-dma)",
        len(device_to_dma),
        len(display_counts),
        skipped_no_dma,
        skipped_unknown_dma,
    )
    return VenuesIndex(
        dma_to_devices=dict(dma_to_devices),
        device_to_dma=device_to_dma,
        display_counts=dict(display_counts),
        venue_names=venue_names,
    )


@lru_cache(maxsize=1)
def get_venues_index() -> VenuesIndex:
    return _load_venues(DEFAULT_VENUES_PATH)
