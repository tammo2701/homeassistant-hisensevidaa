from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_HOST, CONF_NAME
from vidaa.config_flow import VidaaConfigFlow
from vidaa.const import DOMAIN
from vidaa.diagnostics import TO_REDACT
from vidaa.vidaa import TOPIC_SLEEP, VidaaTV


ROOT = Path(__file__).parents[1]


def test_manifest_declares_background_discovery_and_local_push() -> None:
    manifest = json.loads(
        (ROOT / "custom_components" / "vidaa" / "manifest.json").read_text()
    )

    assert manifest["domain"] == DOMAIN
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "local_push"
    assert {"dhcp", "ssdp", "network"} <= set(manifest["dependencies"])
    assert manifest["dhcp"]
    assert manifest["ssdp"]


async def test_user_flow_offers_scan_and_manual_setup(hass) -> None:
    flow = VidaaConfigFlow()
    flow.hass = hass

    result = await flow.async_step_user()

    assert result["type"] == "menu"
    assert set(result["menu_options"]) == {"scan", "manual"}


async def test_dhcp_discovery_aborts_for_existing_mac(hass, monkeypatch) -> None:
    mac = "10:11:12:13:14:15"
    entry = MagicMock()
    entry.data = {CONF_HOST: "192.168.1.20", "mac": mac}
    flow = VidaaConfigFlow()
    flow.hass = hass
    flow._async_current_entries = MagicMock(return_value=[entry])
    update_entry = MagicMock()
    monkeypatch.setattr(hass.config_entries, "async_update_entry", update_entry)
    schedule_reload = MagicMock()
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", schedule_reload)
    info = MagicMock(ip="192.168.1.21", macaddress=mac, hostname="hisense-tv")

    result = await flow.async_step_dhcp(info)

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    update_entry.assert_called_once()
    schedule_reload.assert_called_once_with(entry.entry_id)


def test_topic_sleep_marks_tv_in_standby(hass) -> None:
    tv = VidaaTV(
        hass,
        host="192.168.1.2",
        port=36669,
        client_id="test-client",
        certfile="unused.crt",
        keyfile="unused.key",
    )

    tv._ingest(TOPIC_SLEEP, "")

    assert tv.state["statetype"] == "fake_sleep_0"


def test_diagnostics_redact_network_identifiers() -> None:
    assert TO_REDACT >= {CONF_HOST, "mac", "client_id"}


def test_translations_match_source_strings() -> None:
    source = json.loads(
        (ROOT / "custom_components" / "vidaa" / "strings.json").read_text()
    )
    translation = json.loads(
        (ROOT / "custom_components" / "vidaa" / "translations" / "en.json").read_text()
    )

    assert translation == source
