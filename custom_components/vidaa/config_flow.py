"""Config flow for Hisense VIDAA TVs."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import uuid
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME, CONF_PORT
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .const import (
    CLIENT_CERT,
    CLIENT_KEY,
    CONF_CLIENT_ID,
    CONF_MODEL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
)
from .vidaa import CannotConnect, InvalidAuth, VidaaTV

MANUAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Optional(CONF_MAC, default=""): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)
PIN_SCHEMA = vol.Schema({vol.Required("pin"): str})


class VidaaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up a local connection to a Hisense VIDAA TV."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow state."""
        self._data: dict[str, Any] = {}
        self._tv: VidaaTV | None = None
        self._scan_hosts: list[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Offer automatic discovery, a local scan, or manual setup."""
        return self.async_show_menu(
            step_id="user", menu_options=["scan", "manual"]
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect connection details manually."""
        if user_input is not None:
            return await self._async_connect(user_input)
        return self.async_show_form(step_id="manual", data_schema=MANUAL_SCHEMA)

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Find VIDAA TVs by scanning local IPv4 networks for port 36669."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if CONF_HOST not in user_input:
                return await self.async_step_scan()
            host = user_input[CONF_HOST]
            return await self._async_connect(
                {
                    CONF_HOST: host,
                    CONF_NAME: f"VIDAA TV ({host})",
                    CONF_PORT: DEFAULT_PORT,
                }
            )

        self._scan_hosts = await self._async_scan_local_networks()
        if not self._scan_hosts:
            errors["base"] = "no_tvs_found"
            return self.async_show_form(
                step_id="scan",
                data_schema=vol.Schema(
                    {vol.Optional("scan_again", default=True): bool}
                ),
                errors=errors,
                description_placeholders={"port": str(DEFAULT_PORT)},
            )

        options = [
            {"value": host, "label": f"VIDAA TV — {host}"}
            for host in self._scan_hosts
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): SelectSelector(
                    SelectSelectorConfig(options=options, mode="dropdown")
                )
            }
        )
        return self.async_show_form(step_id="scan", data_schema=schema)

    async def async_step_ssdp(
        self, discovery_info: Any
    ) -> config_entries.ConfigFlowResult:
        """Start setup with a TV found through UPnP/SSDP."""
        upnp = getattr(discovery_info, "upnp", None) or {}
        manufacturer = str(upnp.get("manufacturer", ""))
        model = str(upnp.get("modelName", ""))
        server = getattr(discovery_info, "ssdp_server", "") or ""
        identity = " ".join((manufacturer, model, server))
        if not any(
            brand in identity.casefold() for brand in ("hisense", "vidaa", "toshiba")
        ):
            return self.async_abort(reason="not_vidaa_tv")

        location = urlsplit(getattr(discovery_info, "ssdp_location", "") or "")
        headers = getattr(discovery_info, "ssdp_headers", None) or {}
        host = location.hostname or headers.get("_host")
        if not host:
            return self.async_abort(reason="no_host")

        name = str(upnp.get("friendlyName") or model or f"VIDAA TV ({host})")
        self.context["title_placeholders"] = {"name": name}
        return await self._async_connect(
            {
                CONF_HOST: host,
                CONF_NAME: name,
                CONF_MODEL: model,
                CONF_PORT: DEFAULT_PORT,
            }
        )

    async def _async_scan_local_networks(self) -> list[str]:
        """Probe enabled local IPv4 subnets for the VIDAA MQTT service."""
        adapters = await network.async_get_adapters(self.hass)
        subnets: set[ipaddress.IPv4Network] = set()
        for adapter in adapters:
            if not adapter["enabled"]:
                continue
            for address in adapter["ipv4"]:
                subnet = ipaddress.ip_network(
                    f"{address['address']}/{address['network_prefix']}", strict=False
                )
                if subnet.is_loopback or subnet.is_link_local:
                    continue
                if subnet.num_addresses > 1024:
                    continue
                subnets.add(subnet)

        hosts = sorted({str(host) for subnet in subnets for host in subnet.hosts()})
        semaphore = asyncio.Semaphore(64)

        async def _probe(host: str) -> str | None:
            async with semaphore:
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, DEFAULT_PORT), timeout=0.5
                    )
                except (OSError, asyncio.TimeoutError):
                    return None
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
                return host

        found = await asyncio.gather(*(_probe(host) for host in hosts))
        return [host for host in found if host is not None]

    async def _async_connect(
        self, user_input: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Connect to the selected TV and begin PIN pairing if needed."""
        host = str(user_input[CONF_HOST]).strip()
        mac = str(user_input.get(CONF_MAC, "")).strip()
        if mac:
            try:
                mac = dr.format_mac(mac)
            except (TypeError, ValueError, vol.Invalid):
                return self.async_show_form(
                    step_id="manual",
                    data_schema=MANUAL_SCHEMA,
                    errors={"base": "invalid_mac"},
                )
            user_input[CONF_MAC] = mac

        await self.async_set_unique_id(host.casefold())
        self._abort_if_unique_id_configured()

        client_id = f"ha-{uuid.uuid4().hex[:12]}"
        self._data = {**user_input, CONF_HOST: host, CONF_CLIENT_ID: client_id}
        package_dir = os.path.dirname(__file__)
        tv = VidaaTV(
            self.hass,
            host=host,
            port=user_input.get(CONF_PORT, DEFAULT_PORT),
            client_id=client_id,
            certfile=os.path.join(package_dir, CLIENT_CERT),
            keyfile=os.path.join(package_dir, CLIENT_KEY),
        )
        try:
            await tv.async_connect()
            already_paired = await tv.async_authenticate()
        except CannotConnect:
            await _safe_disconnect(tv)
            return self.async_show_form(
                step_id="manual",
                data_schema=MANUAL_SCHEMA,
                errors={"base": "cannot_connect"},
            )

        self._tv = tv
        if already_paired:
            return await self._async_create()
        return await self.async_step_pair()

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask for the pairing PIN displayed on the TV."""
        errors: dict[str, str] = {}
        assert self._tv is not None

        if user_input is not None:
            try:
                await self._tv.async_send_pin(user_input["pin"])
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            else:
                return await self._async_create()

        return self.async_show_form(
            step_id="pair", data_schema=PIN_SCHEMA, errors=errors
        )

    async def _async_create(self) -> config_entries.ConfigFlowResult:
        """Create the entry after successful pairing."""
        assert self._tv is not None
        model = (
            self._tv.state.get("model")
            or self._tv.state.get("modelname")
            or self._data.get(CONF_MODEL)
        )
        if model:
            self._data[CONF_MODEL] = str(model)
            if self._data.get(CONF_NAME, DEFAULT_NAME) == DEFAULT_NAME:
                self._data[CONF_NAME] = str(model)
        await _safe_disconnect(self._tv)
        return self.async_create_entry(
            title=self._data.get(CONF_NAME, DEFAULT_NAME), data=self._data
        )


async def _safe_disconnect(tv: VidaaTV) -> None:
    """Disconnect a temporary client without masking the original error."""
    try:
        await tv.async_disconnect()
    except Exception:  # noqa: BLE001 - best effort cleanup
        pass
