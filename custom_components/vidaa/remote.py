"""Remote platform for VIDAA TV."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import RemoteEntity
from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VidaaConfigEntry
from .const import DEFAULT_NAME, KEY_POWER
from .entity import VidaaEntity
from .wol import send_magic_packet


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VidaaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the remote from a config entry."""
    tv = entry.runtime_data
    mac = entry.data.get(CONF_MAC, "")
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    async_add_entities([VidaaRemote(tv, entry.entry_id, mac, name)])


class VidaaRemote(VidaaEntity, RemoteEntity):
    """Send arbitrary key presses to a VIDAA TV."""

    _attr_name = "Remote"

    def __init__(self, tv, entry_id: str, mac: str, name: str) -> None:
        """Initialise the remote."""
        super().__init__(tv, entry_id, mac, name, key="remote")
        self._mac = mac

    @property
    def is_on(self) -> bool:
        """Return True if the TV connection is up."""
        return self._tv.available

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the TV on via Wake-on-LAN."""
        if self._mac:
            await self.hass.async_add_executor_job(send_magic_packet, self._mac)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the TV off."""
        await self.hass.async_add_executor_job(self._tv.send_key, KEY_POWER)

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send one or more key codes to the TV."""
        for cmd in command:
            await self.hass.async_add_executor_job(self._tv.send_key, cmd)
