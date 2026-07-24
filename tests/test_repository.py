"""Repository-shape tests for a shareable HACS integration."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "june_oven"


class RepositoryShapeTest(unittest.TestCase):
    """Check metadata and localization without importing Home Assistant."""

    def test_hacs_has_exactly_one_integration(self) -> None:
        directories = [
            path
            for path in (ROOT / "custom_components").iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ]
        self.assertEqual(directories, [INTEGRATION])

    def test_manifest_required_fields(self) -> None:
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        for key in (
            "codeowners",
            "config_flow",
            "documentation",
            "domain",
            "integration_type",
            "iot_class",
            "issue_tracker",
            "name",
            "requirements",
            "version",
        ):
            self.assertIn(key, manifest)
        self.assertEqual(manifest["domain"], INTEGRATION.name)
        self.assertTrue(manifest["config_flow"])

    def test_english_translation_matches_strings(self) -> None:
        strings = json.loads((INTEGRATION / "strings.json").read_text())
        english = json.loads((INTEGRATION / "translations" / "en.json").read_text())
        self.assertEqual(strings, english)


if __name__ == "__main__":
    unittest.main()
