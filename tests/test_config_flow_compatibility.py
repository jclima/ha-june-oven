"""Config-flow compatibility tests against supported Home Assistant releases."""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "june_oven"
HAS_HOME_ASSISTANT = importlib.util.find_spec("homeassistant") is not None


@unittest.skipUnless(HAS_HOME_ASSISTANT, "Home Assistant is not installed")
class ConfigFlowCompatibilityTest(unittest.IsolatedAsyncioTestCase):
    """Exercise requirement installation and the first config-flow step."""

    async def test_user_step_loads(self) -> None:
        """Load the integration exactly as Home Assistant does from config."""
        from homeassistant.config_entries import SOURCE_USER, ConfigEntries
        from homeassistant.core import HomeAssistant
        from homeassistant.data_entry_flow import FlowResultType
        from homeassistant.loader import async_setup as async_setup_loader

        with tempfile.TemporaryDirectory() as config_dir:
            custom_components = Path(config_dir) / "custom_components"
            custom_components.mkdir()
            shutil.copytree(INTEGRATION, custom_components / "june_oven")

            hass = HomeAssistant(config_dir)
            async_setup_loader(hass)
            hass.config_entries = ConfigEntries(hass, {})
            await hass.config_entries.async_initialize()
            await hass.async_start()
            try:
                result = await hass.config_entries.flow.async_init(
                    "june_oven",
                    context={"source": SOURCE_USER},
                )
                self.assertEqual(result["type"], FlowResultType.FORM)
                self.assertEqual(result["step_id"], "user")
                self.assertFalse(result["errors"])
            finally:
                await hass.async_stop(force=True)


if __name__ == "__main__":
    unittest.main()
