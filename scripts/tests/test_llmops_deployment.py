#!/usr/bin/env python3
"""Tests for canonical immutable deployment artifacts."""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))

import llmops_deployment as deployment


class DeploymentTests(unittest.TestCase):
    def _configuration(self, root: Path) -> Path:
        config = root / "config"
        for name in ("models", "agents", "services", "stacks"):
            (config / name).mkdir(parents=True, exist_ok=True)
        (config / "config.json").write_text(
            json.dumps({"schema_version": 1, "runtime": {"allow_command_driver": False}}),
            encoding="utf-8",
        )
        (config / "inventory.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "hosts": [
                        {
                            "name": "local",
                            "role": "hybrid",
                            "host": "localhost",
                            "user": "operator",
                            "port": 22,
                            "transport": "local",
                            "install_root": str(root / "install"),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (config / "models" / "chat.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": {
                        "MODEL_PROFILE": "chat",
                        "MODEL_TYPE": "llm",
                        "MODEL": "/models/chat.gguf",
                        "HOST": "127.0.0.1",
                        "PORT": 11434,
                    },
                }
            ),
            encoding="utf-8",
        )
        (config / "stacks" / "test.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "test",
                    "components": [
                        {
                            "id": "chat",
                            "host": "local",
                            "driver": "modelctl",
                            "profile": "chat",
                            "enabled": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return config

    def test_stage_contains_only_package_and_canonical_host_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self._configuration(root)
            args = argparse.Namespace(
                config_home=str(config),
                inventory=None,
                host_name=None,
                role=None,
                tag=None,
                bundle_id="test-release",
                stage_root=str(root / "stage"),
                allow_dirty=True,
                dry_run=False,
                source=str(deployment.REPO_ROOT),
            )
            stage, manifest = deployment.stage_bundle(args)
            self.assertEqual(manifest["schema_version"], 2)
            self.assertFalse((stage / "hosts" / "local" / "config.env").exists())
            snapshot = stage / "hosts" / "local" / "config.tar.gz"
            with tarfile.open(snapshot, "r:gz") as archive:
                names = archive.getnames()
            self.assertIn("config.json", names)
            self.assertIn("inventory.json", names)
            self.assertFalse(any(name.endswith(".env") for name in names))
            with tarfile.open(stage / "package" / "llm-ops-kit.tar.gz", "r:gz") as archive:
                package_names = archive.getnames()
            self.assertFalse(any("tests" in Path(name).parts for name in package_names))
            self.assertFalse(any(name.endswith((".env", ".DS_Store", ".pyc")) for name in package_names))

    def test_internal_links_exclude_agent_specific_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = self._configuration(Path(temporary))
            topology = deployment._topology(str(config), None)
            script = deployment._link_script(topology.hosts["local"])
        self.assertNotIn("agentctl", script)
        self.assertNotIn("openclaw", script)
        self.assertNotIn("hermes", script)

    def test_dirty_source_is_refused_without_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self._configuration(root)
            args = argparse.Namespace(
                config_home=str(config),
                inventory=None,
                host_name=None,
                role=None,
                tag=None,
                bundle_id="dirty-release",
                stage_root=str(root / "stage"),
                allow_dirty=False,
                dry_run=True,
                source=str(deployment.REPO_ROOT),
            )
            with mock.patch.object(
                deployment,
                "_git_provenance",
                return_value={"git_commit": "test", "git_dirty": True, "toolkit_version": "test"},
            ):
                with self.assertRaisesRegex(deployment.DeploymentError, "refuses a dirty source tree"):
                    deployment.stage_bundle(args)


if __name__ == "__main__":
    unittest.main()
