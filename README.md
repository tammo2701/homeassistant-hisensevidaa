# Hisense VIDAA TV for Home Assistant

A local Home Assistant integration for Hisense TVs running VIDAA OS, including older models from around **2018 onward**. It connects to the TV's built-in MQTT service, using TLS on newer firmware and plain MQTT on some legacy firmware. No cloud account, external broker, or bridge is required.

## Quick links

[![Add this repository to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tammo2701&repository=homeassistant-hisensevidaa&category=integration)
[![Open the integration setup in Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=vidaa)

Add and install the repository in HACS first. Then use the Home Assistant button to set up the TV. This project is an integration, not an add-on.

## Features

- Media player entity for power state, volume, mute, playback controls, and input selection
- Remote entity for supported TV keys, including navigation, digits, playback, and app shortcuts
- Wake-on-LAN power on when a MAC address is available
- Live state updates from the TV over MQTT/TLS; state and volume are requested at connection time
- Automatic local discovery through UPnP/SSDP and matching DHCP hostnames or Hisense MAC prefix
- Automatic IP address updates when DHCP rediscovers a configured TV by MAC address
- Local IPv4 subnet scan as a manual fallback when automatic discovery is unavailable
- PIN pairing and UI flows for re-pairing or changing connection details
- Redacted diagnostics for troubleshooting

## Compatibility

The integration supports multiple VIDAA generations, including some 2018–2019 models. Model year does not guarantee compatibility because networking and authentication vary by model, market, and firmware. Newer sets typically expose TLS MQTT and PIN pairing; some older sets use unencrypted MQTT and authorize the remote without a PIN. Keep the TV powered on and connected to the same reachable LAN during setup.

The setup flow tries supported secure and legacy connection profiles before saving the entry. Some older sets use unencrypted local MQTT; use this only on a trusted home network. TVs exposing a different control protocol are not supported.

During setup, the integration tries the known VIDAA authentication profiles
for newer and legacy firmware. When the TV's MAC address is available from
DHCP or entered in the setup form, it can also derive the per-TV credentials
used by newer VIDAA releases. Authentication failure is reported separately
from an unreachable IP address. The bundled mobile-client certificate source
and license are documented in [`custom_components/vidaa/certs/ASSET_SOURCE.md`](custom_components/vidaa/certs/ASSET_SOURCE.md).

## Installation

### HACS

1. Use **Add this repository to HACS** above, or open **HACS → Integrations → Custom repositories**.
2. Add `https://github.com/tammo2701/homeassistant-hisensevidaa` as an **Integration**.
3. Install **Hisense VIDAA TV** in HACS.
4. Use the setup button above, or go to **Settings → Devices & services → Add integration**.

A Home Assistant restart may be needed after installing or updating an integration that was already loaded.

### Manual installation

Copy `custom_components/vidaa` into the Home Assistant `config/custom_components/` directory and restart Home Assistant.

## Automatic discovery and setup

Home Assistant can detect TVs without you opening the integration first:

- UPnP/SSDP advertisements can provide the TV name and model.
- DHCP hostnames beginning with `hisense`, `vidaa`, or `toshiba`, and the Hisense MAC prefix `10:C7:53`, can trigger a discovery flow. DHCP sightings are offered even if the TV's MQTT port is temporarily unavailable; setup then reports the connection stage clearly.
- When a configured TV is seen at a new address with the same MAC address, the integration updates its stored address and reloads the connection.

DHCP discovery depends on Home Assistant seeing the TV's DHCP traffic. If the TV does not announce itself, open **Add integration → Hisense VIDAA TV → Scan the local network**. The scan checks enabled IPv4 networks with up to 1,024 addresses, adds hosts already observed by Home Assistant's DHCP listener, and reports hosts with an open VIDAA port. Larger networks are skipped to avoid an excessive scan.

## Setup fields

Manual setup asks for:

- **IP address:** The TV's current LAN address.
- **Name:** The name shown for the device in Home Assistant.
- **MAC address:** Optional; used for Wake-on-LAN and stable DHCP rediscovery.
- **Port:** The VIDAA MQTT port, normally `36669`.

Automatic discovery fills in the network address and available hostname/model information. A four-digit PIN shown on the TV completes pairing. The device can be renamed later in Home Assistant.

## Entities and controls

### Media player

The media player entity reports whether the TV is on or in standby and exposes supported volume, mute, playback, and source controls. Available sources are learned from the TV. Power on is exposed when a MAC address is configured and uses Wake-on-LAN; power off uses the TV's remote key protocol.

### Remote

The remote entity sends VIDAA key codes. It supports power, navigation, home/menu/back, digits, channel and volume keys, playback keys, input, and common app shortcuts. An unsupported key is rejected with a clear error.

Example service calls:

```yaml
action: media_player.volume_set
target:
  entity_id: media_player.living_room_tv
data:
  volume_level: 0.25
```

```yaml
action: remote.send_command
target:
  entity_id: remote.living_room_tv_remote
data:
  command: KEY_HOME
```

### Automation example

Turn the TV off when everyone leaves:

```yaml
alias: Turn off the VIDAA TV when everyone leaves
triggers:
  - trigger: state
    entity_id: group.family
    to: not_home
    for: "00:05:00"
actions:
  - action: media_player.turn_off
    target:
      entity_id: media_player.living_room_tv
```

This integration does not provide custom Home Assistant triggers or conditions. Use the media player and remote entities with standard Home Assistant automation actions.

## Data updates

The integration requests TV state and volume when its MQTT connection starts. The TV then pushes state, volume, input, and standby updates when available. No periodic polling is used. If the connection drops, entities become unavailable; the MQTT client reconnects and updates them when the TV is reachable again.

## Re-pairing and connection changes

If the TV loses its Home Assistant pairing, the integration asks for the on-screen PIN again while keeping the existing entities. To change the IP address, name, port, or Wake-on-LAN MAC, open the integration's entry menu and select **Reconfigure**.

## Troubleshooting

- **No discovery prompt:** Confirm that Home Assistant and the TV share a LAN, the TV has mobile remote control enabled, and Home Assistant can receive SSDP/DHCP broadcasts. Try **Scan the local network** or enter the IP manually.
- **Scan finds nothing:** Confirm the TV is on and that TCP port `36669` is reachable from Home Assistant. The scanner skips IPv4 networks larger than 1,024 addresses.
- **Connection fails:** The setup message distinguishes a timeout, a closed TLS/MQTT handshake, and broker credential rejection. Check the IP, port `36669`, VLAN/firewall rules, that the TV is awake, and that mobile remote control is enabled. Review the Home Assistant log for the connection stage and broker response. Reserve its address in the router if possible.
- **PIN rejected or pairing required:** Enter the current four-digit code shown on the TV. If the TV's mobile-control permission was reset, enable it again in the TV settings.
- **Wake-on-LAN does not work:** Add the TV's MAC address, enable network standby/Wake-on-LAN in the TV settings, and verify that the TV remains connected to Ethernet or Wi-Fi in standby.
- **Need help diagnosing an issue:** Download diagnostics from the integration entry. The host, MAC address, and MQTT client ID are redacted.

The TV's MQTT service and authentication vary by firmware. A closed or incompatible local interface cannot be fixed by Home Assistant configuration alone.

## Limitations

- Firmware updates are not supported; the local VIDAA MQTT interface used here does not expose a firmware-update operation.
- TVs without the TLS/PIN MQTT service on port `36669` are not supported.
- Automatic IP updates require DHCP discovery and a matching MAC address; otherwise, reconfigure the host manually.
- Local subnet scans only cover enabled Home Assistant IPv4 networks of up to 1,024 addresses and only run when started from the setup UI.

## Removal

1. Remove **Hisense VIDAA TV** from **Settings → Devices & services**.
2. If installed through HACS, uninstall it from HACS.
3. Restart Home Assistant if the integration had already been loaded.

## Acknowledgements

This project is licensed under the MIT License. Its MQTT transport and Home Assistant integration structure are based on [Alexa-RR/ha-vidaa](https://github.com/Alexa-RR/ha-vidaa). The Hisense logo is used only to identify TV compatibility. This is an independent community project and is not affiliated with Hisense.
