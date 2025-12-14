"""Config flow for JGAura integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_ENABLE_HOT_WATER,
    CONF_REFRESH_RATE,
    DEFAULT_API_HOST,
    DEFAULT_REFRESH_RATE,
    DOMAIN,
)
from .jg_client import JGClient

_LOGGER = logging.getLogger(__name__)


class InvalidAuthError(HomeAssistantError):
    """Error to indicate there is invalid auth."""


async def _async_validate_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    client = JGClient(
        data.get(CONF_HOST, DEFAULT_API_HOST),
        data[CONF_EMAIL],
        data[CONF_PASSWORD],
    )

    try:
        await client.get_thermostats()
    except Exception as err:
        _LOGGER.error("Failed to validate credentials: %s", err)
        raise InvalidAuthError(f"Invalid credentials: {err}") from err

    return {"title": f"JGAura ({data[CONF_EMAIL]})"}


class JGAuraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for JGAura."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL])
            self._abort_if_unique_id_configured()

            try:
                info = await _async_validate_input(self.hass, user_input)
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during credential validation")
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_HOST, default=DEFAULT_API_HOST): str,
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_REFRESH_RATE, default=DEFAULT_REFRESH_RATE): int,
                vol.Optional(CONF_ENABLE_HOT_WATER, default=True): bool,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle reauth upon failed credentials."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _async_validate_input(self.hass, user_input)
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during reauth validation")
                errors["base"] = "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(entry, data=user_input)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort_flow(reason="reauth_successful")

        current_data = entry.data
        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_HOST, default=current_data.get(CONF_HOST, DEFAULT_API_HOST)
                ): str,
                vol.Required(CONF_EMAIL, default=current_data.get(CONF_EMAIL)): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(
                    CONF_REFRESH_RATE,
                    default=current_data.get(CONF_REFRESH_RATE, DEFAULT_REFRESH_RATE),
                ): int,
                vol.Optional(
                    CONF_ENABLE_HOT_WATER,
                    default=current_data.get(CONF_ENABLE_HOT_WATER, True),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="reauth",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"email": current_data.get(CONF_EMAIL)},
        )
