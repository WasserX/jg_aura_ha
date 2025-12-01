"""JGAura integration for Home Assistant."""
from typing import Final

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_HOST, Platform
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, CONF_REFRESH_RATE, CONF_ENABLE_HOT_WATER

PLATFORMS: Final = [Platform.CLIMATE, Platform.SWITCH]

CONFIG_SCHEMA = vol.Schema(
	{
		DOMAIN: vol.Schema({
			vol.Required(CONF_HOST): cv.string,
			vol.Required(CONF_EMAIL): cv.string,
			vol.Required(CONF_PASSWORD): cv.string,
			vol.Optional(CONF_ENABLE_HOT_WATER, default=True): cv.boolean,
			vol.Optional(CONF_REFRESH_RATE, default=30) : cv.positive_int
		})
	},
	extra = vol.ALLOW_EXTRA
)


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
