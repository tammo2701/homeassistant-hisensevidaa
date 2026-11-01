"""Base entity for the VIDAA TV integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .vidaa import VidaaTV


class VidaaEntity(Entity):
    """Common base wiring entities to a TV client."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        tv: VidaaTV,
        entry_id: str,
        mac: str,
        name: str,
        key: str | None = None,
    ) -> None:
        """Initialise the entity.

        ``entry_id`` identifies the shared device; ``key`` distinguishes
        entities that belong to the same device.
        """
        self._tv = tv
        self._entry_id = entry_id
        self._attr_unique_id = entry_id if key is None else f"{entry_id}_{key}"
        connections: set[tuple[str, str]] = set()
        if mac:
            connections.add((CONNECTION_NETWORK_MAC, mac))
        self._name = name
        self._connections = connections

    @property
    def device_info(self) -> DeviceInfo:
        """Return device data, including a model reported by the TV if available."""
        reported_model = self._tv.state.get("model") or self._tv.state.get("modelname")
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            connections=self._connections,
            name=self._name,
            manufacturer="Hisense",
            model=reported_model or "VIDAA TV",
        )

    async def async_added_to_hass(self) -> None:
        """Register for push updates from the TV client."""
        self.async_on_remove(self._tv.add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        """Return whether the TV connection is up."""
        return self._tv.available
