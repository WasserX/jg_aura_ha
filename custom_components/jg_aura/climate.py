"""Climate platform for JGAura integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any, ClassVar

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from . import jg_client, thermostat
from .__init__ import JGAuraConfigEntry
from .const import CONF_REFRESH_RATE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JGAuraConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the climate platform from a config entry."""
    client = entry.runtime_data
    refresh_rate = entry.data.get(CONF_REFRESH_RATE, 30)

    thermostat_entities: list[JGAuraThermostat] = []

    async def async_update_data() -> jg_client.gateway.Gateway:
        """Update data from the API."""
        try:
            return await client.get_thermostats()
        except Exception as err:
            raise UpdateFailed(f"Failed to update thermostat data: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="climate",
        update_method=async_update_data,
        update_interval=timedelta(seconds=refresh_rate),
        config_entry=entry,
    )

    await coordinator.async_config_entry_first_refresh()

    def update_entities() -> None:
        """Update all entities when coordinator updates."""
        for entity in thermostat_entities:
            for therm in coordinator.data.thermostats:
                if therm.id == entity.id:
                    entity.set_values(therm)
                    entity.async_write_ha_state()

    coordinator.async_add_listener(update_entities)

    for therm in coordinator.data.thermostats:
        entity = JGAuraThermostat(
            coordinator, client, coordinator.data.id, therm.id, therm.name, therm.on
        )
        entity.set_values(therm)
        thermostat_entities.append(entity)

    async_add_entities(thermostat_entities)


class JGAuraThermostat(CoordinatorEntity, ClimateEntity):
    """Representation of a JGAura thermostat."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:thermometer"
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5
    _attr_max_temp = 35
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes: ClassVar = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features: ClassVar = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        client: jg_client.JGClient,
        gateway_id: str,
        device_id: str,
        name: str,
        is_on: bool,
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator)
        self._client = client
        self._gateway_id = gateway_id
        self._id = device_id
        self._attr_name = name
        self._attr_unique_id = f"jg_aura_{device_id}"

        self._current_temp: float | None = None
        self._target_temp: float | None = None
        self._preset_mode: str = "Low"
        self._hvac_mode = HVACMode.HEAT
        self._hvac_action = HVACAction.HEATING if is_on else HVACAction.IDLE

    @property
    def id(self) -> str:
        """Return the thermostat ID."""
        return self._id

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._current_temp

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._target_temp

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        return self._hvac_mode

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current HVAC action."""
        return self._hvac_action

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        return self._preset_mode

    @property
    def preset_modes(self) -> list[str]:
        """Return the available preset modes."""
        return jg_client.RUN_MODES

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        self._target_temp = temperature
        await self._client.set_thermostat_temperature(self._id, temperature)
        self.async_write_ha_state()

        await asyncio.sleep(jg_client.API_DELAY_SECONDS)
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        self._preset_mode = preset_mode
        await self._client.set_thermostat_preset(self._id, preset_mode)
        self.async_write_ha_state()

        await asyncio.sleep(jg_client.API_DELAY_SECONDS)
        await self.coordinator.async_request_refresh()

    def set_values(self, therm: thermostat.Thermostat) -> None:
        """Update entity values from thermostat data."""
        self._current_temp = therm.temp_current
        self._target_temp = therm.temp_set_point
        self._preset_mode = therm.state_name
        self._hvac_mode = (
            HVACMode.HEAT
            if self._preset_mode in jg_client.HEATING_MODES
            else HVACMode.OFF
        )
        self._hvac_action = HVACAction.HEATING if therm.on else HVACAction.IDLE
