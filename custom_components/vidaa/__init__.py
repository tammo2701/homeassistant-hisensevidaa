"""The VIDAA TV integration."""

from __future__ import annotations

import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import (
    CLIENT_CERT,
    CLIENT_KEY,
    CONF_CLIENT_ID,
    CONF_MODEL,
    DEFAULT_PORT,
    DOMAIN,
)
from .vidaa import CannotConnect, InvalidAuth, VidaaTV

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.REMOTE]

type VidaaConfigEntry = ConfigEntry[VidaaTV]


async def async_setup_entry(hass: HomeAssistant, entry: VidaaConfigEntry) -> bool:
    """Set up VIDAA TV from a config entry."""
    package_dir = os.path.dirname(__file__)
    certfile = os.path.join(package_dir, CLIENT_CERT)
    keyfile = os.path.join(package_dir, CLIENT_KEY)

    tv = VidaaTV(
        hass,
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        client_id=entry.data[CONF_CLIENT_ID],
        certfile=certfile,
        keyfile=keyfile,
    )
    if model := entry.data.get(CONF_MODEL):
        tv.state["model"] = model

    try:
        await tv.async_connect()
        if not await tv.async_authenticate():
            await tv.async_disconnect()
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="pairing_required"
            )
    except InvalidAuth as err:
        await tv.async_disconnect()
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="invalid_auth"
        ) from err
    except CannotConnect as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": entry.data[CONF_HOST]},
        ) from err

    entry.runtime_data = tv
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VidaaConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_disconnect()
    return unload_ok
