#!/usr/bin/env python
"""Remote update planning, verification, and rollback tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from llmops_kit import llmops_update


HOST = {
    "name": "peer",
    "host": "peer.example",
    "user": "operator",
    "port": 22,
    "install_root": "~/custom/llm-ops",
    "public_bin_dir": "~/custom/bin",
    "state_home": "~/custom/state",
}


class RemoteUpdateTests(unittest.TestCase):
    def test_selected_host_rollback_does_not_fall_through_to_local_installer(self) -> None:
        with (
            mock.patch.object(llmops_update, "_select_hosts", return_value=[("peer", HOST)]),
            mock.patch.object(llmops_update, "_remote_preflight", return_value={"host": "peer", "version": "beta-2"}),
            mock.patch.object(llmops_update, "_remote_rollback", return_value={"host": "peer", "ok": True, "output": "rolled back", "error": ""}) as rollback,
            mock.patch("subprocess.run") as local_run,
        ):
            result = llmops_update.main(["--rollback", "--host", "peer", "--json"])
        self.assertEqual(result, 0)
        rollback.assert_called_once_with("peer", HOST, 900)
        local_run.assert_not_called()

    def test_apply_skips_hosts_already_at_target_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "LLM-Ops-Kit-beta-2.tar.xz"
            archive.write_bytes(b"verified release")
            checksum = root / f"{archive.name}.sha256"
            checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n", encoding="utf-8")
            with (
                mock.patch.object(llmops_update, "_select_hosts", return_value=[("peer", HOST)]),
                mock.patch.object(llmops_update, "_remote_preflight", return_value={"host": "peer", "ok": True, "version": "beta-2"}),
                mock.patch.object(llmops_update, "_remote_stage") as stage,
                mock.patch.object(llmops_update, "_remote_apply") as apply,
            ):
                result = llmops_update.main(["--apply", "--archive", str(archive), "--checksum-file", str(checksum), "--host", "peer", "--json"])
        self.assertEqual(result, 0)
        stage.assert_not_called()
        apply.assert_not_called()

    def test_local_apply_selects_complete_previous_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / "releases" / "beta-1"
            previous = root / "releases" / "beta-2"
            (current / "scripts").mkdir(parents=True)
            previous.mkdir(parents=True)
            (current / "RELEASE.json").write_text('{"version":"beta-1"}\n', encoding="utf-8")
            (previous / "RELEASE.json").write_text('{"version":"beta-2"}\n', encoding="utf-8")
            (current / "scripts" / "install-runtime.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (root / "current").symlink_to(current)
            (root / "previous").symlink_to(previous)
            archive = Path(temporary) / "LLM-Ops-Kit-beta-2.tar.xz"
            archive.write_bytes(b"unused")
            checksum = Path(temporary) / f"{archive.name}.sha256"
            checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n", encoding="utf-8")

            def select_previous(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
                (root / "current").unlink()
                (root / "current").symlink_to(previous)
                return subprocess.CompletedProcess([], 0, "", "")

            with mock.patch("subprocess.run", side_effect=select_previous):
                result = llmops_update.main(["--apply", "--archive", str(archive), "--checksum-file", str(checksum), "--prefix", str(root), "--json"])
        self.assertEqual(result, 0)

    def test_managed_catalog_precedes_release_legacy_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            managed = root / "current-config" / "catalog.json"
            managed.parent.mkdir(parents=True)
            managed.write_text("{}\n", encoding="utf-8")
            self.assertEqual(llmops_update._catalog_path(root, None), managed)

    def test_canonical_inventory_is_accepted_before_catalog_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = root / "inventory.json"
            inventory.write_text(json.dumps({"hosts": [HOST]}), encoding="utf-8")
            self.assertEqual(llmops_update._load_hosts(Path("/missing"), root)["peer"]["host"], "peer.example")

    def test_preflight_uses_configured_install_root(self) -> None:
        completed = subprocess.CompletedProcess([], 0, '{"version":"old"}\n', "")
        with mock.patch.object(llmops_update, "_run_remote", return_value=completed) as run_remote:
            result = llmops_update._remote_preflight("peer", HOST, 10)
        self.assertTrue(result["ok"])
        self.assertEqual(result["version"], "old")
        self.assertIn('"$HOME"/custom/llm-ops/current/RELEASE.json', run_remote.call_args.args[1])

    def test_update_transport_prefers_control_host(self) -> None:
        host = {**HOST, "control_host": "peer-control.example"}
        self.assertEqual(llmops_update._ssh_base(host)[-1], "operator@peer-control.example")

    def test_remote_verify_reports_release_and_configuration_identity(self) -> None:
        output = "VERSION=beta-2\nCATALOG=abc123\n" + json.dumps(
            {"ok": True, "valid": True, "config_hash": "def456"}
        )
        completed = subprocess.CompletedProcess([], 0, output, "")
        with mock.patch.object(llmops_update, "_run_remote", return_value=completed):
            result = llmops_update._remote_verify("peer", HOST, "beta-2", 10)
        self.assertEqual(result, {"version": "beta-2", "catalog_hash": "abc123", "config_hash": "def456"})

    def test_verification_failure_rolls_back_the_updated_host(self) -> None:
        completed = subprocess.CompletedProcess([], 0, "installed\n", "")
        rollback = {"host": "peer", "ok": True, "output": "", "error": ""}
        with (
            mock.patch.object(llmops_update, "_run_remote", return_value=completed),
            mock.patch.object(llmops_update, "_remote_verify", side_effect=llmops_update.UpdateError("bad identity")),
            mock.patch.object(llmops_update, "_remote_rollback", return_value=rollback) as remote_rollback,
        ):
            with self.assertRaisesRegex(llmops_update.UpdateError, "verification rollback"):
                llmops_update._remote_apply("peer", HOST, "$HOME/a.tar.xz", "$HOME/a.sha256", "beta-2", 10)
        remote_rollback.assert_called_once_with("peer", HOST, 10)

    def test_later_host_failure_rolls_back_hosts_already_updated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "LLM-Ops-Kit-beta-2.tar.xz"
            archive.write_bytes(b"verified release")
            checksum = root / f"{archive.name}.sha256"
            checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n", encoding="utf-8")
            first = {**HOST, "name": "first"}
            second = {**HOST, "name": "second", "host": "second.example"}
            with (
                mock.patch.object(llmops_update, "_select_hosts", return_value=[("first", first), ("second", second)]),
                mock.patch.object(llmops_update, "_remote_preflight", side_effect=lambda name, host, timeout: {"host": name, "ok": True}),
                mock.patch.object(llmops_update, "_remote_stage", side_effect=lambda name, host, archive, checksum, version, timeout: ("$HOME/archive", "$HOME/checksum")),
                mock.patch.object(
                    llmops_update,
                    "_remote_apply",
                    side_effect=[{"host": "first", "ok": True}, llmops_update.UpdateError("second failed")],
                ),
                mock.patch.object(llmops_update, "_remote_rollback", return_value={"host": "first", "ok": True}) as rollback,
            ):
                result = llmops_update.main(
                    [
                        "--apply",
                        "--archive",
                        str(archive),
                        "--checksum-file",
                        str(checksum),
                        "--host",
                        "first",
                        "--host",
                        "second",
                        "--prefix",
                        str(root / "install"),
                    ]
                )
            self.assertEqual(result, 2)
            rollback.assert_called_once_with("first", first, 900)


if __name__ == "__main__":
    unittest.main()
