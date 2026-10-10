"""Config flow for June Oven."""

from __future__ import annotations

import ssl
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
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
    JuneCertificateError,
    JuneError,
    JuneNotLocalServerError,
    JunePairingNotReady,
    JunePairingSession,
    SSLOption,
    async_check_local_server,
    create_ssl_option,
)
from .const import (
    CONF_CA_CERT,
    CONF_DEFAULT_MODE,
    CONF_DEFAULT_TEMP_F,
    CONF_DEVICE_NAME,
    CONF_ENDPOINT,
    CONF_VERIFY_SSL,
    DEFAULT_DEVICE_NAME,
    DEFAULT_MODE,
    DEFAULT_MODES,
    DEFAULT_TEMP_F,
    DOMAIN,
    MAX_TEMP_F,
    MIN_TEMP_F,
    normalize_mode,
)
from .protocol import JuneEndpoints, build_endpoints, normalize_endpoint

MODE_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=list(DEFAULT_MODES),
        mode=SelectSelectorMode.DROPDOWN,
        translation_key="cook_mode",
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
ENDPOINT_SELECTOR = TextSelector(TextSelectorConfig())
CA_CERT_SELECTOR = TextSelector(TextSelectorConfig(multiline=True))
VERIFY_SSL_SELECTOR = BooleanSelector()
# Home Assistant discourages URLs inside translation strings.
SERVER_PLACEHOLDERS = {"http_prefix": "http://"}


def _server_fields(
    *,
    endpoint: str = "",
    verify_ssl: bool = True,
    ca_cert: str = "",
) -> dict[vol.Marker, Any]:
    # Suggested values rather than defaults, so clearing a field clears it.
    return {
        vol.Optional(
            CONF_ENDPOINT, description={"suggested_value": endpoint}
        ): ENDPOINT_SELECTOR,
        vol.Required(CONF_VERIFY_SSL, default=verify_ssl): VERIFY_SSL_SELECTOR,
        vol.Optional(
            CONF_CA_CERT, description={"suggested_value": ca_cert}
        ): CA_CERT_SELECTOR,
    }


def _settings_schema(
    *,
    device_name: str = DEFAULT_DEVICE_NAME,
    default_mode: str = DEFAULT_MODE,
    default_temp_f: float = DEFAULT_TEMP_F,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_DEVICE_NAME, default=device_name): NAME_SELECTOR,
            **_server_fields(),
            vol.Required(CONF_DEFAULT_MODE, default=default_mode): MODE_SELECTOR,
            vol.Required(CONF_DEFAULT_TEMP_F, default=default_temp_f): TEMP_SELECTOR,
        }
    )


def _options_schema(
    *,
    default_mode: str = DEFAULT_MODE,
    default_temp_f: float = DEFAULT_TEMP_F,
    endpoint: str = "",
    verify_ssl: bool = True,
    ca_cert: str = "",
) -> vol.Schema:
    return vol.Schema(
        {
            **_server_fields(endpoint=endpoint, verify_ssl=verify_ssl, ca_cert=ca_cert),
            vol.Required(CONF_DEFAULT_MODE, default=default_mode): MODE_SELECTOR,
            vol.Required(CONF_DEFAULT_TEMP_F, default=default_temp_f): TEMP_SELECTOR,
        }
    )


class _ServerSettingsError(Exception):
    """A server setting was rejected; ``field`` names the form field."""

    def __init__(self, field: str, error: str) -> None:
        super().__init__(error)
        self.field = field
        self.error = error


async def _async_server_settings(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> tuple[dict[str, Any], JuneEndpoints, SSLOption]:
    """Normalize the server settings and confirm a local server answers."""
    try:
        endpoint = normalize_endpoint(str(user_input.get(CONF_ENDPOINT) or ""))
    except ValueError as err:
        raise _ServerSettingsError(CONF_ENDPOINT, "invalid_endpoint") from err
    settings: dict[str, Any] = {
        CONF_ENDPOINT: endpoint,
        CONF_VERIFY_SSL: bool(user_input.get(CONF_VERIFY_SSL, True)),
        CONF_CA_CERT: str(user_input.get(CONF_CA_CERT) or "").strip(),
    }
    try:
        ssl_option = await hass.async_add_executor_job(
            create_ssl_option, settings[CONF_VERIFY_SSL], settings[CONF_CA_CERT]
        )
    except (ssl.SSLError, ValueError) as err:
        raise _ServerSettingsError(CONF_CA_CERT, "invalid_ca_cert") from err

    endpoints = build_endpoints(endpoint)
    if endpoints.local:
        try:
            await async_check_local_server(
                async_get_clientsession(hass), endpoints, ssl_option
            )
        except JuneCertificateError as err:
            raise _ServerSettingsError("base", "certificate_error") from err
        except JuneNotLocalServerError as err:
            raise _ServerSettingsError(CONF_ENDPOINT, "not_local_server") from err
        except JuneError as err:
            raise _ServerSettingsError("base", "cannot_connect") from err
    return settings, endpoints, ssl_option


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
            try:
                server, endpoints, ssl_option = await _async_server_settings(
                    self.hass, user_input
                )
            except _ServerSettingsError as err:
                errors[err.field] = err.error
            else:
                self._settings = {**user_input, **server}
                self._pairing = JunePairingSession(
                    async_get_clientsession(self.hass),
                    str(user_input[CONF_DEVICE_NAME]),
                    self.hass.config.time_zone,
                    endpoints=endpoints,
                    ssl_option=ssl_option,
                )
                try:
                    await self._pairing.async_begin()
                except JuneCertificateError:
                    errors["base"] = "certificate_error"
                except JuneError:
                    errors["base"] = "cannot_connect"
                else:
                    return await self.async_step_pair()

        schema = _settings_schema()
        if user_input:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders=SERVER_PLACEHOLDERS,
        )

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
    """Configure the server address and default cook behavior."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage June Oven options."""
        errors: dict[str, str] = {}
        values = {**self._entry.data, **self._entry.options}
        if user_input is not None:
            try:
                server, _, _ = await _async_server_settings(self.hass, user_input)
            except _ServerSettingsError as err:
                errors[err.field] = err.error
                # Cleared optional fields are omitted from the submission.
                values = {**values, CONF_ENDPOINT: "", CONF_CA_CERT: "", **user_input}
            else:
                return self.async_create_entry(title="", data={**user_input, **server})

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                default_mode=normalize_mode(values.get(CONF_DEFAULT_MODE)),
                default_temp_f=float(values.get(CONF_DEFAULT_TEMP_F, DEFAULT_TEMP_F)),
                endpoint=str(values.get(CONF_ENDPOINT, "")),
                verify_ssl=bool(values.get(CONF_VERIFY_SSL, True)),
                ca_cert=str(values.get(CONF_CA_CERT, "")),
            ),
            errors=errors,
            description_placeholders=SERVER_PLACEHOLDERS,
        )
