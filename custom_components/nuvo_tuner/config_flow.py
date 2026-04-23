"""Config flow for Nuvo Tuner."""
import logging
import voluptuous as vol
from homeassistant import config_entries

from . import DOMAIN, CONF_PORT, CONF_BAUD, CONF_TRACK, DEFAULT_BAUD, DEFAULT_TRACK

_LOGGER = logging.getLogger(__name__)

TRACK_OPTIONS = ["seek", "tune", "preset"]


class NuvoTunerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Strip accidental "port: " prefix if user copy-pasted from YAML
            user_input[CONF_PORT] = user_input[CONF_PORT].strip()
            if user_input[CONF_PORT].lower().startswith("port:"):
                user_input[CONF_PORT] = user_input[CONF_PORT].split(":", 1)[1].strip()
            try:
                # Just verify the port opens — don't start the library's background threads
                import serial
                port = serial.serial_for_url(user_input[CONF_PORT], do_not_open=True)
                port.baudrate = int(user_input.get(CONF_BAUD, DEFAULT_BAUD))
                await self.hass.async_add_executor_job(port.open)
                await self.hass.async_add_executor_job(port.close)
                await self.async_set_unique_id(user_input[CONF_PORT])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Nuvo Tuner", data=user_input)
            except Exception:
                _LOGGER.exception("Error connecting to Nuvo Tuner")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_PORT, default="/dev/ttyUSB0"): str,
                vol.Optional(CONF_BAUD, default=DEFAULT_BAUD): str,
                vol.Optional(CONF_TRACK, default=DEFAULT_TRACK): vol.In(TRACK_OPTIONS),
            }),
            errors=errors,
        )
