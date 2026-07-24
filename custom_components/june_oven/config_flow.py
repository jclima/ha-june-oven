"""Config flow for June Oven."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .api import (
    JuneError,
    JunePairingNotReady,
    JunePairingSession,
)
from .const import (
    CONF_DEFAULT_MODE,
    CONF_DEFAULT_TEMP_F,
    CONF_DEVICE_NAME,
    DEFAULT_DEVICE_NAME,
    DEFAULT_MODE,
    DEFAULT_MODES,
    DEFAULT_TEMP_F,
    DOMAIN,
    MAX_TEMP_F,
    MIN_TEMP_F,
)

MODE_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=list(DEFAULT_MODES),
        mode=SelectSelectorMode.DROPDOWN,
    )
)
TEMP_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=MIN_TEMP_F,
        max=MAX_TEMP_F,
        step=5,
        unit_of_measurement="°F",
        mode=NumberSelectorMode.BOX,
    )
)
NAME_SELECTOR = TextSelector(TextSelectorConfig())


def _settings_schema(
    *,
    device_name: str = DEFAULT_DEVICE_NAME,
    default_mode: str = DEFAULT_MODE,
    default_temp_f: float = DEFAULT_TEMP_F,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_DEVICE_NAME, default=device_name): NAME_SELECTOR,
            vol.Required(CONF_DEFAULT_MODE, default=default_mode): MODE_SELECTOR,
            vol.Required(CONF_DEFAULT_TEMP_F, default=default_temp_f): TEMP_SELECTOR,
        }
    )


def _options_schema(
    *,
    default_mode: str = DEFAULT_MODE,
    default_temp_f: float = DEFAULT_TEMP_F,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_DEFAULT_MODE, default=default_mode): MODE_SELECTOR,
            vol.Required(CONF_DEFAULT_TEMP_F, default=default_temp_f): TEMP_SELECTOR,
        }
    )


class JuneOvenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a June Oven config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._pairing: JunePairingSession | None = None
        self._settings: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect preferences and begin direct oven pairing."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._settings = user_input
            self._pairing = JunePairingSession(
                async_get_clientsession(self.hass),
                str(user_input[CONF_DEVICE_NAME]),
                self.hass.config.time_zone,
            )
            try:
                await self._pairing.async_begin()
            except JuneError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_pair()

        schema = _settings_schema()
        if user_input:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wait for the oven to accept the displayed PIN."""
        if self._pairing is None or self._pairing.shown_code is None:
            return self.async_abort(reason="pairing_lost")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                identity = await self._pairing.async_wait_paired()
            except JunePairingNotReady:
                errors["base"] = "not_paired_yet"
            except JuneError:
                errors["base"] = "pairing_failed"
            else:
                await self.async_set_unique_id(identity.oven_id)
                self._abort_if_unique_id_configured()
                data = {**identity.as_dict(), **self._settings}
                return self.async_create_entry(
                    title=str(self._settings[CONF_DEVICE_NAME]),
                    data=data,
                )

        return self.async_show_form(
            step_id="pair",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={
                "code": (
                    f"{self._pairing.shown_code[:4]} {self._pairing.shown_code[4:]}"
                )
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Return the options flow."""
        return JuneOvenOptionsFlow(config_entry)


class JuneOvenOptionsFlow(OptionsFlow):
    """Configure default cook behavior."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage June Oven options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        values = {**self._entry.data, **self._entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                default_mode=str(values.get(CONF_DEFAULT_MODE, DEFAULT_MODE)),
                default_temp_f=float(values.get(CONF_DEFAULT_TEMP_F, DEFAULT_TEMP_F)),
            ),
        )
