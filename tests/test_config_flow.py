"""Tests for the JGAura config flow."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_USB, SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_DEVICE, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.usb import UsbServiceInfo

from .conftest import PORT
from custom_components.jg_aura import config_flow
from custom_components.jg_aura.const import CONF_CONNECTION, CONNECTION_LOCAL, DOMAIN

FLOW = "custom_components.jg_aura.config_flow"
USB_DISCOVERY = UsbServiceInfo(
    device="/dev/ttyUSB0",
    vid="10C4",
    pid="EA60",
    serial_number="014E32FB",
    manufacturer="Silicon Labs",
    description="CP2104 USB to UART Bridge Controller",
)


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    with patch("custom_components.jg_aura.async_setup_entry", return_value=True) as m:
        yield m


@pytest.fixture
def mock_ports() -> Generator[None]:
    with patch(
        f"{FLOW}._list_ports",
        return_value={PORT: "/dev/ttyUSB0 - CP2104 USB to UART Bridge Controller"},
    ):
        yield


@pytest.fixture
def mock_validate() -> Generator[AsyncMock]:
    with patch(f"{FLOW}._async_stick_errors", return_value={}) as m:
        yield m


async def test_user_step_offers_local_and_cloud(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["local", "cloud"]


async def test_local_setup(
    hass: HomeAssistant,
    mock_ports: None,
    mock_validate: AsyncMock,
    mock_setup_entry: AsyncMock,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "local"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "local"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: PORT}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_CONNECTION: CONNECTION_LOCAL, CONF_DEVICE: PORT}
    assert result["result"].unique_id == PORT
    mock_validate.assert_awaited_once_with(PORT)


async def test_local_setup_stick_not_answering(
    hass: HomeAssistant,
    mock_ports: None,
    mock_validate: AsyncMock,
    mock_setup_entry: AsyncMock,
) -> None:
    mock_validate.return_value = {"base": "cannot_connect_stick"}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "local"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: PORT}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect_stick"}

    # Plugged in properly now.
    mock_validate.return_value = {}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: PORT}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_usb_discovery(
    hass: HomeAssistant, mock_validate: AsyncMock, mock_setup_entry: AsyncMock
) -> None:
    with patch(f"{FLOW}.get_serial_by_id", return_value=PORT):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USB}, data=USB_DISCOVERY
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "usb_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_CONNECTION: CONNECTION_LOCAL, CONF_DEVICE: PORT}


async def test_reconfigure_cloud_entry_to_local(
    hass: HomeAssistant,
    mock_ports: None,
    mock_validate: AsyncMock,
    mock_setup_entry: AsyncMock,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="me@example.com",
        data={CONF_EMAIL: "me@example.com", CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: PORT}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    # Same entry, so the entities keep their ids; the cloud password is dropped.
    assert entry.data == {CONF_CONNECTION: CONNECTION_LOCAL, CONF_DEVICE: PORT}


async def test_usb_discovery_ignores_stick_of_switched_cloud_entry(
    hass: HomeAssistant, mock_validate: AsyncMock
) -> None:
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="me@example.com",
        data={CONF_CONNECTION: CONNECTION_LOCAL, CONF_DEVICE: PORT},
    ).add_to_hass(hass)
    with patch(f"{FLOW}.get_serial_by_id", return_value=PORT):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USB}, data=USB_DISCOVERY
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_refuses_stick_of_another_entry(
    hass: HomeAssistant, mock_ports: None, mock_validate: AsyncMock
) -> None:
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=PORT,
        data={CONF_CONNECTION: CONNECTION_LOCAL, CONF_DEVICE: PORT},
    ).add_to_hass(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="me@example.com",
        data={CONF_EMAIL: "me@example.com", CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: PORT}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_validate.assert_not_awaited()


def test_stable_path_matches_docker_device_node_by_serial(tmp_path) -> None:
    # In Docker the by-id path is a device node, not a symlink to /dev/ttyUSB1.
    node = (
        tmp_path
        / "usb-Silicon_Labs_CP2104_USB_to_UART_Bridge_Controller_014E32FB-if00-port0"
    )
    node.touch()
    with (
        patch(f"{FLOW}.BY_ID", str(tmp_path)),
        patch(f"{FLOW}.get_serial_by_id", side_effect=lambda device: device),
    ):
        assert config_flow._stable_path("/dev/ttyUSB1", "014E32FB") == str(node)
        assert config_flow._stable_path("/dev/ttyUSB0", "ABCDEF01") == "/dev/ttyUSB0"


async def test_reconfigure_onto_the_stick_in_use_skips_the_check(
    hass: HomeAssistant,
    mock_ports: None,
    mock_validate: AsyncMock,
    mock_setup_entry: AsyncMock,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="me@example.com",
        data={CONF_CONNECTION: CONNECTION_LOCAL, CONF_DEVICE: "/dev/ttyUSB1"},
        state=ConfigEntryState.LOADED,
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    with patch(f"{FLOW}._same_device", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE: PORT}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_DEVICE] == PORT
    mock_validate.assert_not_awaited()


def test_list_ports_includes_by_id_paths_pyserial_misses(tmp_path) -> None:
    node = (
        tmp_path
        / "usb-Silicon_Labs_CP2104_USB_to_UART_Bridge_Controller_014E32FB-if00-port0"
    )
    node.touch()
    with (
        patch(f"{FLOW}.BY_ID", str(tmp_path)),
        patch(f"{FLOW}.list_ports.comports", return_value=[]),
    ):
        assert config_flow._list_ports() == {str(node): node.name}
