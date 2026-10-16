"""Config flow for Nuvo Tuner."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import SerialPortSelector
from yarl import URL

from . import DOMAIN, CONF_PORT, CONF_BAUD, CONF_TRACK, DEFAULT_BAUD, DEFAULT_TRACK

_LOGGER = logging.getLogger(__name__)

TRACK_OPTIONS = ["seek", "tune", "preset"]


def _port_title(hass: HomeAssistant, port: str) -> str:
    """Name the entry after the port, so several tuners stay distinguishable."""
    url = URL(port)
    if url.scheme == "esphome-hass":
        port_name = url.query.get("port_name")
        esphome_entry_id = url.path.lstrip("/")
        if port_name and esphome_entry_id:
            devices = dr.async_entries_for_config_entry(
                dr.async_get(hass), esphome_entry_id
            )
            device = next(
                (d for d in devices if d.primary_config_entry == esphome_entry_id),
                devices[0] if devices else None,
            )
            if device is not None:
                return f"Nuvo Tuner ({device.name_by_user or device.name} · {port_name})"
            return f"Nuvo Tuner ({port_name})"
    return "Nuvo Tuner"


def _schema(data):
    return vol.Schema({
        # Lists local serial ports and network ports such as ESPHome
        # serial proxies; manual entry still works.
        vol.Required(CONF_PORT, default=data.get(CONF_PORT, vol.UNDEFINED)):
            SerialPortSelector(),
        vol.Optional(CONF_BAUD, default=data.get(CONF_BAUD, DEFAULT_BAUD)): str,
        vol.Optional(CONF_TRACK, default=data.get(CONF_TRACK, DEFAULT_TRACK)):
            vol.In(TRACK_OPTIONS),
    })


async def _async_probe(hass: HomeAssistant, port: str, baud) -> None:
    """Open and close the port; don't start the driver's background threads."""
    import serialx

    handle = serialx.serial_for_url(port, baudrate=int(baud), read_timeout=1)
    await hass.async_add_executor_job(handle.open)
    await hass.async_add_executor_job(handle.close)


class NuvoTunerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry):
        return NuvoTunerOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Strip accidental "port: " prefix if user copy-pasted from YAML
            user_input[CONF_PORT] = user_input[CONF_PORT].strip()
            if user_input[CONF_PORT].lower().startswith("port:"):
                user_input[CONF_PORT] = user_input[CONF_PORT].split(":", 1)[1].strip()
            try:
                await _async_probe(self.hass, user_input[CONF_PORT],
                                   user_input.get(CONF_BAUD, DEFAULT_BAUD))
                await self.async_set_unique_id(user_input[CONF_PORT])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_port_title(self.hass, user_input[CONF_PORT]),
                    data=user_input,
                )
            except Exception:
                _LOGGER.exception("Error connecting to Nuvo Tuner")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}),
            errors=errors,
        )


class NuvoTunerOptionsFlowHandler(config_entries.OptionsFlow):
    """Change the port (e.g. move the tuner onto a network port) without re-adding."""

    def __init__(self, config_entry):
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        errors = {}
        current = {**self._entry.data, **self._entry.options}

        if user_input is not None:
            port = user_input[CONF_PORT].strip()
            user_input[CONF_PORT] = port
            try:
                # Only probe a NEW port: this entry holds its current one open,
                # and serialx opens ports exclusively, so probing it would
                # always fail.
                if port != current[CONF_PORT]:
                    await _async_probe(self.hass, port,
                                       user_input.get(CONF_BAUD, DEFAULT_BAUD))
            except Exception:
                _LOGGER.exception("Error connecting to Nuvo Tuner")
                errors["base"] = "cannot_connect"
            else:
                # Follow the port in the title unless the user renamed the entry
                if port != current[CONF_PORT] and self._entry.title == _port_title(
                    self.hass, current[CONF_PORT]
                ):
                    self.hass.config_entries.async_update_entry(
                        self._entry, title=_port_title(self.hass, port)
                    )
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_schema(user_input or current),
            errors=errors,
        )
