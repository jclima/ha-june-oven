# June Oven for Home Assistant

A Home Assistant custom integration for pairing with and controlling June
ovens directly through June's cloud protocol. It does not require Homebridge,
Apple HomeKit, a June account login, or extracted app credentials.

> [!WARNING]
> This integration can start a real heating appliance remotely. Begin testing
> at a low temperature, keep the oven clear, and verify that `Turn off` works
> before creating automations.

## Features

- Pair from Home Assistant using the same eight-digit code flow as the June app.
- Climate entity with current temperature, target temperature, on/off, and
  cook-mode presets.
- Online, preheat-ready, and cook-done binary sensors.
- Food-probe temperature and cook-progress sensors.
- Interior-camera snapshots while the oven is cooking.
- Automatic token renewal, WebSocket reconnect, live telemetry, and command
  acknowledgements.
- Multiple ovens by adding the integration once per oven.
- Downloadable diagnostics with credentials and tokens redacted.

## Requirements and limitations

- Home Assistant 2025.1 or newer.
- A supported June oven connected to Wi-Fi and June's cloud.
- This uses an unofficial, reverse-engineered cloud API. June or Weber can
  change or discontinue it without notice.
- This is cloud control, not local-LAN control.
- The camera is the oven's native approximately one-frame-per-second still
  feed, not continuous video or recording.
- Changing the target of an active cook cancels and restarts that cook because
  the oven does not reliably apply in-place temperature changes.

## Installation with HACS

Until the repository is included in HACS defaults:

1. Open HACS.
2. Select **Integrations**.
3. Open the menu and choose **Custom repositories**.
4. Add `https://github.com/jclima/ha-june-oven` as an **Integration**.
5. Install **June Oven** and restart Home Assistant.

## Manual installation

Copy `custom_components/june_oven` into your Home Assistant configuration:

```text
config/
└── custom_components/
    └── june_oven/
```

Restart Home Assistant after copying the files.

## Pairing

1. In Home Assistant, open **Settings → Devices & services**.
2. Select **Add integration**, then search for **June Oven**.
3. Enter a friendly name and choose the default cook mode and temperature.
4. On the oven, swipe left twice from the home screen and select **Connect**.
   If connected devices are already listed, select **+**.
5. Enter the eight-digit code shown by Home Assistant.
6. Wait for the oven to finish pairing, then select **Finish pairing**.

The integration stores a companion password, token, and Ed25519 signing seed
inside Home Assistant's config-entry storage. Anyone with those values can
control the oven. Protect Home Assistant backups accordingly.

Removing the integration does not revoke the companion on June's servers.
Remove the companion from the oven's connected-devices screen as well.

## Entities

| Entity | Purpose |
| --- | --- |
| Climate | Start, stop, select a cook mode, and set target temperature |
| Connectivity | Reports whether June's cloud says the oven is online |
| Preheat ready | Pulses on for 30 seconds when the oven reaches temperature |
| Cook done | Pulses on for 30 seconds after a cook ends without cancellation |
| Food probe | Latest connected probe temperature |
| Cook progress | Native cook progress reported by the oven |
| Camera | Latest signed interior-camera still |

Ready and done entities can trigger any Home Assistant notification or
automation. For example:

```yaml
automation:
  - alias: June oven is ready
    triggers:
      - trigger: state
        entity_id: binary_sensor.june_oven_preheat_ready
        to: "on"
    actions:
      - action: notify.mobile_app_your_phone
        data:
          title: June oven
          message: The oven is ready.
```

## Sharing and release checklist

1. Create a public repository named `ha-june-oven` under `jclima`.
2. Push this directory as the repository root.
3. Enable Issues and add repository topics such as `home-assistant`, `hacs`,
   `june-oven`, and `custom-integration`.
4. Confirm the HACS, Hassfest, and Python checks pass.
5. Create a GitHub release tagged `v0.1.0`.
6. Add the repository to HACS as a custom repository for device testing.
7. Add icon and logo assets through the Home Assistant brands repository,
   then remove the temporary `brands` validation exception.
8. Only request inclusion in HACS defaults after real-oven validation.

## Development

Protocol-only checks do not require Home Assistant:

```bash
python3 -m compileall -q custom_components tests
python3 -m unittest discover -s tests -v
```

Full config-flow and entity tests should run inside a Home Assistant development
environment. Pairing and cooking commands require a physical oven.

## Provenance and license

The protocol work comes from Keith Herrington's
[`homebridge-june-oven`](https://github.com/keithah/homebridge-june-oven)
and its
[`JUNE_INTEGRATION_SPEC.md`](https://github.com/keithah/homebridge-june-oven/blob/main/docs/reference/JUNE_INTEGRATION_SPEC.md).
See [NOTICE.md](NOTICE.md) for exact attribution.

MIT licensed. This project is independent and is not affiliated with June
Life, Weber, Home Assistant, or the upstream Homebridge project.
