"""JGAura integration for Home Assistant."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_CONNECTION,
    CONF_ENABLE_HOT_WATER,
    CONNECTION_CLOUD,
    CONNECTION_LOCAL,
    DOMAIN,
)
from .jg_client import JGClient
from .local_client import MAINTENANCE_INTERVAL, LocalClient
from .sal01 import SAL01Error

_LOGGER = logging.getLogger(__name__)

type JGAuraConfigEntry = ConfigEntry[JGClient | LocalClient]

PLATFORMS: Final = [Platform.CLIMATE, Platform.SWITCH]


def _is_local(entry: JGAuraConfigEntry) -> bool:
    """Return whether an entry uses a SAL01 stick (entries without the key are cloud)."""
    return entry.data.get(CONF_CONNECTION, CONNECTION_CLOUD) == CONNECTION_LOCAL


def _platforms(entry: JGAuraConfigEntry) -> list[Platform]:
    """Return the platforms of an entry; hot water is cloud only."""
    if _is_local(entry) or not entry.data.get(CONF_ENABLE_HOT_WATER, True):
        return [Platform.CLIMATE]
    return PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: JGAuraConfigEntry) -> bool:
    """Set up JGAura from a config entry."""
    if _is_local(entry):
        client: JGClient | LocalClient = await _async_setup_local(hass, entry)
    else:
        client = JGClient(
            entry.data["host"],
            entry.data["email"],
            entry.data["password"],
        )
    entry.runtime_data = client

    await hass.config_entries.async_forward_entry_setups(entry, _platforms(entry))

    return True


async def _async_setup_local(
    hass: HomeAssistant, entry: JGAuraConfigEntry
) -> LocalClient:
    """Open the SAL01 stick, keep the thermostats in touch, reload if it goes away."""
    client = LocalClient(entry.data[CONF_DEVICE], _known_names(hass, entry))
    try:
        await client.connect()
    except SAL01Error as err:
        raise ConfigEntryNotReady(
            f"Cannot use the SAL01 stick at {client.port}: {err}"
        ) from err

    entry.async_on_unload(client.close)

    @callback
    def _on_disconnect() -> None:
        hass.config_entries.async_schedule_reload(entry.entry_id)

    async def _async_maintain(_now: datetime) -> None:
        try:
            await client.maintain()
        except SAL01Error as err:
            _LOGGER.warning(
                "Could not reach the thermostats through the stick: %s", err
            )

    entry.async_on_unload(client.on_disconnect(_on_disconnect))
    entry.async_on_unload(
        async_track_time_interval(hass, _async_maintain, MAINTENANCE_INTERVAL)
    )
    return client


def _known_names(hass: HomeAssistant, entry: JGAuraConfigEntry) -> dict[str, str]:
    """Return thermostat names from the entity registry, by cloud id.

    The stick does not know thermostat names. Entities created while the entry
    used the cloud keep their names when the entry is switched to local.
    """
    names = {}
    prefix = f"{DOMAIN}_"
    for entity in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if entity.unique_id.startswith(prefix) and entity.original_name:
            names[entity.unique_id.removeprefix(prefix)] = entity.original_name
    return names


async def async_unload_entry(hass: HomeAssistant, entry: JGAuraConfigEntry) -> bool:
    """Unload a config entry; the stick is closed by an on_unload callback."""
    return await hass.config_entries.async_unload_platforms(entry, _platforms(entry))
