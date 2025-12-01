"""Config flow for JGAura integration."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_HOST

from .const import DOMAIN, CONF_REFRESH_RATE, CONF_ENABLE_HOT_WATER

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Required(CONF_EMAIL): str,
    vol.Required(CONF_PASSWORD): str,
    vol.Optional(CONF_REFRESH_RATE, default=30): int,
    vol.Optional(CONF_ENABLE_HOT_WATER, default=True): bool,
})


class JGAuraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for JGAura."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL])
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"JGAura ({user_input[CONF_EMAIL]})",
                data=user_input,
            )

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)
