"""Hot water data model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HotWater:
    """Hot water data."""

    id: str
    is_on: bool
