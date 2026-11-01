# Certificate asset source

`vidaa_app_client.pem` and `vidaa_app_client.key` are the VidaaAppAndroid
mutual-TLS client identity used by the VIDAA mobile application protocol. They
were sourced from the MIT-licensed `vidaa-control` project:

- <https://github.com/tombabolewski/vidaa-control>
- Source files: `vidaa/certs/vidaa_client.pem` and `vidaa/certs/vidaa_client.key`
- License: MIT (see the source repository's `LICENSE`)

The original Hisense/VIDAA client identity is redistributed as required by
that license. These files are public protocol assets, not Home Assistant user
credentials. The TV still requires local network access and may require PIN
pairing.
