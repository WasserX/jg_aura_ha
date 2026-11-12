"""Diagnostics for JGAura."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import JGAuraConfigEntry
from .local_client import LocalClient

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: JGAuraConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data: dict[str, Any] = {"entry": async_redact_data(dict(entry.data), TO_REDACT)}
    client = entry.runtime_data
    if isinstance(client, LocalClient):
        data["thermostats"] = {
            status.cloud_id: {
                "mode": status.mode.name,
                "heating": status.heating,
                "current_temperature": status.current_temperature,
                "target_temperature": status.target_temperature,
                "raw": status.raw.decode("latin-1"),
            }
            for status in client.statuses.values()
        }
        data["gateway"] = asdict(client.gateway())
    return data
