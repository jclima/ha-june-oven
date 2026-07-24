# June Oven for Home Assistant

[![Release](https://img.shields.io/github/v/release/jclima/ha-june-oven)](https://github.com/jclima/ha-june-oven/releases)
[![Validate](https://github.com/jclima/ha-june-oven/actions/workflows/validate.yml/badge.svg)](https://github.com/jclima/ha-june-oven/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/github/license/jclima/ha-june-oven)](LICENSE)
[![Home Assistant 2025.1+](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5)](https://www.home-assistant.io/)

An unofficial Home Assistant custom integration for pairing with, monitoring,
and controlling June ovens. It communicates directly with June's cloud as a
paired companion—no Homebridge, Apple HomeKit, June account login, or
extracted app credentials required.

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
- Food-probe temperature and cook-progress sensors.
- Interior-camera snapshots while the oven is cooking.
- Live WebSocket telemetry with a periodic cloud-status fallback.
- Signed command acknowledgements, automatic token renewal, and reconnects.
- Multiple ovens by adding the integration once per oven.
- Downloadable diagnostics with credentials and camera URLs redacted.

## Requirements and limitations

| Requirement | Details |
| --- | --- |
| Home Assistant | Version 2025.1 or newer |
| Oven | A June oven connected to Wi-Fi and June's cloud |
| Network | Outbound internet access from Home Assistant |
| Pairing access | Physical access to the oven's **Connect** screen |
| Distribution | HACS custom repository or manual installation |

This is a cloud-push integration, not local-LAN control. If June's cloud, the
oven's internet connection, or Home Assistant's internet connection is
unavailable, monitoring and control will be unavailable.

Additional behavior to know:

- Target temperatures range from 100 °F to 500 °F in 5 °F steps.
- Supported cook presets are **Bake**, **Roast**, **Broil**, **Air fry**, and
  **Toast**.
- Changing the temperature or cook mode during an active cook cancels and
  restarts that cook because the oven does not reliably apply those changes
  in place.
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

## Configuration

To change the default cook mode or temperature:

1. Open **Settings → Devices & services**.
2. Find **June Oven**.
3. Select **Configure**.
4. Choose the new defaults and select **Submit**.

The defaults are used when a cook does not already have a selected target or
mode. They do not automatically start the oven.

## Entities and controls

Entity IDs depend on the name assigned during pairing. Use the entity picker
in Home Assistant instead of relying on the examples below.

| Entity | Type | Purpose |
| --- | --- | --- |
| Oven | Climate | Start or cancel cooking, select a mode, and set target temperature |
| Connectivity | Binary sensor | Reports whether June's cloud says the oven is online |
| Preheat ready | Binary sensor | Pulses on for 30 seconds when the oven reaches temperature |
| Cook done | Binary sensor | Pulses on for 30 seconds after a cook ends without cancellation |
| Food probe | Sensor | Latest connected probe temperature |
| Cook progress | Sensor | Native cook progress reported by the oven |
| Interior | Camera | Latest signed interior-camera still |

### Climate entity

The climate entity provides two HVAC modes:

- **Heat** starts the selected cook preset at the selected target temperature.
- **Off** sends a cook-cancellation command.

Changing the preset or target while the oven is active sends a cancellation,
waits briefly, and starts a replacement cook. Any timer or progress associated
with the original cook may be lost.

### Ready and done events

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

### Entities are unavailable

- Confirm the oven itself reports that it is connected to Wi-Fi.
- Confirm Home Assistant has working internet access.
- Check whether June's cloud or API is unavailable.
- Reload the integration from **Settings → Devices & services → June Oven**.
- Download diagnostics and inspect the connection state before opening an
  issue.

### A temperature or mode change restarted cooking

This is expected. June does not reliably apply in-place changes to an active
cook, so the integration cancels and restarts it with the new settings.

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
