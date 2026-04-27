"""Support for interfacing with Nuvo T2-SIR Tuner via serial/RS-232."""

import asyncio
import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.media_player import (DOMAIN, PLATFORM_SCHEMA,
    MediaPlayerEnqueue, MediaPlayerEntity, MediaPlayerEntityFeature)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (CONF_NAME, CONF_PORT, STATE_OFF, STATE_PLAYING)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store
from typing import Any
from serial import SerialException
from nuvo_tuner import get_nuvo

STORAGE_VERSION = 1
STORAGE_KEY = "nuvo_tuner_sources"

from . import DOMAIN as NUVO_DOMAIN

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

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    nuvo = hass.data[NUVO_DOMAIN][entry.entry_id]
    async_add_entities([
        NuvoTuner(hass, nuvo, 'A', 'Nuvo Tuner A', entry.entry_id),
        NuvoTuner(hass, nuvo, 'B', 'Nuvo Tuner B', entry.entry_id),
    ], True)


def setup_platform(hass, config, add_entities, discovery_info=None):
    port = config.get(CONF_PORT)
    baud = config.get(CONF_BAUD)
    track = config.get(CONF_TRACK)
    hass.data[DATA_NUVO] = []

    try:
        nuvo = get_nuvo(port, baud, track)
    except SerialException:
        _LOGGER.error("Error opening serial port")
        return False

    model = nuvo.get_model()
    if model == 'Unknown':
        _LOGGER.error('This does not appear to be a supported Nuvo device.')
    else:
        _LOGGER.info('Detected Nuvo tuner %s', model)

    hass.data[DATA_NUVO].append(NuvoTuner(hass, nuvo, 'A', 'Nuvo Tuner A'))
    hass.data[DATA_NUVO].append(NuvoTuner(hass, nuvo, 'B', 'Nuvo Tuner B'))

    add_entities(hass.data[DATA_NUVO], True)

class NuvoTuner(MediaPlayerEntity):
    """Representation of a Nuvo tuner."""

    def __init__(self, hass: HomeAssistant, nuvo, tuner, tuner_name, entry_id=None):
        """Initialize new tuner."""
        self._nuvo = nuvo
        self._name = tuner_name
        self._tuner = tuner
        self._state = None
        self._source = None
        self._sources = []
        self._entry_id = entry_id
        self._store = None
        self._pending_source = None
        self._pending_tries = 0

    @property
    def unique_id(self):
        if self._entry_id:
            return f"{self._entry_id}_{self._tuner}"
        return None

    def update(self):
        """Retrieve latest state."""
        state = self._nuvo.tuner_status(self._tuner)
        if not state:
            return False
        new_sources = state.sources
        self._band = state.band
        self._channel = state.channel
        self._freq = state.freq
        self._artist = state.artist
        self._title = state.title
        self._state = STATE_PLAYING if state.power else STATE_OFF
        if self._state == STATE_OFF:
            self._pending_tries = 0
        try:
            self._source = self._source_id_name[int(state.source)]
        except:
            self._source = 'Unknown'
        if self._pending_source is not None and self._state == STATE_PLAYING:
            _LOGGER.debug('Tuner %s: sending queued source change to %s (try %d)', self._tuner, self._pending_source, self._pending_tries + 1)
            self._nuvo.set_source(self._tuner, self._pending_source)
            self._pending_tries += 1
            if self._pending_tries >= 10:
                self._pending_source = None
                self._pending_tries = 0
        if state.power and new_sources != self._sources:
            cached_has_sirius = any(s.startswith('SR ') for s in self._sources)
            fresh_has_sirius = any(s.startswith('SR ') for s in new_sources)
            if cached_has_sirius and not fresh_has_sirius:
                pass  # Tuner just powered on, Sirius not yet downloaded — keep cached list
            else:
                self._sources = new_sources
                if self._store is not None:
                    asyncio.run_coroutine_threadsafe(
                        self._store.async_save({"sources": self._sources}),
                        self.hass.loop,
                    )

    async def async_added_to_hass(self) -> None:
        if self._entry_id:
            self._store = Store(
                self.hass,
                STORAGE_VERSION,
                f"{STORAGE_KEY}.{self._entry_id}.{self._tuner}",
            )
            data = await self._store.async_load()
            if data and "sources" in data:
                self._sources = data["sources"]
                _LOGGER.debug("Tuner %s: loaded %d cached sources", self._tuner, len(self._sources))
        self._nuvo.add_callback(self._update_callback, self._tuner)
        await self.hass.async_add_executor_job(self.update)

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
        self._pending_source = source
        self._pending_tries = 0
        _LOGGER.debug('Tuner %s: queuing source change to %s', self._tuner, source)
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

