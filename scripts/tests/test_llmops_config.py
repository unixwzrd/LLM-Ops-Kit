#!/usr/bin/env python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from llmops_kit.llmops_config import ConfigError, load_config, update_display
from llmops_kit.llmops_paths import resolve_paths


class LlmOpsConfigTests(unittest.TestCase):
    def test_missing_config_returns_minimum_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_paths({"HOME": str(Path(tmp) / "home")})
            config = load_config(paths=paths)
            self.assertFalse(config.exists)
            self.assertEqual(config.schema_version, 1)
            self.assertEqual(config.data["secrets"]["provider"], "env")

    def test_valid_config_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "secrets": {
                            "provider": "none",
                        },
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(config_path)
            self.assertTrue(config.exists)
            self.assertEqual(config.data["secrets"]["provider"], "none")
            self.assertEqual(config.data["runtime"], {})

    def test_invalid_json_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text("{not valid json", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(config_path)

    def test_invalid_secret_provider_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "secrets": {
                            "provider": "required-seckit",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_config(config_path)

    def test_display_metadata_is_transactional_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text('{"schema_version": 1}\n', encoding="utf-8")
            backup = update_display(config_path, organization="Example", site="Lab")
            self.assertTrue(backup.is_file())
            self.assertEqual(load_config(config_path).data["display"], {"organization": "Example", "site": "Lab"})


if __name__ == "__main__":
    unittest.main()
