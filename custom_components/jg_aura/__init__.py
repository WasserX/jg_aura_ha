"""JGAura integration for Home Assistant."""

from __future__ import annotations

from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_ENABLE_HOT_WATER
from .jg_client import JGClient

type JGAuraConfigEntry = ConfigEntry[JGClient]

PLATFORMS: Final = [Platform.CLIMATE, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: JGAuraConfigEntry) -> bool:
    """Set up JGAura from a config entry."""
    client = JGClient(
        entry.data["host"],
        entry.data["email"],
        entry.data["password"],
    )
    entry.runtime_data = client

    platforms_to_setup = PLATFORMS
    if not entry.data.get(CONF_ENABLE_HOT_WATER, True):
        platforms_to_setup = [Platform.CLIMATE]

    await hass.config_entries.async_forward_entry_setups(entry, platforms_to_setup)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: JGAuraConfigEntry) -> bool:
    """Unload a config entry."""
    platforms_to_unload = PLATFORMS
    if not entry.data.get(CONF_ENABLE_HOT_WATER, True):
        platforms_to_unload = [Platform.CLIMATE]

    return await hass.config_entries.async_unload_platforms(entry, platforms_to_unload)
