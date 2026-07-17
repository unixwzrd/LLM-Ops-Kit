#!/usr/bin/env python3
"""Tests for non-destructive LLM-Ops-Kit starter configuration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.lib.llmops_config import load_config
from scripts.lib.llmops_init import InitError, discover_model_profiles, initialize
from scripts.lib.llmops_inventory import load_inventory
from scripts.lib.llmops_paths import resolve_paths
from scripts.lib.llmops_topology import Topology, load_stacks, validate_topology


class InitTests(unittest.TestCase):
    def paths(self, root: Path):
        return resolve_paths(
            {
                "HOME": str(root),
                "LLMOPS_CONFIG_HOME": str(root / "config"),
                "LLMOPS_DATA_HOME": str(root / "data"),
                "LLMOPS_STATE_HOME": str(root / "state"),
                "LLMOPS_CACHE_HOME": str(root / "cache"),
            }
        )

    def test_single_host_preset_is_valid_and_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.paths(Path(tmp))
            initialize(paths, preset="single-host", user="operator")
            topology = Topology(
                stacks=load_stacks(paths),
                hosts=load_inventory(paths.inventory_file),
                paths=paths,
                config=load_config(paths=paths),
            )
            self.assertEqual(validate_topology(topology), [])
            self.assertFalse(any(item.enabled for item in topology.all_components()))

    def test_local_lan_preset_uses_two_ssh_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.paths(Path(tmp))
            initialize(
                paths,
                preset="local-lan",
                user="operator",
                model_host="models.local",
                agent_host="agents.local",
            )
            hosts = load_inventory(paths.inventory_file)
            self.assertEqual(sorted(hosts), ["agent-host", "model-host"])
            self.assertTrue(all(host.transport == "ssh" for host in hosts.values()))

    def test_init_refuses_to_overwrite_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.paths(Path(tmp))
            initialize(paths, preset="single-host", user="operator")
            with self.assertRaisesRegex(InitError, "refusing to overwrite"):
                initialize(paths, preset="single-host", user="operator")

    def test_imports_legacy_models_converts_secrets_and_binds_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "existing"
            (source / "models").mkdir(parents=True)
            (source / "models" / "chat-model.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "chat-model",
                        "type": "llm",
                        "env": {
                            "MODEL": "/models/chat.gguf",
                            "HOST": "127.0.0.1",
                            "PORT": 11434,
                            "API_KEY": "literal-secret",
                        },
                        "sources": ["legacy.sh"],
                    }
                ),
                encoding="utf-8",
            )
            candidates = discover_model_profiles(source)
            paths = self.paths(root)
            result = initialize(
                paths,
                preset="single-host",
                user="operator",
                model_candidates=candidates,
                import_models=["chat-model"],
                default_chat="chat-model",
            )
            imported = json.loads((paths.models_dir / "chat-model.json").read_text(encoding="utf-8"))
            self.assertNotIn("env", imported)
            self.assertNotIn("sources", imported)
            self.assertEqual(imported["environment"]["API_KEY"], "env:API_KEY")
            self.assertEqual(imported["environment"]["MODEL_PROFILE"], "chat-model")
            stack = json.loads((paths.stacks_dir / "starter.json").read_text(encoding="utf-8"))
            chat = next(item for item in stack["components"] if item["id"] == "chat")
            self.assertEqual(chat["profile"], "chat-model")
            self.assertFalse(chat["enabled"])
            self.assertEqual(result.imported_models, ("chat-model",))
            self.assertIn("chat-model:environment.API_KEY", result.converted_secrets)

    def test_invalid_import_leaves_destination_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "existing"
            (source / "models").mkdir(parents=True)
            (source / "models" / "bad.json").write_text(
                json.dumps({"schema_version": 1, "name": "bad", "type": "llm", "env": {"MODEL": "relative.gguf"}}),
                encoding="utf-8",
            )
            paths = self.paths(root)
            with self.assertRaisesRegex(InitError, "model path must be absolute"):
                discover_model_profiles(source)
            self.assertFalse(paths.config_home.exists())


if __name__ == "__main__":
    unittest.main()
