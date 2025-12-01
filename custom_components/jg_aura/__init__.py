"""JGAura integration for Home Assistant."""
from typing import Final

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, CONF_ENABLE_HOT_WATER

PLATFORMS: Final = [Platform.CLIMATE, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Set up JGAura from a config entry."""
	hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry.data

	await hass.config_entries.async_forward_entry_setups(
		entry,
		[Platform.CLIMATE, Platform.SWITCH] if entry.data.get(CONF_ENABLE_HOT_WATER, True) else [Platform.CLIMATE]
	)

	return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Unload a config entry."""
	platforms = [Platform.CLIMATE, Platform.SWITCH] if entry.data.get(CONF_ENABLE_HOT_WATER, True) else [Platform.CLIMATE]
	result = await hass.config_entries.async_unload_platforms(entry, platforms)

	if result:
		hass.data[DOMAIN].pop(entry.entry_id)

	return result
