"""Config flow for JGAura integration."""

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_ENABLE_HOT_WATER, CONF_REFRESH_RATE, DOMAIN
from .jg_client import JGClient


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


_LOGGER = logging.getLogger(__name__)

DEFAULT_HOST = "https://emea-salprod02-api.arrayent.com:8081/zdk/services/zamapi"


async def _async_validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    client = JGClient(data["host"], data["email"], data["password"])

    try:
        # Try to fetch thermostats to validate credentials
        await client.GetThermostats()
    except Exception as err:
        _LOGGER.error(f"Failed to validate credentials: {err}")
        raise InvalidAuth(f"Invalid credentials: {err}") from err

    return {"title": f"JGAura ({data['email']})"}


class JGAuraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for JGAura."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Check if email is already configured
            await self.async_set_unique_id(user_input["email"])
            self._abort_if_unique_id_configured()

            # Validate credentials
            try:
                info = await _async_validate_input(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during credential validation")
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required("host", default=DEFAULT_HOST): str,
                vol.Required("email"): str,
                vol.Required("password"): str,
                vol.Optional("refresh_rate", default=60): int,
                vol.Optional("hot_water", default=True): bool,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_reauth(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Handle reauth upon failed credentials."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors = {}

        if user_input is not None:
            # Validate new credentials
            try:
                info = await _async_validate_input(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during reauth validation")
                errors["base"] = "cannot_connect"
            else:
                # Update the entry with new credentials
                self.hass.config_entries.async_update_entry(
                    entry, data=user_input
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort_flow(reason="reauth_successful")

        # Pre-fill with current email and host
        current_data = entry.data
        data_schema = vol.Schema(
            {
                vol.Required("host", default=current_data.get("host", DEFAULT_HOST)): str,
                vol.Required("email", default=current_data.get("email")): str,
                vol.Required("password"): str,
                vol.Optional("refresh_rate", default=current_data.get("refresh_rate", 60)): int,
                vol.Optional("hot_water", default=current_data.get("hot_water", True)): bool,
            }
        )

        return self.async_show_form(
            step_id="reauth", data_schema=data_schema, errors=errors, description_placeholders={"email": current_data.get("email")}
        )
