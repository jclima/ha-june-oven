# June Oven for Home Assistant

[![Release](https://img.shields.io/github/v/release/jclima/ha-june-oven)](https://github.com/jclima/ha-june-oven/releases)
[![Validate](https://github.com/jclima/ha-june-oven/actions/workflows/validate.yml/badge.svg)](https://github.com/jclima/ha-june-oven/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/github/license/jclima/ha-june-oven)](LICENSE)
[![Home Assistant 2025.1+](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5)](https://www.home-assistant.io/)

An unofficial Home Assistant custom integration for pairing with, monitoring,
and controlling June ovens. It pairs as a companion with an oven running the
[Project July](https://project-july.org) local server, or with June's cloud,
with no Homebridge, Apple HomeKit, June account login, or extracted app
credentials required.

[![Open your Home Assistant instance and add this repository to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jclima&repository=ha-june-oven&category=integration)

> [!WARNING]
> This integration can start a real heating appliance remotely. Begin testing
> at a low temperature with the oven attended and unobstructed. Verify that
> **Turn off** works before creating any automation that starts cooking.

> [!IMPORTANT]
> This project uses an unofficial, reverse-engineered cloud API. June or Weber
> may change or discontinue the service without notice. The software and
> protocol checks pass, but broader physical-oven validation is still needed.

## Contents

- [Features](#features)
- [Requirements and limitations](#requirements-and-limitations)
- [Installation](#installation)
- [Pairing the oven](#pairing-the-oven)
- [Project July local server](#project-july-local-server)
- [Configuration](#configuration)
- [Entities and controls](#entities-and-controls)
- [Automations](#automations)
- [Troubleshooting](#troubleshooting)
- [Diagnostics, privacy, and security](#diagnostics-privacy-and-security)
- [Removing the integration](#removing-the-integration)
- [Development and contributing](#development-and-contributing)
- [Support the project](#support-the-project)
- [Provenance and license](#provenance-and-license)

## Features

- Native Home Assistant config flow with an eight-digit oven pairing code.
- Climate entity with current temperature, target temperature, on/off, and
  cook-mode presets.
- Connectivity, preheat-ready, and cook-done binary sensors.
- Food-probe temperature, cook-progress, cook-phase, and elapsed-time sensors.
- Interior-camera snapshots while the oven is cooking.
- Works with a Project July local server by oven hostname or IP address.
- Live WebSocket telemetry with a periodic status fallback.
- Signed command acknowledgements, automatic token renewal, and reconnects.
- Multiple ovens by adding the integration once per oven.
- Downloadable diagnostics with credentials and camera URLs redacted.

## Requirements and limitations

| Requirement | Details |
| --- | --- |
| Home Assistant | Version 2025.1 or newer |
| Oven | A June oven running the Project July local server, or connected to June's cloud |
| Network | Home Assistant can reach the oven on the LAN (Project July), or has internet access (June cloud) |
| Pairing access | Physical access to the oven's **Connect** screen |
| Distribution | HACS custom repository or manual installation |

With an oven address configured, Home Assistant talks only to the Project
July server on your network; no internet access is needed. Without an oven
address it uses June's cloud, and monitoring and control depend on that
service, the oven's internet connection, and Home Assistant's internet
connection.

Additional behavior to know:

- Target temperatures range from 100 °F to 500 °F in 5 °F steps.
- Supported cook presets are **Bake**, **Roast**, **Broil**, **Air fry**, and
  **Toast**. A program started on the oven's touchscreen, such as **Proof**,
  is shown as the preset while it runs.
- Changing the temperature during an active cook is applied in place. If the
  oven refuses, a cook started from one of the presets above is cancelled and
  restarted at the new temperature; other programs are left running. Changing
  the cook mode always cancels and restarts the cook.
- The camera is June's native still-image feed, approximately one frame per
  second while cooking. It is not continuous video or recording.
- The integration does not expose June's guided recipes or food-recognition
  features.

## Installation

### Option 1: HACS (recommended)

HACS is not bundled with Home Assistant. If needed, install and configure it
using the [official HACS instructions](https://hacs.xyz/docs/use/download/download/).

#### Add this custom repository

Use the button below and follow the prompt:

[![Open your Home Assistant instance and add this repository to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jclima&repository=ha-june-oven&category=integration)

Or add it manually:

1. Open **HACS** in the Home Assistant sidebar.
2. Open the three-dot menu in the upper-right corner.
3. Select **Custom repositories**.
4. Enter `https://github.com/jclima/ha-june-oven`.
5. Select **Integration** as the category, then select **Add**.
6. Search for **June Oven** and open its details page.
7. Select **Download** and choose the latest release.
8. Restart Home Assistant when HACS reports **Pending restart**.

After restarting, continue with [Pairing the oven](#pairing-the-oven).

### Option 2: Manual installation

1. Download the
   [latest release](https://github.com/jclima/ha-june-oven/releases/latest).
2. Extract the release archive.
3. Copy the extracted `custom_components/june_oven` directory into the
   `custom_components` directory inside your Home Assistant configuration.
4. Confirm the resulting path is:

   ```text
   config/
   └── custom_components/
       └── june_oven/
           ├── __init__.py
           ├── manifest.json
           └── ...
   ```

5. Restart Home Assistant.

Do not copy the repository's outer directory into `custom_components`; Home
Assistant must see `custom_components/june_oven/manifest.json`.

### Updating

With HACS, install the offered update from **Settings → Updates** or select
**Redownload** from the repository menu, then restart Home Assistant.

For a manual installation, replace the existing
`custom_components/june_oven` directory with the directory from the new
release and restart Home Assistant. Do not delete the integration from
**Devices & services** during a normal update; doing so removes its pairing
credentials.

## Pairing the oven

Pairing creates a private June companion identity for Home Assistant.

1. In Home Assistant, open **Settings → Devices & services**.
2. Select **Add integration** and search for **June Oven**.
3. Enter:

   - **Oven name**: the companion and device name, such as `Kitchen June`.
   - **Oven address**: the oven's hostname or IP address, such as
     `192.168.1.75`. Leave empty to use June's cloud. See
     [Project July local server](#project-july-local-server).
   - **Verify TLS certificate** and **CA certificate (PEM)**: how Home
     Assistant trusts the oven's certificate.
   - **Default cook mode**: the mode used when turning the climate entity on.
   - **Default temperature**: the initial target, from 100 °F to 500 °F.

4. On the oven, swipe left twice from the home screen and select **Connect**.
   If connected devices are already listed, select **+**.
5. Enter the eight-digit code shown by Home Assistant.
6. Wait for the oven to accept the pairing.
7. Return to Home Assistant and select **Submit**. If pairing is still being
   processed, wait a few seconds and submit again.

The pairing session expires after approximately five minutes. If it expires,
cancel the Home Assistant flow and start again to receive a new code.

To add another oven, repeat these steps. Each oven receives an independent
companion identity and Home Assistant device.

## Project July local server

[Project July](https://project-july.org) runs `june-local` on the oven itself,
answering the same REST and WebSocket routes June's cloud used. The
integration derives every URL from the one **Oven address**, in the same way
as the Project July phone build:

| Purpose | URL |
| --- | --- |
| REST API and messaging | `https://<address>` |
| WebSocket | `wss://<address>/1/messaging/websocket/companion` |
| Server check | `https://<address>/local/status` |
| Camera stills | `https://<address>/media/...` |

Accepted address forms:

| You enter | Home Assistant uses |
| --- | --- |
| `192.168.1.75` | `https://192.168.1.75` |
| `june-oven.local` | `https://june-oven.local` |
| `192.168.1.75:8443` | `https://192.168.1.75:8443` |
| `fe80::1` | `https://[fe80::1]` |
| `http://192.168.1.75` | `http://192.168.1.75:8080`, the plaintext listener |

Before pairing, and whenever the address changes, Home Assistant checks
`/local/status` and continues only if the server reports `june-local`.

### Trusting the oven's certificate

`june-local` serves a per-install certificate signed by your own CA, which
Home Assistant does not trust by default. Choose one option:

1. **Paste the CA (recommended).** Paste the contents of the `ca.crt` produced
   by `generate_certs.sh` into **CA certificate (PEM)** and keep **Verify TLS
   certificate** on. Home Assistant then trusts only that CA for the oven. The
   oven address must match a `DNS:` or `IP:` name in the leaf certificate
   (`JUNE_HOSTNAME` or `JUNE_IP_SAN` when the certificates were generated).
2. **Turn off Verify TLS certificate.** The connection stays encrypted and
   commands stay signed, but anyone on your network could impersonate the
   oven's server.
3. **Use the plaintext listener** by entering `http://<oven-ip>`. This avoids
   certificates entirely and is not encrypted. Pairing stays SRP-protected
   and commands stay signed.

## Configuration

To change the oven address, certificate settings, default cook mode, or
default temperature:

1. Open **Settings → Devices & services**.
2. Find **June Oven**.
3. Select **Configure**.
4. Change the settings and select **Submit**.

The integration reloads and reconnects immediately. Changing the address,
for example after the oven gets a new IP address, keeps the existing pairing;
you do not need to pair again. Pointing an existing entry at a different
oven's server does not work; add that oven as a new integration instead.

The defaults are used when a cook does not already have a selected target or
mode. They do not automatically start the oven.

## Entities and controls

Entity IDs depend on the name assigned during pairing. Use the entity picker
in Home Assistant instead of relying on the examples below.

| Entity | Type | Purpose |
| --- | --- | --- |
| Oven | Climate | Start or cancel cooking, select a mode, and set target temperature |
| Connectivity | Binary sensor | Reports whether the server says the oven is connected |
| Preheat ready | Binary sensor | Pulses on for 30 seconds when the oven finishes preheating |
| Cook done | Binary sensor | Pulses on for 30 seconds after a cook ends without cancellation |
| Food probe | Sensor | Latest connected probe temperature |
| Cook progress | Sensor | Progress reported by the oven, 0-100%: preheat progress while preheating |
| Cook phase | Sensor | Idle, preheating, preheated (holding temperature for food), or cooking |
| Cook time elapsed | Sensor | Cooking time reported by the oven; empty while preheating |
| Interior | Camera | Latest signed interior-camera still |

### Climate entity

The climate entity provides two HVAC modes:

- **Heat** starts the selected cook preset at the selected target temperature.
- **Off** sends a cook-cancellation command.

Changing the target while the oven is active asks the oven to change the
running cook, keeping its timer and progress. If the oven refuses, a cook
started from a preset is cancelled and restarted at the new target, and any
timer or progress associated with the original cook may be lost. Changing the
preset while the oven is active always cancels and restarts the cook.

While a program started on the oven's touchscreen runs, the climate entity
shows it as the preset. **Heat** starts the configured default mode instead
after such a program ends.

### Ready and done events

**Preheat ready** turns on when the oven reports that preheating finished and
it is holding temperature until food goes in. It fires once per cook.

**Preheat ready** and **Cook done** are deliberately short-lived binary
sensors. Each remains on for 30 seconds so it can trigger an automation, then
resets automatically.

**Cook done** is not emitted when Home Assistant knows the cook was manually
cancelled.

## Automations

Notification-only automations are the safest place to start. Replace the
example entity and notification IDs using Home Assistant's entity and action
pickers.

### Notify when preheating finishes

```yaml
automation:
  - alias: June oven is ready
    triggers:
      - trigger: state
        entity_id: binary_sensor.kitchen_june_preheat_ready
        to: "on"
    actions:
      - action: notify.mobile_app_your_phone
        data:
          title: June oven
          message: The oven has reached its target temperature.
```

### Notify when cooking finishes

```yaml
automation:
  - alias: June oven cook finished
    triggers:
      - trigger: state
        entity_id: binary_sensor.kitchen_june_cook_done
        to: "on"
    actions:
      - action: notify.mobile_app_your_phone
        data:
          title: June oven
          message: The cook has finished.
```

> [!CAUTION]
> Avoid unattended automations that turn the oven on. Conditions, schedules,
> and presence checks can fail or become stale and are not substitutes for
> confirming that the oven is empty, unobstructed, and safe to heat.

## Troubleshooting

### June Oven does not appear when adding an integration

- Confirm the path is exactly
  `config/custom_components/june_oven/manifest.json`.
- Restart Home Assistant after installing or updating the files.
- Check **Settings → System → Logs** for `june_oven` or manifest errors.
- If installed with HACS, confirm the repository is downloaded and no longer
  shows **Pending restart**.

### The pairing code is rejected or pairing times out

- Confirm the oven is online, idle, and closed.
- Start pairing from the oven's **Connect** screen before entering the code.
- Enter all eight digits, including any leading zero.
- Use the newest code shown in Home Assistant; codes and pairing sessions
  expire.
- If Home Assistant says the oven has not finished pairing, wait several
  seconds and select **Submit** again.
- If the flow was closed or Home Assistant restarted, begin pairing again.

### Setup reports a connection or certificate problem

- Open `http://<oven-ip>:8080/local` from a device on the same network. It
  should say `june-local` is running.
- **Could not connect**: check the address and that Home Assistant can
  reach the oven, for example that it is not on an isolated VLAN or guest
  network.
- **Not a Project July local server**: something else answered at that
  address. Check for a typo or a changed IP address.
- **Certificate not trusted**: paste the CA from the same install as the
  oven's certificate, and enter the address exactly as it appears in the
  certificate. For example, a certificate generated with only
  `JUNE_HOSTNAME=oven.local` does not match `192.168.1.75`.

### Entities are unavailable

- Confirm the oven itself reports that it is connected to Wi-Fi.
- With an oven address, confirm the oven's IP address has not changed. If it
  has, update it under **Configure**. Consider a DHCP reservation for the oven.
- Without an oven address, confirm Home Assistant has working internet
  access and check whether June's cloud or API is unavailable.
- Reload the integration from **Settings → Devices & services → June Oven**.
- Download diagnostics and inspect the connection state before opening an
  issue.

### A temperature or mode change restarted cooking

A mode change always restarts the cook. A temperature change restarts it only
when the oven refuses to change the running cook in place.

### The interior camera is blank

- The oven normally publishes camera frames only while actively cooking.
- Signed camera URLs expire and are refreshed through live June messages.
- Confirm the climate entity is active and the oven is online.
- Reload the integration if telemetry is working but the camera remains stale.

### A command timed out

The integration waits for June to acknowledge heating and cancellation
commands. Confirm the oven is online and inspect Home Assistant logs before
retrying. Avoid repeatedly sending a heating command when the oven's state is
uncertain.

## Diagnostics, privacy, and security

Download diagnostics from the June Oven integration page under
**Settings → Devices & services**. Diagnostics redact:

- access and refresh tokens;
- the companion password;
- the command-signing seed;
- the built-in client secret; and
- signed camera URLs.

Diagnostics can still contain state and configuration details. Review the file
before sharing it publicly.

The integration stores a companion password, access tokens, and an Ed25519
signing seed in Home Assistant's config-entry storage. Anyone with these
values may be able to control the oven. Protect Home Assistant backups,
diagnostic downloads, and the `.storage` directory.

Do not post pairing codes, tokens, oven IDs, camera URLs, or unredacted
backups in GitHub issues. Follow [SECURITY.md](SECURITY.md) for vulnerability
reports.

## Removing the integration

1. Open **Settings → Devices & services**.
2. Find **June Oven**, open its menu, and select **Delete**.
3. On the oven, open its connected-devices or companions screen and remove the
   Home Assistant companion.
4. If installed with HACS, remove the repository from HACS and restart Home
   Assistant.
5. For a manual installation, remove
   `config/custom_components/june_oven` and restart Home Assistant.

Deleting the Home Assistant integration does not revoke its companion identity
from June's servers. Removing the companion on the oven is the revocation
step.

## Development and contributing

Clone the repository and install the protocol test dependency and Ruff:

```bash
python3 -m pip install PyNaCl==1.6.2 ruff
```

Run the local checks:

```bash
ruff format --check custom_components tests
ruff check custom_components tests
python3 -m compileall -q custom_components tests
python3 -m unittest discover -s tests -v
```

GitHub Actions additionally runs HACS and Hassfest validation. Full config-flow
and entity tests should run inside a Home Assistant development environment.
Pairing, heating, cancellation, telemetry, and camera changes must state
whether they were verified on a physical oven.

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

For bugs, use the
[issue tracker](https://github.com/jclima/ha-june-oven/issues) and attach only
redacted diagnostics. This project is maintained independently; do not report
integration bugs to HACS, Home Assistant, June, or the upstream Homebridge
project.

## Support the project

If this integration is useful to you, you can support its continued
development and maintenance:

<a href="https://buymeacoffee.com/jclima"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" width="217"></a>

## Provenance and license

The protocol work is derived from Keith Herrington's MIT-licensed
[`homebridge-june-oven`](https://github.com/keithah/homebridge-june-oven) and
its
[`JUNE_INTEGRATION_SPEC.md`](https://github.com/keithah/homebridge-june-oven/blob/main/docs/reference/JUNE_INTEGRATION_SPEC.md).
See [NOTICE.md](NOTICE.md) for exact attribution.

This project is licensed under the [MIT License](LICENSE). It is independent
and is not affiliated with or endorsed by June Life, Weber, Home Assistant, or
the upstream Homebridge project.
