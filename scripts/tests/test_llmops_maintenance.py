#!/usr/bin/env python
"""Tests for fail-closed immutable toolkit release retention."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from llmops_kit import llmops_maintenance
from llmops_kit.llmops_executor import operation_lock


def completed(command: list[str], returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    """Return a subprocess result for mocked reference inspection."""

    return subprocess.CompletedProcess(command, returncode, stdout, "")


class ReleaseMaintenanceTests(unittest.TestCase):
    def fixture(self, root: Path) -> Path:
        install = root / "install"
        releases = install / "releases"
        releases.mkdir(parents=True)
        for version in ("b49", "b50", "b51"):
            release = releases / version
            (release / "app/bin").mkdir(parents=True)
            (release / "scripts").mkdir()
            for relative in ("app/bin/llmops", "scripts/llmops", "scripts/install-runtime.sh"):
                executable = release / relative
                executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                executable.chmod(0o755)
            (release / "RELEASE.json").write_text(
                json.dumps({"schema_version": 1, "version": version}), encoding="utf-8"
            )
            (release / "release-manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "LLM-Ops-Kit",
                        "version": version,
                        "files": [
                            {
                                "path": relative,
                                "sha256": hashlib.sha256((release / relative).read_bytes()).hexdigest(),
                                "mode": 0o755,
                            }
                            for relative in ("scripts/llmops", "scripts/install-runtime.sh")
                        ],
                    }
                ),
                encoding="utf-8",
            )
        (install / "current").symlink_to(releases / "b51")
        (install / "previous").symlink_to(releases / "b50")
        state = root / "state"
        (state / "run").mkdir(parents=True)
        (install / "install.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "install_root": str(install),
                    "public_bin_dir": str(root / "bin"),
                    "state_home": str(state),
                    "active_release": str(releases / "b51"),
                }
            ),
            encoding="utf-8",
        )
        return install

    def maintain(self, install: Path, **kwargs: object) -> dict[str, object]:
        launch_agents = install.parent / "LaunchAgents"
        launch_agents.mkdir(exist_ok=True)
        kwargs.pop("run_dir", None)
        if kwargs.get("apply") and "plan_digest" not in kwargs:
            plan = llmops_maintenance.maintain_releases(
                install / "install.json",
                launch_agents_dir=launch_agents,
                config_roots=kwargs.get("config_roots", ()),
            )
            kwargs["plan_digest"] = plan["plan_digest"]
        return llmops_maintenance.maintain_releases(
            install / "install.json", launch_agents_dir=launch_agents, **kwargs
        )

    def no_references(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[0] == "ps":
            return completed(command)
        return completed(command, returncode=1)

    def test_plan_protects_current_and_previous_and_selects_only_owned_old_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            install = self.fixture(Path(temporary))
            with mock.patch("subprocess.run", side_effect=self.no_references):
                payload = self.maintain(install)
            actions = {row["release"]: row["action"] for row in payload["releases"]}
            self.assertEqual(actions, {"b49": "remove", "b50": "keep", "b51": "keep"})
            self.assertTrue((install / "releases" / "b49").is_dir())

    def test_apply_removes_old_release_but_never_real_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            with mock.patch("subprocess.run", side_effect=self.no_references):
                payload = self.maintain(install, apply=True, run_dir=root / "state" / "run")
            self.assertEqual(payload["removed"], ["b49"])
            self.assertFalse((install / "releases" / "b49").exists())
            self.assertTrue((install / "releases" / "b50").is_dir())

    def test_active_old_release_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)

            def active(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                if command[0] == "ps":
                    old_release = (install / "releases" / "b49").resolve()
                    return completed(command, stdout=f"42 {old_release}/app/bin/python worker\n")
                return completed(command, returncode=1)

            with mock.patch("subprocess.run", side_effect=active):
                payload = self.maintain(install, apply=True, run_dir=root / "state" / "run")
            self.assertEqual(payload["removed"], [])
            self.assertTrue((install / "releases" / "b49").is_dir())
            self.assertEqual(payload["releases"][0]["action"], "skip")

    def test_unmanaged_directory_is_retained_while_owned_candidate_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            (install / "releases" / "manual-copy").mkdir()
            with mock.patch("subprocess.run", side_effect=self.no_references):
                payload = self.maintain(install, apply=True, run_dir=root / "state" / "run")
            self.assertFalse((install / "releases" / "b49").exists())
            self.assertTrue((install / "releases" / "manual-copy").is_dir())
            unknown = next(row for row in payload["releases"] if row["release"] == "manual-copy")
            self.assertEqual(unknown["action"], "skip")

    def test_ds_store_is_retained_without_blocking_owned_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            ds_store = install / "releases/.DS_Store"
            ds_store.write_bytes(b"fixture metadata")
            with mock.patch("subprocess.run", side_effect=self.no_references):
                payload = self.maintain(install, apply=True)
            self.assertEqual(payload["removed"], ["b49"])
            self.assertTrue(ds_store.is_file())
            row = next(item for item in payload["releases"] if item["release"] == ".DS_Store")
            self.assertEqual(row["action"], "skip")
            self.assertEqual(row["reason"], "unmanaged regular file retained")

    def test_tainted_previous_is_still_reported_as_protected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            install = self.fixture(Path(temporary))
            (install / "previous/scripts/llmops").write_text("tampered\n", encoding="utf-8")
            with mock.patch("subprocess.run", side_effect=self.no_references):
                payload = self.maintain(install)
            row = next(item for item in payload["releases"] if item["release"] == "b50")
            self.assertEqual(row["action"], "keep")
            self.assertEqual(row["reason"], "previous")

    def test_drop_previous_requires_apply_and_removes_selector(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            with self.assertRaisesRegex(llmops_maintenance.MaintenanceError, "not supported"):
                self.maintain(install, drop_previous=True)
            with self.assertRaisesRegex(llmops_maintenance.MaintenanceError, "not supported"):
                self.maintain(install, apply=True, drop_previous=True)
            self.assertTrue((install / "previous").is_symlink())

    def test_escaping_symlink_rejects_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            (install / "releases" / "b49" / "escape").symlink_to(root / "outside")
            with mock.patch("subprocess.run", side_effect=self.no_references):
                with self.assertRaisesRegex(llmops_maintenance.MaintenanceError, "not clean"):
                    self.maintain(install, apply=True, run_dir=root / "state" / "run")
            self.assertTrue((install / "releases" / "b49").is_dir())

    def test_selector_drift_before_remove_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            original_inventory = llmops_maintenance._inventory
            with mock.patch("subprocess.run", side_effect=self.no_references):
                reviewed = self.maintain(install)

            def drift(*args: object, **kwargs: object) -> object:
                result = original_inventory(*args, **kwargs)
                (install / "previous").unlink()
                (install / "previous").symlink_to(install / "releases" / "b49")
                return result

            with (
                mock.patch("subprocess.run", side_effect=self.no_references),
                mock.patch.object(llmops_maintenance, "_inventory", side_effect=drift),
            ):
                with self.assertRaisesRegex(llmops_maintenance.MaintenanceError, "changed"):
                    self.maintain(
                        install,
                        apply=True,
                        plan_digest=reviewed["plan_digest"],
                    )
            self.assertTrue((install / "releases" / "b49").is_dir())

    def test_apply_uses_lifecycle_orchestration_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            lock_path = root / "state" / "run" / "orchestrator.lock"
            with (
                mock.patch("subprocess.run", side_effect=self.no_references),
                operation_lock(lock_path),
                self.assertRaisesRegex(llmops_maintenance.MaintenanceError, "another lifecycle operation"),
            ):
                self.maintain(install, apply=True, run_dir=lock_path.parent)
            self.assertTrue((install / "releases" / "b49").is_dir())

    def test_apply_uses_canonical_update_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            lock = install / "update.lock"
            lock.mkdir(mode=0o700)
            (lock / "owner").write_text("fixture-owner\n", encoding="utf-8")
            with (
                mock.patch("subprocess.run", side_effect=self.no_references),
                self.assertRaisesRegex(llmops_maintenance.MaintenanceError, "another install mutation"),
            ):
                self.maintain(install, apply=True)
            self.assertTrue((install / "releases/b49").is_dir())

    def test_direct_installer_repair_contends_on_same_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            lock = install / "update.lock"
            lock.mkdir(mode=0o700)
            (lock / "owner").write_text("fixture-owner\n", encoding="utf-8")
            installer = Path(__file__).parents[2] / "scripts/install-runtime.sh"
            completed_process = subprocess.run(
                [
                    "bash",
                    str(installer),
                    "--prefix",
                    str(install),
                    "--state-home",
                    str(root / "state"),
                    "--public-bin-dir",
                    str(root / "bin"),
                    "--repair",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed_process.returncode, 2)
            self.assertIn("another install mutation", completed_process.stderr)
            self.assertTrue((install / "releases/b49").is_dir())

    def test_group_writable_candidate_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            unsafe = install / "releases/b49/scripts"
            unsafe.chmod(0o775)
            with mock.patch("subprocess.run", side_effect=self.no_references):
                payload = self.maintain(install)
            row = next(item for item in payload["releases"] if item["release"] == "b49")
            self.assertEqual(row["action"], "blocked")
            self.assertIn("group/world writable", row["reason"])

    def test_group_writable_runtime_reference_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            reference = root / "state/run/model.pid"
            reference.write_text("123\n", encoding="utf-8")
            reference.chmod(0o666)
            with mock.patch("subprocess.run", side_effect=self.no_references):
                payload = self.maintain(install)
            row = next(item for item in payload["releases"] if item["release"] == "b49")
            self.assertEqual(row["action"], "blocked")
            self.assertIn("group/world writable", row["reason"])

    def test_group_writable_runtime_lock_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            run_root = root / "state/run"
            run_root.chmod(0o775)
            with self.assertRaisesRegex(llmops_maintenance.MaintenanceError, "group/world writable"):
                self.maintain(install)

    def test_apply_requires_matching_reviewed_plan_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            install = self.fixture(Path(temporary))
            with (
                mock.patch("subprocess.run", side_effect=self.no_references),
                self.assertRaisesRegex(llmops_maintenance.MaintenanceError, "reviewed --plan-digest"),
            ):
                llmops_maintenance.maintain_releases(
                    install / "install.json",
                    apply=True,
                    launch_agents_dir=install.parent / "LaunchAgents",
                )
            self.assertTrue((install / "releases/b49").is_dir())

    def test_stopped_release_referenced_by_active_config_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            config = root / "config"
            config.mkdir()
            old = (install / "releases" / "b49").resolve()
            (config / "services.json").write_text(
                json.dumps({"start": [str(old / "scripts/llmops"), "component", "start"]}),
                encoding="utf-8",
            )
            with mock.patch("subprocess.run", side_effect=self.no_references):
                payload = self.maintain(install, apply=True, config_roots=(config,))
            row = next(item for item in payload["releases"] if item["release"] == "b49")
            self.assertEqual(row["action"], "skip")
            self.assertEqual(row["references"], [{"category": "configuration"}])

    def test_stopped_release_referenced_by_launchagent_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            launch_agents = root / "LaunchAgents"
            launch_agents.mkdir()
            old = (install / "releases" / "b49").resolve()
            (launch_agents / "ai.example.old.plist").write_text(
                f"<plist><string>{old}/app/bin/llmops</string></plist>", encoding="utf-8"
            )
            with mock.patch("subprocess.run", side_effect=self.no_references):
                reviewed = llmops_maintenance.maintain_releases(
                    install / "install.json", launch_agents_dir=launch_agents
                )
                payload = llmops_maintenance.maintain_releases(
                    install / "install.json",
                    apply=True,
                    launch_agents_dir=launch_agents,
                    plan_digest=reviewed["plan_digest"],
                )
            row = next(item for item in payload["releases"] if item["release"] == "b49")
            self.assertEqual(row["references"], [{"category": "launchd-plist"}])

    def test_recorded_started_runtime_root_skips_stopped_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            old = (install / "releases/b49").resolve()
            (root / "state/run/model.state").write_text(
                f"pid=\nstarted_runtime_root={old}\n", encoding="utf-8"
            )
            with mock.patch("subprocess.run", side_effect=self.no_references):
                payload = self.maintain(install, apply=True)
            row = next(item for item in payload["releases"] if item["release"] == "b49")
            self.assertEqual(row["references"], [{"category": "runtime-state"}])

    def test_process_reference_reports_pid_without_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            install = self.fixture(Path(temporary))

            def active(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                if command[0] == "ps":
                    old = (install / "releases" / "b49").resolve()
                    return completed(command, stdout=f"42 {old}/secret-command --token hidden\n")
                return completed(command, returncode=1)

            with mock.patch("subprocess.run", side_effect=active):
                payload = self.maintain(install)
            serialized = json.dumps(payload)
            self.assertIn('"pid": 42', serialized)
            self.assertNotIn("secret-command", serialized)
            self.assertNotIn("hidden", serialized)

    def test_existing_regular_previous_selector_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            install = self.fixture(Path(temporary))
            (install / "previous").unlink()
            (install / "previous").write_text("b50\n", encoding="utf-8")
            with self.assertRaisesRegex(llmops_maintenance.MaintenanceError, "not a symlink"):
                self.maintain(install)

    def test_process_timeout_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            install = self.fixture(Path(temporary))
            with mock.patch(
                "subprocess.run", side_effect=subprocess.TimeoutExpired(["ps"], 10)
            ):
                payload = self.maintain(install)
            row = next(item for item in payload["releases"] if item["release"] == "b49")
            self.assertEqual(row["action"], "blocked")
            self.assertNotIn("command", json.dumps(row))

    def test_releases_directory_identity_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            original = llmops_maintenance._node_snapshot
            releases_calls = 0
            with mock.patch("subprocess.run", side_effect=self.no_references):
                reviewed = self.maintain(install)

            def drift(path: Path) -> llmops_maintenance.NodeSnapshot:
                nonlocal releases_calls
                snapshot = original(path)
                if path == install.resolve() / "releases":
                    releases_calls += 1
                    if releases_calls > 1:
                        return llmops_maintenance.NodeSnapshot(snapshot.device, snapshot.inode + 1)
                return snapshot

            with (
                mock.patch("subprocess.run", side_effect=self.no_references),
                mock.patch.object(llmops_maintenance, "_node_snapshot", side_effect=drift),
                self.assertRaisesRegex(llmops_maintenance.MaintenanceError, "releases directory changed"),
            ):
                self.maintain(
                    install,
                    apply=True,
                    plan_digest=reviewed["plan_digest"],
                )
            self.assertTrue((install / "releases/b49").is_dir())

    def test_release_walk_error_blocks_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)

            def failed_walk(path: Path, **kwargs: object) -> object:
                onerror = kwargs["onerror"]
                assert callable(onerror)
                onerror(PermissionError(13, "denied", str(path)))
                return iter(())

            with (
                mock.patch("subprocess.run", side_effect=self.no_references),
                mock.patch("os.walk", side_effect=failed_walk),
                self.assertRaisesRegex(llmops_maintenance.MaintenanceError, "not clean"),
            ):
                self.maintain(install, apply=True, run_dir=root / "state/run")
            self.assertTrue((install / "releases/b49").is_dir())

    def test_release_root_mount_is_not_removable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            old = (install / "releases/b49").resolve()
            original = llmops_maintenance.os.path.ismount
            with (
                mock.patch(
                    "llmops_kit.llmops_maintenance.os.path.ismount",
                    side_effect=lambda path: Path(path) == old or original(path),
                ),
                mock.patch("subprocess.run", side_effect=self.no_references),
                self.assertRaisesRegex(llmops_maintenance.MaintenanceError, "not clean"),
            ):
                self.maintain(install, apply=True, run_dir=root / "state/run")
            self.assertTrue(old.is_dir())

    def test_empty_manifest_is_unowned_and_retained(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            manifest = install / "releases/b49/release-manifest.json"
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["files"] = []
            manifest.write_text(json.dumps(document), encoding="utf-8")
            with mock.patch("subprocess.run", side_effect=self.no_references):
                payload = self.maintain(install, apply=True, run_dir=root / "state/run")
            row = next(item for item in payload["releases"] if item["release"] == "b49")
            self.assertEqual(row["action"], "skip")
            self.assertTrue((install / "releases/b49").is_dir())

    def test_previous_selector_path_in_config_pins_previous_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = self.fixture(root)
            config = root / "config"
            config.mkdir()
            (config / "service.json").write_text(
                json.dumps({"command": str(install.resolve() / "previous/app/bin/llmops")}),
                encoding="utf-8",
            )
            with mock.patch("subprocess.run", side_effect=self.no_references):
                payload = self.maintain(install, config_roots=(config,))
            previous = next(item for item in payload["releases"] if item["release"] == "b50")
            self.assertEqual(previous["action"], "keep")
            self.assertTrue((install / "previous").is_symlink())


if __name__ == "__main__":
    unittest.main()
