"""Switch platform for JGAura integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from . import jg_client
from .__init__ import JGAuraConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JGAuraConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform from a config entry."""
    client = entry.runtime_data

    async def async_update_data() -> jg_client.hotwater.HotWater:
        """Update data from the API."""
        try:
            return await client.get_hot_water()
        except Exception as err:
            raise UpdateFailed(f"Failed to update hot water data: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="switch",
        update_method=async_update_data,
        update_interval=timedelta(seconds=60),
        config_entry=entry,
    )

    await coordinator.async_config_entry_first_refresh()

    hot_water_switch = HotWaterSwitch(coordinator, client, coordinator.data)

    def update_entities() -> None:
        """Update all entities when coordinator updates."""
        hot_water_switch.set_state(coordinator.data.is_on)
        hot_water_switch.async_write_ha_state()

    coordinator.async_add_listener(update_entities)

    async_add_entities([hot_water_switch])


class HotWaterSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a hot water switch."""

    _attr_has_entity_name = True
    _attr_name = "Hot water"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        client: jg_client.JGClient,
        hot_water: jg_client.hotwater.HotWater,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._client = client
        self._is_on = hot_water.is_on
        self._attr_unique_id = f"jg_aura_hot_water_{hot_water.id}"

    @property
    def is_on(self) -> bool:
        """Return whether the hot water is on."""
        return self._is_on

    def set_state(self, is_on: bool) -> None:
        """Set the state of the hot water."""
        self._is_on = is_on

    async def async_turn_on(self, **kwargs: dict) -> None:
        """Turn on the hot water."""
        hot_water_id = self.coordinator.data.id
        await self._client.set_hot_water(hot_water_id, True)
        self._is_on = True
        self.async_write_ha_state()

        await asyncio.sleep(jg_client.API_DELAY_SECONDS)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: dict) -> None:
        """Turn off the hot water."""
        hot_water_id = self.coordinator.data.id
        await self._client.set_hot_water(hot_water_id, False)
        self._is_on = False
        self.async_write_ha_state()

        await asyncio.sleep(jg_client.API_DELAY_SECONDS)
        await self.coordinator.async_request_refresh()
