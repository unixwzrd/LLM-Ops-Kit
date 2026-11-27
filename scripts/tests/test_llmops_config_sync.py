#!/usr/bin/env python
"""Configuration reconciliation identity tests."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from llmops_kit.llmops_config import load_config
from llmops_kit.llmops_config_sync import ReconcileError, apply_snapshot, reconcile_plan, remote_snapshot_status, snapshot_hash
from llmops_kit.llmops_config_sync import _remote_command
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
            config.write_text(
                '{"schema_version": 2, "display": {"site": "changed"}}\n',
                encoding="utf-8",
            )
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
            (root / "config.json").write_text('{"schema_version": 2}\n', encoding="utf-8")
            self.assertEqual(snapshot_hash(root), snapshot_hash(root))

    def test_local_ui_preferences_do_not_change_configuration_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config.json").write_text('{"schema_version": 2}\n', encoding="utf-8")
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

    def test_local_target_observation_does_not_inherit_authority_overrides(self) -> None:
        host = mock.Mock(transport="local")
        with mock.patch.dict(
            "os.environ",
            {
                "LLMOPS_CONFIG_HOME": "/authority",
                "LLMOPS_AUTHORITY_CONFIG_HOME": "/authority",
                "KEEP_ME": "yes",
            },
        ), mock.patch("subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            _remote_command(host, "/usr/bin/true")
        environment = run.call_args.kwargs["env"]
        self.assertNotIn("LLMOPS_CONFIG_HOME", environment)
        self.assertNotIn("LLMOPS_AUTHORITY_CONFIG_HOME", environment)
        self.assertEqual(environment["KEEP_ME"], "yes")

    def test_reconcile_plan_refuses_conflict_unreachable_and_error_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            topology = self.topology(Path(temporary))
            cases = (
                ({"reachable": True, "ok": False, "valid": False, "config_hash": "declared"}, "conflict"),
                ({"reachable": False, "ok": False, "error": "offline"}, "unreachable"),
                ({"reachable": True, "ok": False, "error": "inventory not found: target"}, "apply"),
                ({"reachable": True, "ok": False, "error": "unsupported schema_version: 1"}, "apply"),
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

    def test_snapshot_install_does_not_accumulate_transfer_archives(self) -> None:
        native_run = subprocess.run
        for transport, copy_fails in (("local", False), ("ssh", False), ("ssh", True)):
            with self.subTest(transport=transport, copy_fails=copy_fails), tempfile.TemporaryDirectory(
                prefix="llmops config "
            ) as temporary:
                home = Path(temporary).resolve()
                snapshot = home / "source snapshot"
                snapshot.mkdir()
                (snapshot / "config.json").write_text('{"schema_version":2}\n', encoding="utf-8")
                digest = snapshot_hash(snapshot)[0]
                install = home / "install"
                previous = install / "config-revisions/old"
                previous.mkdir(parents=True)
                (install / "current-config").symlink_to(previous)
                launcher = home / "bin/llmops"
                launcher.parent.mkdir()
                launcher.write_text(f"#!/bin/sh\nprintf 'config_hash={digest}\\n'\n", encoding="utf-8")
                launcher.chmod(0o700)
                host = mock.Mock(
                    name="peer", transport=transport, port=22, destination="operator@peer",
                    install_root=str(install), public_bin_dir=str(launcher.parent),
                )
                host.name = "peer"

                def remote(_host: object, command: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
                    return native_run(
                        ["/bin/sh", "-c", command], env={**os.environ, "HOME": str(home)},
                        text=True, capture_output=True, check=False, timeout=timeout,
                    )

                def copy(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                    self.assertEqual(argv[0], "scp")
                    destination = argv[-1].split(":", 1)[1]
                    shutil.copy2(argv[-2], home / destination)
                    return subprocess.CompletedProcess(argv, 255 if copy_fails else 0, "", "disconnected" if copy_fails else "")

                with (
                    mock.patch("llmops_kit.llmops_config_sync._remote_command", side_effect=remote),
                    mock.patch("llmops_kit.llmops_config_sync.subprocess.run", side_effect=copy) as scp,
                ):
                    if copy_fails:
                        with self.assertRaisesRegex(ReconcileError, "could not transfer"):
                            apply_snapshot(host, snapshot, digest)
                    else:
                        self.assertTrue(apply_snapshot(host, snapshot, digest)["ok"])
                self.assertEqual(scp.call_count, int(transport == "ssh"))
                self.assertEqual(list((home / ".cache/llm-ops/config").glob("*")), [])
                if copy_fails:
                    self.assertEqual((install / "current-config").resolve(), previous)
                else:
                    self.assertEqual((install / "previous-config").resolve(), previous)
                    self.assertEqual(
                        (install / "current-config/config.json").read_bytes(), (snapshot / "config.json").read_bytes()
                    )
                    self.assertFalse((install / "current-config").resolve().is_relative_to(home / ".cache"))


if __name__ == "__main__":
    unittest.main()
