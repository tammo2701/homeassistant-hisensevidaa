"""Constants for the VIDAA TV integration."""

from __future__ import annotations

DOMAIN = "vidaa"

DEFAULT_NAME = "VIDAA TV"
DEFAULT_PORT = 36669
KEEPALIVE = 60

# Credentials exposed by the TV's built-in MQTT broker. These are identical
# across all VIDAA / Hisense televisions and are required to connect.
MQTT_USERNAME = "hisenseservice"
MQTT_PASSWORD = "multimqttservice"

# Bundled mutual-TLS client identity (the standard mobile-client certificate
# the TV expects). Relative to this package directory.
CLIENT_CERT = "certs/vidaa_client.crt"
CLIENT_KEY = "certs/vidaa_client.key"

CONF_MAC = "mac"
CONF_CLIENT_ID = "client_id"
CONF_MODEL = "model"

# How long the config flow waits for the TV to answer over MQTT.
DISCOVERY_TIMEOUT = 8

# Remote key codes accepted by the sendkey action.
KEY_POWER = "KEY_POWER"
KEY_UP = "KEY_UP"
KEY_DOWN = "KEY_DOWN"
KEY_LEFT = "KEY_LEFT"
KEY_RIGHT = "KEY_RIGHT"
KEY_OK = "KEY_OK"
KEY_BACK = "KEY_BACK"
KEY_HOME = "KEY_HOME"
KEY_MENU = "KEY_MENU"
KEY_EXIT = "KEY_EXIT"
KEY_VOLUME_UP = "KEY_VOLUMEUP"
KEY_VOLUME_DOWN = "KEY_VOLUMEDOWN"
KEY_MUTE = "KEY_MUTE"
KEY_CHANNEL_UP = "KEY_CHANNELUP"
KEY_CHANNEL_DOWN = "KEY_CHANNELDOWN"
KEY_PLAY = "KEY_PLAY"
KEY_PAUSE = "KEY_PAUSE"
KEY_STOP = "KEY_STOP"
KEY_FORWARD = "KEY_FORWARDS"
KEY_REWIND = "KEY_BACKS"
KEY_SOURCE = "KEY_INPUTS"

# Full list of keys the TV understands, surfaced to the remote entity.
SUPPORTED_KEYS = [
    KEY_POWER,
    KEY_UP,
    KEY_DOWN,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_OK,
    KEY_BACK,
    KEY_HOME,
    KEY_MENU,
    KEY_EXIT,
    KEY_VOLUME_UP,
    KEY_VOLUME_DOWN,
    KEY_MUTE,
    KEY_CHANNEL_UP,
    KEY_CHANNEL_DOWN,
    KEY_PLAY,
    KEY_PAUSE,
    KEY_STOP,
    KEY_FORWARD,
    KEY_REWIND,
    KEY_SOURCE,
    "KEY_0",
    "KEY_1",
    "KEY_2",
    "KEY_3",
    "KEY_4",
    "KEY_5",
    "KEY_6",
    "KEY_7",
    "KEY_8",
    "KEY_9",
    "KEY_SUBTITLE",
    "KEY_NETFLIX",
    "KEY_YOUTUBE",
    "KEY_AMAZON",
]
