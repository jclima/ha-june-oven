"""Diagnostics for June Oven."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_SECRET,
    CONF_ED25519_SEED_HEX,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
)
from .coordinator import JuneDataUpdateCoordinator

TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_SECRET,
    CONF_ED25519_SEED_HEX,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return credentials-safe diagnostics."""
    coordinator: JuneDataUpdateCoordinator = entry.runtime_data
    state = asdict(coordinator.data)
    if state.get("snapshot_url"):
        state["snapshot_url"] = "**REDACTED**"
    return {
        "config_entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "state": state,
        "last_update_success": coordinator.last_update_success,
    }
