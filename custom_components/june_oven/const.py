"""Constants for the June Oven integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "june_oven"

CONF_ACCESS_TOKEN: Final = "access_token"
CONF_CA_CERT: Final = "ca_cert"
CONF_CLIENT_ID: Final = "client_id"
CONF_CLIENT_SECRET: Final = "client_secret"
CONF_DEFAULT_MODE: Final = "default_mode"
CONF_DEFAULT_TEMP_F: Final = "default_temp_f"
CONF_DEVICE_ID: Final = "device_id"
CONF_DEVICE_NAME: Final = "device_name"
CONF_ED25519_SEED_HEX: Final = "ed25519_seed_hex"
CONF_ENDPOINT: Final = "endpoint"
CONF_OVEN_ID: Final = "oven_id"
CONF_PASSWORD: Final = "password"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_VERIFY_SSL: Final = "verify_ssl"

DEFAULT_DEVICE_NAME: Final = "Home Assistant"
DEFAULT_MODE: Final = "bake"
DEFAULT_TEMP_F: Final = 350
# Cook primitives sent as 11002 ``primitive_type``; names match the June app.
DEFAULT_MODES: Final[tuple[str, ...]] = (
    "bake",
    "roast",
    "broil",
    "airfry",
    "toast",
)
# Earlier releases stored air fry as "air-fry"; the June app sends "airfry".
LEGACY_MODES: Final[dict[str, str]] = {"air-fry": "airfry"}

MIN_TEMP_F: Final = 100
MAX_TEMP_F: Final = 500
POLL_INTERVAL_SECONDS: Final = 60

PLATFORMS: Final[tuple[str, ...]] = (
    "binary_sensor",
    "camera",
    "climate",
    "sensor",
)

ATTRIBUTION: Final = "Data provided by June's unofficial cloud API via ha-june-oven"


def normalize_mode(mode: object) -> str:
    """Return a stored default cook mode as a current primitive."""
    value = LEGACY_MODES.get(str(mode), str(mode))
    return value if value in DEFAULT_MODES else DEFAULT_MODE
