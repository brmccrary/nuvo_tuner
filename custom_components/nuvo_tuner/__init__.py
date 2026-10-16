"""The nuvo_tuner component."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from serialx import SerialException
from .tuner import get_nuvo

_LOGGER = logging.getLogger(__name__)

DOMAIN = "nuvo_tuner"
PLATFORMS = [Platform.MEDIA_PLAYER]

CONF_PORT = "port"
CONF_BAUD = "baud"
CONF_TRACK = "track"
DEFAULT_BAUD = "57600"
DEFAULT_TRACK = "seek"


async def _async_remote_port_available(hass: HomeAssistant, port: str) -> bool:
    """Whether a network serial port is currently offered by its device.

    Local paths always pass; the driver retries those on its own.
    """
    if not port.startswith(("esphome-hass://", "esphome://")):
        return True

    from homeassistant.components.usb import async_scan_serial_ports

    try:
        ports = await async_scan_serial_ports(hass)
    except Exception:
        _LOGGER.debug("Serial port scan failed", exc_info=True)
        return True
    return any(p.device == port for p in ports)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    conf = {**entry.data, **entry.options}
    port = conf[CONF_PORT]
    baud = conf.get(CONF_BAUD, DEFAULT_BAUD)
    track = conf.get(CONF_TRACK, DEFAULT_TRACK)

    applied_options = dict(entry.options)

    async def _async_reload_on_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Apply changed options (e.g. a new port) by reloading the entry.

        Title-only updates also land here; reloading on those too would run
        two setups back to back, and the first one's port would linger.
        """
        if dict(entry.options) != applied_options:
            await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))

    # A network port (e.g. an ESPHome serial proxy) only exists while its
    # device is connected, which on a restart can be after this entry loads.
    if not await _async_remote_port_available(hass, port):
        raise ConfigEntryNotReady(f"Waiting for the device providing {port} to connect")

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
        nuvo = hass.data[DOMAIN].pop(entry.entry_id, None)
        if nuvo is not None:
            # Release the port so a reload (or another integration) can open it
            await hass.async_add_executor_job(nuvo.close)
    return unload_ok
