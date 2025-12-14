"""Thermostat data model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Thermostat:
    """Thermostat data."""

    id: str
    name: str
    on: bool
    state_name: str
    temp_current: float
    temp_set_point: float
