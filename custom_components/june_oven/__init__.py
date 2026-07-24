"""June Oven integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import JuneClient, JuneError, JuneIdentity
from .const import PLATFORMS
from .coordinator import JuneDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up June Oven from a config entry."""
    identity = JuneIdentity.from_mapping(entry.data)

    def save_tokens(updated: JuneIdentity) -> None:
        data: dict[str, Any] = {**entry.data, **updated.as_dict()}
        hass.config_entries.async_update_entry(entry, data=data)

    client = JuneClient(
        async_get_clientsession(hass),
        identity,
        token_callback=save_tokens,
    )
    coordinator = JuneDataUpdateCoordinator(hass, client)

    try:
        await client.async_refresh_token()
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        await client.async_stop()
        raise
    except JuneError as err:
        await client.async_stop()
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = coordinator
    client.async_start_websocket()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a June Oven config entry."""
    coordinator: JuneDataUpdateCoordinator = entry.runtime_data
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await coordinator.async_shutdown()
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after options change."""
    await hass.config_entries.async_reload(entry.entry_id)
