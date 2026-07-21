#!/usr/bin/env python
"""Configuration reconciliation identity tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from llmops_kit.llmops_config import load_config
from llmops_kit.llmops_config_sync import reconcile_plan, remote_snapshot_status, snapshot_hash
from llmops_kit.llmops_init import initialize
from llmops_kit.llmops_inventory import load_inventory
from llmops_kit.llmops_paths import resolve_paths
from llmops_kit.llmops_topology import Topology, load_stacks


class ConfigSyncTests(unittest.TestCase):
    def topology(self, root: Path) -> Topology:
        paths = resolve_paths(
            {
                "HOME": str(root),
                "LLMOPS_CONFIG_HOME": str(root / "config"),
                "LLMOPS_DATA_HOME": str(root / "data"),
                "LLMOPS_STATE_HOME": str(root / "state"),
                "LLMOPS_CACHE_HOME": str(root / "cache"),
            }
        )
        initialize(paths, preset="single-host", user="operator")
        stack_path = paths.stacks_dir / "starter.json"
        stack = json.loads(stack_path.read_text(encoding="utf-8"))
        stack["components"][0]["enabled"] = True
        stack_path.write_text(json.dumps(stack), encoding="utf-8")
        return Topology(load_stacks(paths), load_inventory(paths.inventory_file), paths, load_config(paths=paths))

    def test_manifest_detects_manual_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config.json"
            config.write_text('{"schema_version": 1}\n', encoding="utf-8")
            record = {"path": "config.json", "sha256": hashlib.sha256(config.read_bytes()).hexdigest()}
            (root / "resolved.json").write_text(json.dumps({"files": [record]}), encoding="utf-8")
            first, valid, errors = snapshot_hash(root)
            self.assertTrue(valid)
            self.assertFalse(errors)
            config.write_text('{"schema_version": 2}\n', encoding="utf-8")
            second, valid, errors = snapshot_hash(root)
            self.assertEqual(first, second)
            self.assertFalse(valid)
            self.assertTrue(errors)

    def test_canonical_config_without_manifest_has_stable_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config.json").write_text('{"schema_version": 1}\n', encoding="utf-8")
            self.assertEqual(snapshot_hash(root), snapshot_hash(root))

    def test_local_ui_preferences_do_not_change_configuration_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config.json").write_text('{"schema_version": 1}\n', encoding="utf-8")
            before = snapshot_hash(root)[0]
            (root / "ui.json").write_text('{"refresh_seconds": 30}\n', encoding="utf-8")
            self.assertEqual(snapshot_hash(root)[0], before)

    def test_remote_drift_payload_is_preserved_on_nonzero_exit(self) -> None:
        host = mock.Mock(transport="local", public_bin_dir="~/.local/bin")
        completed = subprocess.CompletedProcess(
            [],
            2,
            json.dumps({"ok": False, "valid": False, "config_hash": "declared", "errors": ["changed"]}),
            "",
        )
        with mock.patch("llmops_kit.llmops_config_sync._remote_command", return_value=completed):
            result = remote_snapshot_status(host)
        self.assertTrue(result["reachable"])
        self.assertFalse(result["valid"])
        self.assertEqual(result["config_hash"], "declared")

    def test_reconcile_plan_refuses_conflict_unreachable_and_error_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            topology = self.topology(Path(temporary))
            cases = (
                ({"reachable": True, "ok": False, "valid": False, "config_hash": "declared"}, "conflict"),
                ({"reachable": False, "ok": False, "error": "offline"}, "unreachable"),
                ({"reachable": True, "ok": False, "error": "inventory not found: target"}, "apply"),
                ({"reachable": True, "ok": False, "error": "bad response"}, "error"),
            )
            for observed, expected in cases:
                with self.subTest(expected=expected), mock.patch(
                    "llmops_kit.llmops_config_sync.remote_snapshot_status", return_value=observed
                ):
                    plan, snapshots = reconcile_plan(topology, ["local"])
                    try:
                        self.assertEqual(plan[0]["action"], expected)
                    finally:
                        shutil.rmtree(next(iter(snapshots.values())).parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
