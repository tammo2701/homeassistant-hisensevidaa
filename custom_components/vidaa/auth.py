"""Authentication profiles for VIDAA firmware generations."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from .const import (
    CLIENT_CERT,
    CLIENT_KEY,
    MQTT_PASSWORD,
    MQTT_USERNAME,
    VIDAA_APP_CERT,
    VIDAA_APP_KEY,
)

_PATTERN = "38D65DC30F45109A369A86FCE866A85B"
_TIME_XOR = 0x569814772B03A968
_SUFFIX_LEGACY = "h*i&s%e!r^v0i1c9"
_SUFFIX_MODERN = "h!i@s#$v%i^d&a*a"


@dataclass(frozen=True)
class AuthProfile:
    """One MQTT identity and its matching TLS client certificate."""

    method: str
    client_id: str
    username: str
    password: str
    certfile: str
    keyfile: str


def _dynamic_profile(
    package_dir: str,
    mac: str,
    method: str,
    timestamp: int | None = None,
) -> AuthProfile:
    """Generate a per-TV, time-based VIDAA MQTT identity."""
    timestamp = int(time.time()) if timestamp is None else timestamp
    uuid = mac.upper()
    race = hashlib.md5(f"{_PATTERN}${uuid}".encode()).hexdigest().upper()[:6]
    client_id = f"{uuid}$his${race}_vidaacommon_001"
    if method == "dynamic_legacy":
        username = f"his${timestamp}"
        suffix = _SUFFIX_LEGACY
    else:
        username = f"his${timestamp ^ _TIME_XOR}"
        suffix = _SUFFIX_MODERN if method == "dynamic_modern" else _SUFFIX_LEGACY
    remainder = sum(int(digit) for digit in str(timestamp)) % 10
    value_hash = hashlib.md5(f"his{remainder}{suffix}".encode()).hexdigest().upper()[:6]
    password = hashlib.md5(f"{timestamp}${value_hash}".encode()).hexdigest().upper()
    return AuthProfile(
        method=method,
        client_id=client_id,
        username=username,
        password=password,
        certfile=str(Path(package_dir) / VIDAA_APP_CERT),
        keyfile=str(Path(package_dir) / VIDAA_APP_KEY),
    )


def build_auth_profiles(
    package_dir: str,
    client_id: str,
    mac: str | None,
) -> list[AuthProfile]:
    """Return connection candidates from newer to legacy VIDAA auth."""
    profiles: list[AuthProfile] = []
    if mac:
        profiles.extend(
            _dynamic_profile(package_dir, mac, method)
            for method in ("dynamic_modern", "dynamic_middle", "dynamic_legacy")
        )
    profiles.extend(
        (
            AuthProfile(
                method="static_modern",
                client_id=client_id,
                username=MQTT_USERNAME,
                password=MQTT_PASSWORD,
                certfile=str(Path(package_dir) / VIDAA_APP_CERT),
                keyfile=str(Path(package_dir) / VIDAA_APP_KEY),
            ),
            AuthProfile(
                method="static_legacy",
                client_id=client_id,
                username=MQTT_USERNAME,
                password=MQTT_PASSWORD,
                certfile=str(Path(package_dir) / CLIENT_CERT),
                keyfile=str(Path(package_dir) / CLIENT_KEY),
            ),
        )
    )
    return profiles


def profile_for_method(
    package_dir: str, client_id: str, mac: str | None, method: str | None
) -> AuthProfile:
    """Rebuild the saved profile when Home Assistant reconnects."""
    if method and method.startswith("dynamic_") and mac:
        return _dynamic_profile(package_dir, mac, method)
    if method == "static_modern":
        return build_auth_profiles(package_dir, client_id, None)[0]
    return build_auth_profiles(package_dir, client_id, None)[-1]
