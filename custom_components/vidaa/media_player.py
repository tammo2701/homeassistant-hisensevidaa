"""Media player platform for VIDAA TV."""

from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VidaaConfigEntry
from .const import (
    DEFAULT_NAME,
    KEY_MUTE,
    KEY_POWER,
    KEY_VOLUME_DOWN,
    KEY_VOLUME_UP,
)
from .entity import VidaaEntity
from .wol import send_magic_packet

SUPPORT = (
    MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VidaaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the media player from a config entry."""
    tv = entry.runtime_data
    mac = entry.data.get(CONF_MAC, "")
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    async_add_entities([VidaaMediaPlayer(tv, entry.entry_id, mac, name)])


class VidaaMediaPlayer(VidaaEntity, MediaPlayerEntity):
    """Representation of a VIDAA TV as a media player."""

    _attr_name = None
    _attr_supported_features = SUPPORT

    def __init__(self, tv, entry_id: str, mac: str, name: str) -> None:
        """Initialise the media player."""
        super().__init__(tv, entry_id, mac, name)
        self._mac = mac
        if mac:
            self._attr_supported_features |= MediaPlayerEntityFeature.TURN_ON

    @property
    def state(self) -> MediaPlayerState:
        """Return the current playback state."""
        if not self._tv.available:
            return MediaPlayerState.OFF
        statetype = self._tv.state.get("statetype", "")
        if statetype in ("fake_sleep_0", "standby"):
            return MediaPlayerState.OFF
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float | None:
        """Return the volume level (0..1)."""
        volume = self._tv.state.get("volume", {})
        value = volume.get("volume_value") if isinstance(volume, dict) else None
        if value is None:
            return None
        return int(value) / 100

    @property
    def is_volume_muted(self) -> bool | None:
        """Return whether the TV is muted."""
        volume = self._tv.state.get("volume", {})
        if isinstance(volume, dict) and "muted" in volume:
            return bool(volume["muted"])
        return None

    @property
    def source(self) -> str | None:
        """Return the active input source."""
        return self._tv.state.get("sourcename")

    @property
    def source_list(self) -> list[str]:
        """Return the list of selectable input sources."""
        sources = self._tv.state.get("sourcelist", [])
        if isinstance(sources, list):
            return [s.get("sourcename", "") for s in sources if isinstance(s, dict)]
        return []

    async def async_turn_on(self) -> None:
        """Turn the TV on via Wake-on-LAN."""
        if self._mac:
            await self.hass.async_add_executor_job(send_magic_packet, self._mac)

    async def async_turn_off(self) -> None:
        """Turn the TV off."""
        await self.hass.async_add_executor_job(self._tv.send_key, KEY_POWER)

    async def async_volume_up(self) -> None:
        """Step the volume up."""
        await self.hass.async_add_executor_job(self._tv.send_key, KEY_VOLUME_UP)

    async def async_volume_down(self) -> None:
        """Step the volume down."""
        await self.hass.async_add_executor_job(self._tv.send_key, KEY_VOLUME_DOWN)

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute the TV."""
        await self.hass.async_add_executor_job(self._tv.send_key, KEY_MUTE)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set the absolute volume level."""
        await self.hass.async_add_executor_job(
            self._tv.set_volume, round(volume * 100)
        )

    async def async_select_source(self, source: str) -> None:
        """Select an input source by name."""
        sources = self._tv.state.get("sourcelist", [])
        for item in sources if isinstance(sources, list) else []:
            if isinstance(item, dict) and item.get("sourcename") == source:
                await self.hass.async_add_executor_job(
                    self._tv.select_source,
                    item.get("sourceid", ""),
                    item.get("sourcename", ""),
                )
                return

    async def async_media_play(self) -> None:
        """Send play."""
        await self.hass.async_add_executor_job(self._tv.send_key, "KEY_PLAY")

    async def async_media_pause(self) -> None:
        """Send pause."""
        await self.hass.async_add_executor_job(self._tv.send_key, "KEY_PAUSE")

    async def async_media_stop(self) -> None:
        """Send stop."""
        await self.hass.async_add_executor_job(self._tv.send_key, "KEY_STOP")

    async def async_added_to_hass(self) -> None:
        """Request source list once connected."""
        await super().async_added_to_hass()
        await self.hass.async_add_executor_job(self._tv.request_sources)
