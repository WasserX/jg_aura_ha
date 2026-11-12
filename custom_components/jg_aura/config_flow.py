"""Config flow for JGAura integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import os
import stat
from typing import Any

from serial.tools import list_ports
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.usb import get_serial_by_id
from homeassistant.const import CONF_DEVICE, CONF_EMAIL, CONF_HOST, CONF_PASSWORD
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.service_info.usb import UsbServiceInfo

from .const import (
    CONF_CONNECTION,
    CONF_ENABLE_HOT_WATER,
    CONF_REFRESH_RATE,
    CONNECTION_LOCAL,
    DEFAULT_API_HOST,
    DEFAULT_REFRESH_RATE,
    DOMAIN,
)
from .jg_client import JGClient
from .sal01 import SAL01Client, SAL01Error

_LOGGER = logging.getLogger(__name__)

LOCAL_TITLE = "JGAura (SAL01 USB stick)"


async def _async_cloud_errors(data: dict[str, Any]) -> dict[str, str]:
    """Return form errors for cloud credentials, empty if they work."""
    client = JGClient(
        data.get(CONF_HOST, DEFAULT_API_HOST), data[CONF_EMAIL], data[CONF_PASSWORD]
    )
    try:
        await client.get_thermostats()
    except Exception as err:
        _LOGGER.error("Failed to validate credentials: %s", err)
        return {"base": "invalid_auth"}
    return {}


def _cloud_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Return the cloud credentials form, prefilled from defaults."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_HOST, default=defaults.get(CONF_HOST, DEFAULT_API_HOST)
            ): str,
            vol.Required(CONF_EMAIL, default=defaults.get(CONF_EMAIL, "")): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(
                CONF_REFRESH_RATE,
                default=defaults.get(CONF_REFRESH_RATE, DEFAULT_REFRESH_RATE),
            ): int,
            vol.Optional(
                CONF_ENABLE_HOT_WATER,
                default=defaults.get(CONF_ENABLE_HOT_WATER, True),
            ): bool,
        }
    )


async def _async_stick_errors(port: str) -> dict[str, str]:
    """Return form errors for a SAL01 stick, empty if it answers on the port."""
    client = SAL01Client(port)
    try:
        await client.connect()
        await client.get_devices()
    except SAL01Error as err:
        _LOGGER.warning("No SAL01 stick answered on %s: %s", port, err)
        return {"base": "cannot_connect_stick"}
    finally:
        await client.close()
    return {}


def _local_data(port: str) -> dict[str, Any]:
    """Return the entry data for a stick on port."""
    return {CONF_CONNECTION: CONNECTION_LOCAL, CONF_DEVICE: port}


BY_ID = "/dev/serial/by-id"


def _stable_path(device: str, serial_number: str | None) -> str:
    """Return the /dev/serial/by-id path of a serial port, or device if there is none.

    A stick passed into a Docker container by its by-id path is a device node there,
    not a symlink, and the /dev/ttyUSBn path the system reports does not exist; so
    also match the by-id name on the USB serial number.
    """
    path = get_serial_by_id(device)
    if path != device or not serial_number or not os.path.isdir(BY_ID):
        return path
    for entry in os.scandir(BY_ID):
        if f"_{serial_number}-" in entry.name:
            return entry.path
    return device


def _list_ports() -> dict[str, str]:
    """Return serial ports as {stable path: label}, SAL01-like sticks first."""
    result: dict[str, str] = {}
    for port in list_ports.comports():
        label = f"{port.device} - {port.description}"
        if port.serial_number:
            label += f" ({port.serial_number})"
        result[_stable_path(port.device, port.serial_number)] = label
    # pyserial only finds /dev/ttyUSBn and the like, which a Docker container given
    # the by-id path alone does not have.
    if os.path.isdir(BY_ID):
        for entry in os.scandir(BY_ID):
            result.setdefault(entry.path, entry.name)
    return dict(
        sorted(result.items(), key=lambda item: "CP2104" not in item[0] + item[1])
    )


def _same_device(path: str, other: str | None) -> bool:
    """Return whether two paths are the same serial device."""
    if other is None:
        return False
    try:
        first, second = os.stat(path), os.stat(other)
    except OSError:
        return False
    return (
        stat.S_ISCHR(first.st_mode)
        and stat.S_ISCHR(second.st_mode)
        and first.st_rdev == second.st_rdev
    )


class JGAuraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for JGAura."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovered_port: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask how the thermostats are reached."""
        return self.async_show_menu(step_id="user", menu_options=["local", "cloud"])

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Set up through the JG Aura cloud."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL])
            self._abort_if_unique_id_configured()
            errors = await _async_cloud_errors(user_input)
            if not errors:
                return self.async_create_entry(
                    title=f"JGAura ({user_input[CONF_EMAIL]})", data=user_input
                )

        return self.async_show_form(
            step_id="cloud", data_schema=_cloud_schema({}), errors=errors
        )

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Set up with a SAL01 stick plugged into this machine."""
        errors: dict[str, str] = {}
        if user_input is not None:
            port = user_input[CONF_DEVICE]
            # Entries switched from the cloud keep their email as unique id.
            self._async_abort_entries_match({CONF_DEVICE: port})
            await self.async_set_unique_id(port)
            self._abort_if_unique_id_configured()
            errors = await _async_stick_errors(port)
            if not errors:
                return self.async_create_entry(
                    title=LOCAL_TITLE, data=_local_data(port)
                )

        return self.async_show_form(
            step_id="local",
            data_schema=await self._async_port_schema(),
            errors=errors,
        )

    async def async_step_usb(
        self, discovery_info: UsbServiceInfo
    ) -> config_entries.ConfigFlowResult:
        """Handle a stick found by USB discovery."""
        port = await self.hass.async_add_executor_job(
            _stable_path, discovery_info.device, discovery_info.serial_number
        )
        self._async_abort_entries_match({CONF_DEVICE: port})
        await self.async_set_unique_id(port)
        self._abort_if_unique_id_configured(updates={CONF_DEVICE: port})
        self._discovered_port = port
        self.context["title_placeholders"] = {"port": port}
        return await self.async_step_usb_confirm()

    async def async_step_usb_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm a discovered stick."""
        assert self._discovered_port is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _async_stick_errors(self._discovered_port)
            if not errors:
                return self.async_create_entry(
                    title=LOCAL_TITLE, data=_local_data(self._discovered_port)
                )

        return self.async_show_form(
            step_id="usb_confirm",
            errors=errors,
            description_placeholders={"port": self._discovered_port},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Switch an entry to (or move it between) SAL01 sticks.

        Entities keep their ids, names and history: a cloud entry switched to
        local keeps working when the cloud shuts down.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            port = user_input[CONF_DEVICE]
            if any(
                other.data.get(CONF_DEVICE) == port
                for other in self._async_current_entries()
                if other.entry_id != entry.entry_id
            ):
                return self.async_abort(reason="already_configured")
            # The running entry holds the stick open, and a second connection would
            # steal its answers: do not test a stick the entry is already using.
            in_use = entry.state is config_entries.ConfigEntryState.LOADED and (
                await self.hass.async_add_executor_job(
                    _same_device, port, entry.data.get(CONF_DEVICE)
                )
            )
            if not in_use:
                errors = await _async_stick_errors(port)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, title=LOCAL_TITLE, data=_local_data(port)
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=await self._async_port_schema(entry.data.get(CONF_DEVICE)),
            errors=errors,
        )

    async def _async_port_schema(self, current: str | None = None) -> vol.Schema:
        """Return a port picker that also accepts a typed path."""
        ports = await self.hass.async_add_executor_job(_list_ports)
        default = current or next(iter(ports), None)
        selector = SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=path, label=label)
                    for path, label in ports.items()
                ],
                custom_value=True,
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
        key = (
            vol.Required(CONF_DEVICE)
            if default is None
            else vol.Required(CONF_DEVICE, default=default)
        )
        return vol.Schema({key: selector})

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle reauth upon failed credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask for new cloud credentials."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _async_cloud_errors(user_input)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=user_input)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_cloud_schema(entry.data),
            errors=errors,
            description_placeholders={"email": entry.data.get(CONF_EMAIL)},
        )
