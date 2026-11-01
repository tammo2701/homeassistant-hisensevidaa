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
from homeassistant.exceptions import HomeAssistantError
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
PIN_SCHEMA = vol.Schema(
    {vol.Required("pin"): vol.All(str, vol.Match(r"^\d{4}$"))}
)


class VidaaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up a local connection to a Hisense VIDAA TV."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow state."""
        self._data: dict[str, Any] = {}
        self._tv: VidaaTV | None = None
        self._scan_hosts: list[str] = []
        self._discovered_data: dict[str, Any] = {}
        self._reconfigure_entry: config_entries.ConfigEntry | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None

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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Update a TV's host, name, port, or Wake-on-LAN MAC address."""
        entry = self._get_reconfigure_entry()
        self._reconfigure_entry = entry
        if user_input is not None:
            updated_data = {**entry.data, **user_input}
            if user_input[CONF_HOST] != entry.data[CONF_HOST]:
                updated_data.pop(CONF_CLIENT_ID, None)
            return await self._async_connect(updated_data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(MANUAL_SCHEMA, entry.data),
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Restart pairing if the TV no longer trusts Home Assistant."""
        self._reauth_entry = self._get_reauth_entry()
        assert self._reauth_entry is not None
        self._data = dict(entry_data)
        errors: dict[str, str] = {}
        try:
            self._tv = await self._async_create_client(self._data)
            await self._tv.async_connect()
            if await self._tv.async_authenticate():
                await _safe_disconnect(self._tv)
                return self.async_update_reload_and_abort(
                    self._reauth_entry, data_updates={}
                )
        except CannotConnect:
            if self._tv is not None:
                await _safe_disconnect(self._tv)
            self._tv = None
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            if self._tv is not None:
                await _safe_disconnect(self._tv)
            self._tv = None
            errors["base"] = "invalid_auth"
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=PIN_SCHEMA, errors=errors
        )

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Pair the existing entry again with a TV PIN."""
        assert self._reauth_entry is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                if self._tv is None:
                    self._tv = await self._async_create_client(self._data)
                    await self._tv.async_connect()
                    if await self._tv.async_authenticate():
                        await _safe_disconnect(self._tv)
                        return self.async_update_reload_and_abort(
                            self._reauth_entry, data_updates={}
                        )
                await self._tv.async_send_pin(user_input["pin"])
            except CannotConnect:
                if self._tv is not None:
                    await _safe_disconnect(self._tv)
                self._tv = None
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            else:
                await _safe_disconnect(self._tv)
                return self.async_update_reload_and_abort(
                    self._reauth_entry, data_updates={}
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=PIN_SCHEMA, errors=errors
        )

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

        try:
            self._scan_hosts = await self._async_scan_local_networks()
        except (OSError, HomeAssistantError):
            errors["base"] = "scan_failed"
            return self.async_show_form(
                step_id="scan",
                data_schema=vol.Schema(
                    {vol.Optional("scan_again", default=True): bool}
                ),
                errors=errors,
                description_placeholders={"port": str(DEFAULT_PORT)},
            )
        configured_hosts = {
            str(entry.data.get(CONF_HOST, "")).casefold()
            for entry in self._async_current_entries()
        }
        self._scan_hosts = [
            host for host in self._scan_hosts if host.casefold() not in configured_hosts
        ]
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

    async def async_step_dhcp(
        self, discovery_info: Any
    ) -> config_entries.ConfigFlowResult:
        """Handle a VIDAA-like TV seen in local DHCP traffic."""
        host = str(discovery_info.ip)
        try:
            mac = dr.format_mac(discovery_info.macaddress)
        except (TypeError, ValueError, vol.Invalid):
            mac = ""

        # DHCP can report a TV after its address changes. Reuse its existing
        # entry by MAC so users do not get duplicate devices.
        for entry in self._async_current_entries():
            entry_mac = str(entry.data.get(CONF_MAC, "")).casefold()
            same_mac = bool(entry_mac and entry_mac == mac.casefold())
            same_host = str(entry.data.get(CONF_HOST, "")).casefold() == host.casefold()
            if same_mac or same_host:
                updated_mac = mac or str(entry.data.get(CONF_MAC, ""))
                changed = (
                    entry.data.get(CONF_HOST) != host
                    or (mac and entry.data.get(CONF_MAC) != mac)
                )
                if changed:
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={**entry.data, CONF_HOST: host, CONF_MAC: updated_mac},
                        unique_id=(updated_mac or host).casefold(),
                    )
                    self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return self.async_abort(reason="already_configured")

        await self.async_set_unique_id((mac or host).casefold())
        self._abort_if_unique_id_configured()
        if not await _async_port_open(host, DEFAULT_PORT):
            return self.async_abort(reason="not_vidaa_tv")

        hostname = str(getattr(discovery_info, "hostname", "") or "").strip()
        name = hostname or f"VIDAA TV ({host})"
        self._discovered_data = {
            CONF_HOST: host,
            CONF_NAME: name,
            CONF_MAC: mac,
            CONF_PORT: DEFAULT_PORT,
        }
        self.context["title_placeholders"] = {"name": name}
        return await self.async_step_dhcp_confirm()

    async def async_step_dhcp_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask before pairing a TV detected from DHCP traffic."""
        if user_input is not None:
            return await self._async_connect(self._discovered_data)
        return self.async_show_form(
            step_id="dhcp_confirm",
            description_placeholders={
                "name": self._discovered_data[CONF_NAME],
                "host": self._discovered_data[CONF_HOST],
            },
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

        if self._reconfigure_entry is None:
            for entry in self._async_current_entries():
                entry_host = str(entry.data.get(CONF_HOST, "")).casefold()
                entry_mac = str(entry.data.get(CONF_MAC, "")).casefold()
                if entry_host == host.casefold() or (mac and entry_mac == mac.casefold()):
                    return self.async_abort(reason="already_configured")

            await self.async_set_unique_id((mac or host).casefold())
            self._abort_if_unique_id_configured()

        client_id = user_input.get(CONF_CLIENT_ID) or f"ha-{uuid.uuid4().hex[:12]}"
        self._data = {**user_input, CONF_HOST: host, CONF_CLIENT_ID: client_id}
        tv = await self._async_create_client(self._data)
        try:
            await tv.async_connect()
            already_paired = await tv.async_authenticate()
        except (CannotConnect, InvalidAuth) as err:
            await _safe_disconnect(tv)
            if isinstance(err, InvalidAuth):
                error = "invalid_auth"
            else:
                error = "cannot_connect"
            return self.async_show_form(
                step_id="manual",
                data_schema=MANUAL_SCHEMA,
                errors={"base": error},
            )

        self._tv = tv
        if already_paired:
            return await self._async_create()
        return await self.async_step_pair()

    async def _async_create_client(self, data: dict[str, Any]) -> VidaaTV:
        """Create a client using the integration's bundled TLS identity."""
        package_dir = os.path.dirname(__file__)
        return VidaaTV(
            self.hass,
            host=str(data[CONF_HOST]),
            port=int(data.get(CONF_PORT, DEFAULT_PORT)),
            client_id=str(data[CONF_CLIENT_ID]),
            certfile=os.path.join(package_dir, CLIENT_CERT),
            keyfile=os.path.join(package_dir, CLIENT_KEY),
        )

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
        title = self._data.get(CONF_NAME, DEFAULT_NAME)
        if self._reconfigure_entry is not None:
            return self.async_update_reload_and_abort(
                self._reconfigure_entry,
                data_updates=self._data,
                title=title,
                unique_id=(self._data.get(CONF_MAC) or self._data[CONF_HOST]).casefold(),
            )
        return self.async_create_entry(title=title, data=self._data)


async def _safe_disconnect(tv: VidaaTV) -> None:
    """Disconnect a temporary client without masking the original error."""
    try:
        await tv.async_disconnect()
    except Exception:  # noqa: BLE001 - best effort cleanup
        pass


async def _async_port_open(host: str, port: int) -> bool:
    """Check that the VIDAA MQTT TCP endpoint is reachable."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=1.0
        )
    except (OSError, asyncio.TimeoutError):
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return True
