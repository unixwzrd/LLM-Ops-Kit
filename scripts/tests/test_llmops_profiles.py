#!/usr/bin/env python
"""Tests for canonical profile resolution and one-way migration."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

from llmops_kit.llmops_migration import MigrationError, migrate
from llmops_kit.llmops_paths import resolve_paths
from llmops_kit.llmops_profiles import ProfileError, load_profile, model_values, resolve_references, service_values


class ProfileTests(unittest.TestCase):
    def test_profile_loader_never_falls_back_to_repository_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = resolve_paths({"HOME": temporary})
            with self.assertRaisesRegex(ProfileError, "profile not found"):
                load_profile("model", "Qwen3", paths=paths)

    def test_structured_model_profile_resolves_runtime_values(self) -> None:
        values = model_values(
            {
                "schema_version": 2,
                "name": "chat",
                "type": "llm",
                "model_path": "/models/chat.gguf",
                "mmproj_path": "/models/mmproj.gguf",
                "runtime": {"host": "127.0.0.1", "port": 11434},
                "llama": {"ctx_size": 32768, "use_mlock": True},
                "server": {"cache_prompt": True, "extra_flags": ["--metrics"]},
            }
        )
        self.assertEqual(values["MODEL"], "/models/chat.gguf")
        self.assertEqual(values["MMPROJ"], "/models/mmproj.gguf")
        self.assertEqual(values["MODEL_PROFILE"], "chat")
        self.assertEqual(values["PORT"], "11434")
        self.assertEqual(values["USE_MLOCK"], "1")
        self.assertEqual(values["EXTRA_FLAGS"], "--metrics")

    def test_embedding_profile_does_not_resolve_vision_projector(self) -> None:
        values = model_values(
            {
                "schema_version": 2,
                "name": "embedding",
                "type": "embedding",
                "model_path": "/models/embedding.gguf",
                "mmproj_path": "/models/unused-mmproj.gguf",
            }
        )
        self.assertNotIn("MMPROJ", values)

    def test_structured_model_paths_override_legacy_environment(self) -> None:
        values = model_values(
            {
                "schema_version": 2,
                "name": "chat",
                "type": "llm",
                "model_path": "/models/current-chat.gguf",
                "mmproj_path": "/models/current-mmproj.gguf",
                "environment": {
                    "MODEL": "/models/legacy-chat.gguf",
                    "MMPROJ": "/models/legacy-mmproj.gguf",
                },
            }
        )
        self.assertEqual(values["MODEL"], "/models/current-chat.gguf")
        self.assertEqual(values["MMPROJ"], "/models/current-mmproj.gguf")

    def test_service_environment_is_explicit_json(self) -> None:
        self.assertEqual(
            service_values("model-proxy", {"environment": {"MODEL_PROXY_LISTEN_PORT": 11434}}),
            {"MODEL_PROXY_LISTEN_PORT": "11434"},
        )

    def test_model_proxy_reasoning_diagnostic_is_schema_bound(self) -> None:
        values = service_values(
            "model-proxy",
            {
                "runtime": {
                    "listen_host": "127.0.0.1",
                    "listen_port": 11434,
                    "upstream_host": "model.local",
                    "upstream_port": 11434,
                },
                "logging": {"show_reasoning": True},
            },
        )

        self.assertEqual(values["MODEL_PROXY_SHOW_REASONING"], "1")

    def test_runtime_environment_references_are_resolved_explicitly(self) -> None:
        self.assertEqual(resolve_references({"API_KEY": "env:MODEL_API_KEY"}, {"MODEL_API_KEY": "value"}), {"API_KEY": "value"})
        with self.assertRaisesRegex(ProfileError, "unresolved environment reference"):
            resolve_references({"API_KEY": "env:MISSING"}, {})


class MigrationTests(unittest.TestCase):
    def test_realistic_legacy_fixture_maps_all_supported_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / "legacy"
            shutil.copytree(FIXTURES / "legacy", legacy)
            paths = resolve_paths(
                {
                    "HOME": str(root),
                    "LLMOPS_CONFIG_HOME": str(root / "canonical"),
                    "LLMOPS_DATA_HOME": str(root / "data"),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                    "LLMOPS_CACHE_HOME": str(root / "cache"),
                }
            )
            preview = migrate(legacy, paths, dry_run=True)
            self.assertEqual({item["kind"] for item in preview.mappings}, {"model", "service", "agent", "inventory"})
            result = migrate(legacy, paths)
            self.assertFalse(result.skipped)
            tts = json.loads((paths.models_dir / "TTSModel.json").read_text(encoding="utf-8"))
            agent = json.loads((paths.agents_dir / "generic.json").read_text(encoding="utf-8"))
            self.assertEqual(tts["environment"]["TTS_API_KEY"], "env:TTS_API_KEY")
            self.assertEqual(agent["environment"]["AGENT_API_TOKEN"], "env:AGENT_API_TOKEN")
            self.assertFalse(agent["enabled"])

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

    def test_migration_classifies_services_and_reports_unknown_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / "legacy"
            (legacy / "config").mkdir(parents=True)
            (legacy / "config.env").write_text("HOST=127.0.0.1\n", encoding="utf-8")
            (legacy / "config" / "model-proxy.env").write_text(
                "LLMOPS_UPSTREAM_HOST=models.local\nLLMOPS_UPSTREAM_PORT=11434\nAPI_KEY=secret\n",
                encoding="utf-8",
            )
            (legacy / "config" / "notes.env").write_text("UNRELATED=value\n", encoding="utf-8")
            paths = resolve_paths(
                {
                    "HOME": str(root),
                    "LLMOPS_CONFIG_HOME": str(root / "canonical"),
                    "LLMOPS_DATA_HOME": str(root / "data"),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                    "LLMOPS_CACHE_HOME": str(root / "cache"),
                }
            )
            preview = migrate(legacy, paths, dry_run=True)
            unknown = str((legacy / "config" / "notes.env").resolve())
            self.assertEqual(preview.skipped, (unknown,))
            self.assertEqual(preview.mappings[0]["kind"], "service")
            with self.assertRaisesRegex(MigrationError, "unclassified inputs"):
                migrate(legacy, paths)
            result = migrate(legacy, paths, allow_partial=True)
            service = json.loads((paths.services_dir / "model-proxy.json").read_text(encoding="utf-8"))
            self.assertEqual(service["environment"]["API_KEY"], "env:API_KEY")
            self.assertIn(unknown, result.skipped)

    def test_global_service_values_do_not_reclassify_models(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / "legacy"
            (legacy / "config").mkdir(parents=True)
            (legacy / "config.env").write_text(
                "HOST=127.0.0.1\nTTS_BRIDGE_PORT=11440\nLLMOPS_UPSTREAM_HOST=models.local\n",
                encoding="utf-8",
            )
            (legacy / "config" / "chat.env").write_text(
                "MODEL_PATH=/models/chat.gguf\nMODEL_NAME=chat\nMODEL_PORT=11434\n",
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
            result = migrate(legacy, paths)
            self.assertFalse(result.skipped)
            model = json.loads((paths.models_dir / "chat.json").read_text(encoding="utf-8"))
            self.assertEqual(model["environment"]["MODEL"], "/models/chat.gguf")
            self.assertEqual(model["environment"]["MODEL_PROFILE"], "chat")
            self.assertNotIn("TTS_BRIDGE_PORT", model["environment"])
            self.assertTrue((paths.services_dir / "model-proxy.json").is_file())
            self.assertTrue((paths.services_dir / "tts-bridge.json").is_file())


if __name__ == "__main__":
    unittest.main()
