# Hisense VIDAA TV for Home Assistant

A local Home Assistant integration for Hisense TVs running VIDAA OS, focused on models from **2020 through 2026**. The integration communicates directly with the TV over its local network; it does not use a cloud service or external MQTT broker.

## Features

- Media player controls for power state, volume, mute, playback, and input selection
- Remote entity for sending supported VIDAA key codes
- Optional Wake-on-LAN power on when a MAC address is provided
- Live state updates from the TV over local MQTT/TLS
- Automatic UPnP/SSDP discovery with the TV name and model when the device publishes them
- Local subnet scan for TVs that do not announce themselves over SSDP
- One-time PIN pairing using the code shown on the TV

## Compatibility

The project targets Hisense VIDAA models released from 2020 to 2026. VIDAA firmware and network capabilities can vary by model, market, and software version, so the model year alone cannot guarantee compatibility. The TV must expose the TLS-protected MQTT service on TCP port `36669` and support mobile remote control and PIN pairing. The TV needs to be powered on during setup.

Home Assistant 2024.6 or newer is required.

## Installation with HACS

1. In HACS, open **Integrations** and choose **Custom repositories** from the menu.
2. Add `https://github.com/tammo2701/homeassistant-hisensevidaa` as an **Integration**.
3. Install **Hisense VIDAA TV** and restart Home Assistant.

## Manual installation

Copy `custom_components/vidaa` into the Home Assistant `config/custom_components/` directory, then restart Home Assistant.

## Setup and discovery

Home Assistant can offer the integration automatically when it discovers a Hisense/VIDAA TV through UPnP/SSDP. The device description can provide the TV's friendly name and model, which are used for the integration title and device details.

To find TVs that do not announce themselves through SSDP:

1. Open **Settings → Devices & services → Add integration → Hisense VIDAA TV**.
2. Select **Scan local network**. The integration checks enabled local IPv4 networks for the VIDAA service on port `36669`.
3. Select the TV it finds. If it is not found, use **Enter details manually** or check that Home Assistant and the TV are on the same LAN. Automatic scans skip networks larger than 1,024 addresses.
4. Enter the PIN displayed on the TV to finish pairing.

Enable mobile remote or app control in the TV settings before setup. Reserve the TV's IP address in your router if possible. Enter its MAC address during manual setup to enable Wake-on-LAN.

## License and acknowledgements

This project is licensed under the MIT License. Its MQTT transport and Home Assistant integration structure are based on the open-source project [Alexa-RR/ha-vidaa](https://github.com/Alexa-RR/ha-vidaa). VIDAA and Hisense are trademarks of their respective owners. This is an independent community project and is not affiliated with Hisense.
