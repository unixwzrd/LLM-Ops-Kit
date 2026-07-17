#!/usr/bin/env python3
"""Tests for canonical profile resolution and one-way migration."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))

from llmops_migration import MigrationError, migrate
from llmops_paths import resolve_paths
from llmops_profiles import ProfileError, load_profile, model_values, service_values


class ProfileTests(unittest.TestCase):
    def test_profile_loader_never_falls_back_to_repository_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = resolve_paths({"HOME": temporary})
            with self.assertRaisesRegex(ProfileError, "profile not found"):
                load_profile("model", "Qwen3", paths=paths)

    def test_structured_model_profile_resolves_runtime_values(self) -> None:
        values = model_values(
            {
                "schema_version": 1,
                "name": "chat",
                "type": "llm",
                "model_path": "/models/chat.gguf",
                "runtime": {"host": "127.0.0.1", "port": 11434},
                "llama": {"ctx_size": 32768, "use_mlock": True},
                "server": {"cache_prompt": True, "extra_flags": ["--metrics"]},
            }
        )
        self.assertEqual(values["MODEL"], "/models/chat.gguf")
        self.assertEqual(values["MODEL_PROFILE"], "chat")
        self.assertEqual(values["PORT"], "11434")
        self.assertEqual(values["USE_MLOCK"], "1")
        self.assertEqual(values["EXTRA_FLAGS"], "--metrics")

    def test_service_environment_is_explicit_json(self) -> None:
        self.assertEqual(
            service_values("model-proxy", {"environment": {"MODEL_PROXY_LISTEN_PORT": 11434}}),
            {"MODEL_PROXY_LISTEN_PORT": "11434"},
        )


class MigrationTests(unittest.TestCase):
    def test_migration_is_one_way_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / "legacy"
            (legacy / "config").mkdir(parents=True)
            (legacy / "config.env").write_text("HOST=127.0.0.1\n", encoding="utf-8")
            (legacy / "config" / "chat.env").write_text(
                "MODEL=/models/chat.gguf\nPORT=11434\n",
                encoding="utf-8",
            )
            paths = resolve_paths(
                {
                    "HOME": str(root),
                    "LLMOPS_CONFIG_HOME": str(root / "canonical"),
                    "LLMOPS_DATA_HOME": str(root / "data"),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                    "LLMOPS_CACHE_HOME": str(root / "cache"),
                }
            )
            first = migrate(legacy, paths)
            second = migrate(legacy, paths)
            self.assertFalse(first.unchanged)
            self.assertTrue(second.unchanged)
            profile = json.loads((paths.models_dir / "chat.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["environment"]["MODEL"], "/models/chat.gguf")
            self.assertEqual(profile["environment"]["HOST"], "127.0.0.1")
            (legacy / "config" / "chat.env").write_text("MODEL=/models/new.gguf\n", encoding="utf-8")
            with self.assertRaisesRegex(MigrationError, "source changed"):
                migrate(legacy, paths)


if __name__ == "__main__":
    unittest.main()
