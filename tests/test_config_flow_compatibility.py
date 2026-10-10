"""Config-flow compatibility tests against supported Home Assistant releases."""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "june_oven"
HAS_HOME_ASSISTANT = importlib.util.find_spec("homeassistant") is not None

USER_INPUT = {
    "device_name": "Home Assistant",
    "verify_ssl": True,
    "default_mode": "bake",
    "default_temp_f": 350,
}


def _forget_custom_components() -> None:
    """Drop the cached custom_components package and its submodules.

    Home Assistant imports custom_components once per process and then scans
    the cached package's __path__, which would still point at an earlier
    test's deleted config directory.
    """
    for name in list(sys.modules):
        if name == "custom_components" or name.startswith("custom_components."):
            del sys.modules[name]


@unittest.skipUnless(HAS_HOME_ASSISTANT, "Home Assistant is not installed")
class ConfigFlowCompatibilityTest(unittest.IsolatedAsyncioTestCase):
    """Exercise requirement installation and the first config-flow step."""

    @asynccontextmanager
    async def _hass(self) -> AsyncIterator[Any]:
        """Load the integration exactly as Home Assistant does from config."""
        from homeassistant.config_entries import ConfigEntries
        from homeassistant.core import HomeAssistant
        from homeassistant.loader import async_setup as async_setup_loader

        with tempfile.TemporaryDirectory() as config_dir:
            custom_components = Path(config_dir) / "custom_components"
            custom_components.mkdir()
            shutil.copytree(INTEGRATION, custom_components / "june_oven")

            _forget_custom_components()
            hass = HomeAssistant(config_dir)
            async_setup_loader(hass)
            hass.config_entries = ConfigEntries(hass, {})
            await hass.config_entries.async_initialize()
            await hass.async_start()
            try:
                yield hass
            finally:
                await hass.async_stop(force=True)
                _forget_custom_components()

    async def _start_user_flow(self, hass: Any) -> dict[str, Any]:
        from homeassistant.config_entries import SOURCE_USER

        return await hass.config_entries.flow.async_init(
            "june_oven",
            context={"source": SOURCE_USER},
        )

    async def test_user_step_loads(self) -> None:
        from homeassistant.data_entry_flow import FlowResultType

        async with self._hass() as hass:
            result = await self._start_user_flow(hass)
            self.assertEqual(result["type"], FlowResultType.FORM)
            self.assertEqual(result["step_id"], "user")
            self.assertFalse(result["errors"])

    async def test_invalid_endpoint_is_rejected(self) -> None:
        from homeassistant.data_entry_flow import FlowResultType

        async with self._hass() as hass:
            result = await self._start_user_flow(hass)
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {**USER_INPUT, "endpoint": "oven local"}
            )
            self.assertEqual(result["type"], FlowResultType.FORM)
            self.assertEqual(result["errors"], {"endpoint": "invalid_endpoint"})

    async def test_unreachable_endpoint_cannot_connect(self) -> None:
        from aiohttp import ClientSession
        from homeassistant.data_entry_flow import FlowResultType

        async with self._hass() as hass, ClientSession() as session:
            result = await self._start_user_flow(hass)
            # Home Assistant's shared session needs components a bare test
            # instance does not load, so the flow gets a plain session.
            with patch(
                "custom_components.june_oven.config_flow.async_get_clientsession",
                return_value=session,
            ):
                result = await hass.config_entries.flow.async_configure(
                    result["flow_id"], {**USER_INPUT, "endpoint": "127.0.0.1:1"}
                )
            self.assertEqual(result["type"], FlowResultType.FORM)
            self.assertEqual(result["errors"], {"base": "cannot_connect"})


if __name__ == "__main__":
    unittest.main()
