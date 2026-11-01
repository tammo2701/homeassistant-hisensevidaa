"""Diagnostics support for Hisense VIDAA TVs."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_CLIENT_ID, DOMAIN
from .vidaa import VidaaTV

TO_REDACT = {CONF_HOST, CONF_MAC, CONF_CLIENT_ID}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[VidaaTV]
) -> dict[str, Any]:
    """Return useful connection state without exposing network identifiers."""
    tv = entry.runtime_data
    state = {
        key: tv.state[key]
        for key in ("model", "modelname", "statetype", "sourcename", "volume")
        if key in tv.state
    }
    return {
        "entry": async_redact_data(entry.data, TO_REDACT),
        "connection": {
            "available": tv.available,
            "port": tv.port,
            "state": state,
        },
    }
