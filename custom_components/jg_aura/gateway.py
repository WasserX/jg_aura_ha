"""Gateway data model."""

from __future__ import annotations

from dataclasses import dataclass

from .thermostat import Thermostat


@dataclass
class Gateway:
    """Gateway data."""

    id: str
    name: str
    thermostats: list[Thermostat]
