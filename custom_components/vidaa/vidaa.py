"""Direct local MQTT client for VIDAA / Hisense televisions.

The TV runs its own MQTT broker on port 36669 protected by mutual TLS. This
client connects to it directly - no external broker or bridge is involved.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import ssl
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant, callback

from .const import (
    DISCOVERY_TIMEOUT,
    KEEPALIVE,
    MQTT_PASSWORD,
    MQTT_USERNAME,
)

_LOGGER = logging.getLogger(__name__)

# Broadcast topics the TV publishes to (no client id in the path).
TOPIC_BROADCAST = "/remoteapp/mobile/broadcast/#"
TOPIC_STATE = "/remoteapp/mobile/broadcast/ui_service/state"
TOPIC_VOLUME = "/remoteapp/mobile/broadcast/platform_service/actions/volumechange"
TOPIC_SLEEP = "/remoteapp/mobile/broadcast/platform_service/actions/tvsleep"


def _build_client(client_id: str) -> mqtt.Client:
    """Create a paho client compatible with both the v1 and v2 APIs."""
    try:
        from paho.mqtt.client import CallbackAPIVersion

        return mqtt.Client(CallbackAPIVersion.VERSION1, client_id=client_id)
    except (ImportError, AttributeError, TypeError):  # pragma: no cover
        return mqtt.Client(client_id=client_id)


class VidaaError(Exception):
    """Base error for the VIDAA client."""


class CannotConnect(VidaaError):
    """Raised when the TV broker cannot be reached."""


class InvalidAuth(VidaaError):
    """Raised when PIN pairing fails."""


class VidaaTV:
    """Manage the lifecycle of a single TV connection."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        client_id: str,
        certfile: str,
        keyfile: str,
    ) -> None:
        """Initialise the client."""
        self.hass = hass
        self.host = host
        self.port = port
        self.client_id = client_id
        self.available = False
        self.state: dict[str, Any] = {}

        self._certfile = certfile
        self._keyfile = keyfile
        self._tls_ready = False
        self._listeners: list[Callable[[], None]] = []
        self._message_hooks: list[Callable[[str, Any], None]] = []

        self._client = _build_client(client_id)
        self._client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def _setup_tls(self) -> None:
        """Build the TLS context (blocking - run in an executor).

        The TV presents a legacy certificate and cipher suite that modern
        OpenSSL rejects at its default security level, so the level is lowered
        and peer verification is disabled. The connection stays encrypted and
        the TV still authenticates us via the bundled client certificate.
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certfile=self._certfile, keyfile=self._keyfile)
        try:
            context.set_ciphers("DEFAULT:@SECLEVEL=0")
        except ssl.SSLError:  # pragma: no cover - depends on OpenSSL build
            _LOGGER.debug("Unable to lower cipher security level")
        self._client.tls_set_context(context)
        self._client.tls_insecure_set(True)
        self._tls_ready = True

    # -- topic helpers -------------------------------------------------

    def _action(self, service: str, action: str) -> str:
        """Build a publish topic addressed to the TV."""
        return f"/remoteapp/tv/{service}/{self.client_id}/actions/{action}"

    @property
    def _mobile(self) -> str:
        """Base topic the TV replies to for this client."""
        return f"/remoteapp/mobile/{self.client_id}"

    # -- connection ----------------------------------------------------

    async def async_connect(self) -> None:
        """Connect and start the network loop."""
        if not self._tls_ready:
            await self.hass.async_add_executor_job(self._setup_tls)
        try:
            await self.hass.async_add_executor_job(
                self._client.connect, self.host, self.port, KEEPALIVE
            )
        except (OSError, socket.error) as err:
            _LOGGER.error(
                "Failed to connect to VIDAA TV at %s:%s: %s",
                self.host,
                self.port,
                err,
            )
            raise CannotConnect(str(err)) from err
        self._client.loop_start()

    async def async_disconnect(self) -> None:
        """Stop the loop and disconnect."""
        await self.hass.async_add_executor_job(self._client.disconnect)
        self._client.loop_stop()

    # -- paho callbacks (run in the network thread) --------------------

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            _LOGGER.warning("VIDAA TV %s refused connection (rc=%s)", self.host, rc)
            return
        client.subscribe(TOPIC_BROADCAST)
        client.subscribe(f"{self._mobile}/#")
        self.available = True
        # Pull current state right away.
        self.send("ui_service", "gettvstate")
        self.send("platform_service", "getvolume")
        self._dispatch()

    def _on_disconnect(self, client, userdata, rc) -> None:
        self.available = False
        self._dispatch()

    def _on_message(self, client, userdata, msg) -> None:
        raw = msg.payload.decode("utf-8", "ignore")
        try:
            data: Any = json.loads(raw)
        except (ValueError, TypeError):
            data = raw
        self._ingest(msg.topic, data)

    # -- state handling ------------------------------------------------

    def _ingest(self, topic: str, data: Any) -> None:
        """Fold an incoming message into the cached state."""
        if topic == TOPIC_STATE or topic.endswith("/data/gettvstate"):
            if isinstance(data, dict):
                self.state.update(data)
        elif topic == TOPIC_VOLUME or topic.endswith("/data/getvolume"):
            if isinstance(data, dict):
                self.state["volume"] = data
        elif topic == TOPIC_SLEEP:
            self.state["statetype"] = "fake_sleep_0"
        elif topic.endswith("/data/sourcelist"):
            self.state["sourcelist"] = data
        elif topic.endswith("/data/applist"):
            self.state["applist"] = data

        for hook in list(self._message_hooks):
            hook(topic, data)
        self._dispatch()

    # -- commands ------------------------------------------------------

    def publish(self, topic: str, payload: Any = "") -> None:
        """Publish a raw payload to the TV."""
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        self._client.publish(topic, payload)

    def send(self, service: str, action: str, payload: Any = "") -> None:
        """Publish an action to the TV."""
        self.publish(self._action(service, action), payload)

    def send_key(self, key: str) -> None:
        """Send a remote key press."""
        self.send("remote_service", "sendkey", key)

    def set_volume(self, volume: int) -> None:
        """Set the absolute volume (0-100)."""
        self.send("platform_service", "changevolume", str(int(volume)))

    def request_volume(self) -> None:
        """Ask the TV for its current volume."""
        self.send("platform_service", "getvolume")

    def request_sources(self) -> None:
        """Ask the TV for its input source list."""
        self.send("ui_service", "sourcelist")

    def select_source(self, source_id: str, source_name: str) -> None:
        """Switch to an input source."""
        self.send(
            "ui_service",
            "changesource",
            {"sourceid": source_id, "sourcename": source_name},
        )

    def request_apps(self) -> None:
        """Ask the TV for its installed app list."""
        self.send("ui_service", "applist")

    def launch_app(self, app_id: str, name: str, url: str) -> None:
        """Launch an installed application."""
        self.send("ui_service", "launchapp", {"appId": app_id, "name": name, "url": url})

    # -- pairing -------------------------------------------------------

    async def async_authenticate(self) -> bool:
        """Trigger the on-screen PIN. Returns True if already paired."""
        future: asyncio.Future[bool] = self.hass.loop.create_future()

        def _hook(topic: str, data: Any) -> None:
            if topic.endswith("/ui_service/data/authentication"):
                if not future.done():
                    future.set_result(False)  # PIN required
            elif topic.endswith("/data/gettvstate"):
                if not future.done():
                    future.set_result(True)  # already paired

        remove = self.add_message_hook(_hook)
        try:
            self.send("ui_service", "gettvstate")
            try:
                return await asyncio.wait_for(future, DISCOVERY_TIMEOUT)
            except asyncio.TimeoutError:
                # No explicit auth prompt and no state: assume pairing is needed.
                return False
        finally:
            remove()

    async def async_send_pin(self, pin: str) -> None:
        """Submit the PIN shown on the TV."""
        future: asyncio.Future[bool] = self.hass.loop.create_future()

        def _hook(topic: str, data: Any) -> None:
            if topic.endswith("/data/authenticationcode") and not future.done():
                ok = isinstance(data, dict) and data.get("result") in (1, "1", True)
                future.set_result(ok)

        remove = self.add_message_hook(_hook)
        try:
            self.send("ui_service", "authenticationcode", {"authNum": int(pin)})
            try:
                ok = await asyncio.wait_for(future, DISCOVERY_TIMEOUT)
            except asyncio.TimeoutError as err:
                raise InvalidAuth("Timed out waiting for PIN result") from err
            if not ok:
                raise InvalidAuth("TV rejected the PIN")
        finally:
            remove()

    # -- listeners -----------------------------------------------------

    def add_message_hook(self, hook: Callable[[str, Any], None]) -> Callable[[], None]:
        """Register a raw message hook used during pairing."""
        self._message_hooks.append(hook)

        def _remove() -> None:
            if hook in self._message_hooks:
                self._message_hooks.remove(hook)

        return _remove

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register an entity update listener."""
        self._listeners.append(listener)

        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    def _dispatch(self) -> None:
        """Notify listeners on the event loop thread."""

        @callback
        def _run() -> None:
            for listener in list(self._listeners):
                listener()

        self.hass.loop.call_soon_threadsafe(_run)
