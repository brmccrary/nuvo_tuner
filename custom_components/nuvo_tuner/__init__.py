"""The nuvo_tuner component."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from serial import SerialException
from nuvo_tuner import get_nuvo

_LOGGER = logging.getLogger(__name__)

DOMAIN = "nuvo_tuner"
PLATFORMS = [Platform.MEDIA_PLAYER]

CONF_PORT = "port"
CONF_BAUD = "baud"
CONF_TRACK = "track"
DEFAULT_BAUD = "57600"
DEFAULT_TRACK = "seek"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    port = entry.data[CONF_PORT]
    baud = entry.data.get(CONF_BAUD, DEFAULT_BAUD)
    track = entry.data.get(CONF_TRACK, DEFAULT_TRACK)

    try:
        nuvo = await hass.async_add_executor_job(get_nuvo, port, baud, track)
    except SerialException:
        raise ConfigEntryNotReady(f"Cannot connect to serial port {port}")

    model = await hass.async_add_executor_job(nuvo.get_model)
    if model == "Unknown":
        _LOGGER.warning("Could not detect Nuvo model — continuing anyway")
    else:
        _LOGGER.info("Detected Nuvo tuner %s", model)
    if not isinstance(hass.data.get(DOMAIN), dict):
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN][entry.entry_id] = nuvo

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
