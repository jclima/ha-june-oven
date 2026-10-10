"""June Oven integration."""

from __future__ import annotations

import logging
import ssl
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import JuneClient, JuneError, JuneIdentity, create_ssl_option
from .const import CONF_CA_CERT, CONF_ENDPOINT, CONF_VERIFY_SSL, PLATFORMS
from .coordinator import JuneDataUpdateCoordinator
from .protocol import build_endpoints

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up June Oven from a config entry."""
    identity = JuneIdentity.from_mapping(entry.data)
    # Connection settings chosen during setup may be changed later in options.
    config = {**entry.data, **entry.options}
    try:
        endpoints = build_endpoints(str(config.get(CONF_ENDPOINT, "")))
        ssl_option = await hass.async_add_executor_job(
            create_ssl_option,
            bool(config.get(CONF_VERIFY_SSL, True)),
            str(config.get(CONF_CA_CERT, "")),
        )
    except (ssl.SSLError, ValueError) as err:
        raise ConfigEntryError(f"Invalid server settings: {err}") from err

    def save_tokens(updated: JuneIdentity) -> None:
        data: dict[str, Any] = {**entry.data, **updated.as_dict()}
        hass.config_entries.async_update_entry(entry, data=data)

    client = JuneClient(
        async_get_clientsession(hass),
        identity,
        endpoints=endpoints,
        ssl_option=ssl_option,
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
