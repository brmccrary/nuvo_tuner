"""Support for interfacing with Nuvo T2-SIR Tuner via serial/RS-232."""

import logging
import voluptuous as vol

from homeassistant.components import zeroconf
from homeassistant.exceptions import ConfigEntryNotReady, ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv, entity_platform, \
     service, discovery

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.media_player import (DOMAIN, PLATFORM_SCHEMA, \
    MediaPlayerEnqueue, MediaPlayerEntity, MediaPlayerEntityFeature)
from homeassistant.config_entries import ConfigEntry, ConfigEntryState, \
    SOURCE_IMPORT
from homeassistant.const import (
    ATTR_ENTITY_ID, CONF_NAME, CONF_PORT, STATE_OFF, STATE_PLAYING)
from homeassistant.helpers import config_validation as cv, entity_platform, \
    service, discovery
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from typing import Any
from serial import SerialException
from nuvo_tuner import get_nuvo

NUVO = 'nuvo_tuner'
DATA_NUVO = 'nuvo_tuner'
CONF_SOURCES = 'sources'
CONF_PORT = 'port'
CONF_BAUD = 'baud'
CONF_TRACK = 'track'
CONF_NUVOSYNC = 'nuvosync'
MODEL = 'model'
DEFAULT_BAUD = '57600'
DEFAULT_TRACK = 'seek'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_PORT): cv.string,
    vol.Optional(CONF_BAUD, default=DEFAULT_BAUD): cv.string,
    vol.Optional(CONF_TRACK, default=DEFAULT_TRACK): cv.string,
})

_LOGGER = logging.getLogger(__name__)

SUPPORT_NUVO =  MediaPlayerEntityFeature.TURN_ON | \
                MediaPlayerEntityFeature.TURN_OFF | \
                MediaPlayerEntityFeature.PLAY_MEDIA | \
                MediaPlayerEntityFeature.SELECT_SOURCE | \
                MediaPlayerEntityFeature.PREVIOUS_TRACK | \
                MediaPlayerEntityFeature.NEXT_TRACK

# async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
def setup_platform(hass, config, add_entities, discovery_info=None):
    port = config.get(CONF_PORT)
    baud = config.get(CONF_BAUD)
    track = config.get(CONF_TRACK)
    hass.data[DATA_NUVO] = []

    try:
        global NUVO
        NUVO = get_nuvo(port, baud, track)
    except SerialException:
        _LOGGER.error("Error opening serial port")
        return False

    model = NUVO.get_model()
    if model == 'Unknown':
        _LOGGER.error('This does not appear to be a supported Nuvo device.')
    else:
        _LOGGER.info('Detected Nuvo tuner %s', model)

    hass.data[DATA_NUVO].append(NuvoTuner(hass,
       NUVO, 'A', 'Nuvo Tuner A'))
    hass.data[DATA_NUVO].append(NuvoTuner(hass,
       NUVO, 'B', 'Nuvo Tuner B'))

    add_entities(hass.data[DATA_NUVO], True)

class NuvoTuner(MediaPlayerEntity):
    """Representation of a Nuvo tuner."""

    def __init__(self, hass: HomeAssistant, nuvo, tuner, tuner_name):
        """Initialize new tuner."""
        self._nuvo = nuvo
        self._name = tuner_name
        self._tuner = tuner
        self._state = None
        self._source = None

    def update(self):
        """Retrieve latest state."""
        state = self._nuvo.tuner_status(self._tuner)
        self._sources = state.sources
        if not state:
            return False
        self._band = state.band
        self._channel = state.channel
        self._freq = state.freq
        self._artist = state.artist
        self._title = state.title
        self._state = STATE_PLAYING if state.power else STATE_OFF
        try:
            self._source = self._source_id_name[int(state.source)]
        except:
            self._source = 'Unknown'

    async def async_added_to_hass(self) -> None:
        self._nuvo.add_callback(self._update_callback, self._tuner)
        self.update()

    @callback
    def _update_callback(self):
        _LOGGER.debug('Tuner %s media player update called', self._tuner)
        self.schedule_update_ha_state(True)

    @property
    def name(self):
        """Return the name of the tuner."""
        return self._name

    @property
    def should_poll(self):
        """Disable polling."""
        return False

    @property
    def device_class(self):
        """Return the type of the device."""
        return 'speaker'

    @property
    def state(self):
        """Return the state of the tuner."""
        return self._state

    @property
    def source_list(self):
        """List of available input sources."""
        return self._sources

    @property
    def source(self):
        if self._channel == '':
            return f'{self._band} {self._freq}'
        else:
            return f'{self._band} {self._freq} - {self._channel}'

    @property
    def media_channel(self):
        if self._channel == '':
            return f'{self._band} {self._freq}'
        else:
            return f'{self._band} {self._freq} - {self._channel}'

    @property
    def media_artist(self):
        if self._artist == "":
            return None
        else:
            return self._artist

    @property
    def media_title(self):
        if self._title == "":
            return None
        else:
            return self._title

    @property
    def media_content_type(self):
        return 'music'

    @property
    def supported_features(self):
        """Return flag of media commands that are supported."""
        return SUPPORT_NUVO

    def select_source(self, source):
        self._nuvo.set_source(self._tuner, source)

    def media_previous_track(self):
        self._nuvo.media_previous_track(self._tuner)

    def media_next_track(self):
        self._nuvo.media_next_track(self._tuner)

    def play_media(
        self,
        media_type: str,
        media_id: str,
        enqueue: MediaPlayerEnqueue | None = None,
        announce: bool | None = None, **kwargs: Any) -> None:
        """Tunes to a specific channel and other uses.  Type is ignored."""
        self._nuvo.tune(self._tuner, media_id)

    def turn_on(self):
        """Turn the media player on."""
        self._nuvo.set_power(True)

    def turn_off(self):
        """Turn the media player off."""
        self._nuvo.set_power(False)
