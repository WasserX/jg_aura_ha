"""Tests for the integration running on a SAL01 stick."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import time
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    ATTR_TEMPERATURE,
    CONF_DEVICE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import DOWNSTAIRS_BATHROOM, PORT, FakeSAL01
from custom_components.jg_aura import local_client
from custom_components.jg_aura.const import CONF_CONNECTION, CONNECTION_LOCAL, DOMAIN
from custom_components.jg_aura.diagnostics import async_get_config_entry_diagnostics
from custom_components.jg_aura.sal01 import Mode, Preset


def local_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="JGAura (SAL01 USB stick)",
        unique_id=PORT,
        data={CONF_CONNECTION: CONNECTION_LOCAL, CONF_DEVICE: PORT},
    )


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_creates_thermostats(
    hass: HomeAssistant, fake_stick: type[FakeSAL01]
) -> None:
    entry = local_entry()
    await setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get("climate.thermostat_bea0")
    assert state is not None
    assert state.attributes[ATTR_PRESET_MODE] == "Frost"
    assert state.attributes["current_temperature"] == 18.5
    assert state.attributes[ATTR_TEMPERATURE] == 5.0
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.IDLE
    assert hass.states.get("climate.thermostat_b7b0") is not None
    # Startup syncs the clocks, tells the thermostats a gateway is online and asks
    # them all to report.
    assert fake_stick.instances[0].commands == [("refresh",), ("online",), ("report",)]


async def test_names_and_ids_survive_switch_from_cloud(
    hass: HomeAssistant, fake_stick: type[FakeSAL01], entity_registry: er.EntityRegistry
) -> None:
    entry = local_entry()
    entry.add_to_hass(hass)
    # As left behind by the cloud version of the same entry.
    entity_registry.async_get_or_create(
        CLIMATE_DOMAIN,
        DOMAIN,
        "jg_aura_bea0",
        config_entry=entry,
        suggested_object_id="downstairs_bathroom",
        original_name="Downstairs bathroom",
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("climate.downstairs_bathroom")
    assert state is not None
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Downstairs bathroom"


async def test_push_update(hass: HomeAssistant, fake_stick: type[FakeSAL01]) -> None:
    await setup(hass, local_entry())

    fake_stick.instances[0].report(
        replace(
            DOWNSTAIRS_BATHROOM, mode=Mode.LOW, heating=True, target_temperature=20.0
        )
    )
    await hass.async_block_till_done()

    state = hass.states.get("climate.thermostat_bea0")
    assert state.attributes[ATTR_PRESET_MODE] == "Low"
    assert state.attributes[ATTR_TEMPERATURE] == 20.0
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING


async def test_set_preset_and_temperature(
    hass: HomeAssistant, fake_stick: type[FakeSAL01]
) -> None:
    await setup(hass, local_entry())

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: "climate.thermostat_bea0", ATTR_PRESET_MODE: "Medium"},
        blocking=True,
    )
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: "climate.thermostat_bea0", ATTR_TEMPERATURE: 19.5},
        blocking=True,
    )

    commands = fake_stick.instances[0].commands
    assert ("preset", 0xA0BE, Preset.MEDIUM) in commands
    assert ("temperature", 0xA0BE, 19.5) in commands


async def test_stick_missing_retries_later(
    hass: HomeAssistant, fake_stick: type[FakeSAL01]
) -> None:
    fake_stick.fail_connect = True
    entry = local_entry()
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unplugged_stick_reloads_entry(
    hass: HomeAssistant, fake_stick: type[FakeSAL01]
) -> None:
    entry = local_entry()
    await setup(hass, entry)

    fake_stick.instances[0].lose_connection()
    await hass.async_block_till_done()

    assert len(fake_stick.instances) == 2
    assert entry.state is ConfigEntryState.LOADED


async def test_unload_closes_stick_without_reloading(
    hass: HomeAssistant, fake_stick: type[FakeSAL01]
) -> None:
    entry = local_entry()
    await setup(hass, entry)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not fake_stick.instances[0].connected
    assert len(fake_stick.instances) == 1


async def test_time_sync_uses_home_assistant_time_zone(
    hass: HomeAssistant, fake_stick: type[FakeSAL01]
) -> None:
    # The host's own time zone (UTC in most containers) must not matter.
    await hass.config.async_set_time_zone("Asia/Kolkata")
    await setup(hass, local_entry())
    synced_at = fake_stick.instances[0].synced_at
    assert synced_at.utcoffset() == timedelta(hours=5, minutes=30)


async def test_maintenance_keeps_thermostats_in_touch(
    hass: HomeAssistant, fake_stick: type[FakeSAL01]
) -> None:
    await setup(hass, local_entry())
    stick = fake_stick.instances[0]
    stick.commands.clear()

    async_fire_time_changed(hass, dt_util.utcnow() + local_client.MAINTENANCE_INTERVAL)
    await hass.async_block_till_done()
    assert stick.commands == [("online",)]

    stick.commands.clear()
    later = time.monotonic() + local_client.SYNC_INTERVAL_SECONDS + 1
    with patch.object(local_client.time, "monotonic", return_value=later):
        async_fire_time_changed(
            hass, dt_util.utcnow() + 2 * local_client.MAINTENANCE_INTERVAL
        )
        await hass.async_block_till_done()
    assert stick.commands == [("online",), ("refresh",)]


async def test_diagnostics(hass: HomeAssistant, fake_stick: type[FakeSAL01]) -> None:
    entry = local_entry()
    await setup(hass, entry)
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data["entry"] == {CONF_CONNECTION: CONNECTION_LOCAL, CONF_DEVICE: PORT}
    assert data["thermostats"]["bea0"]["mode"] == "FROST"
    assert len(data["gateway"]["thermostats"]) == 2


async def test_failed_setup_closes_stick(
    hass: HomeAssistant, fake_stick: type[FakeSAL01]
) -> None:
    entry = local_entry()
    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        side_effect=RuntimeError("platform failed"),
    ):
        await setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert not fake_stick.instances[0].connected
