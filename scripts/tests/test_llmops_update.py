#!/usr/bin/env python
"""Remote update planning, verification, and rollback tests."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from llmops_kit import llmops_update
from llmops_kit.llmops_transfer_stage import TransferStage, TransferStageError, transfer_stage


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
                result = llmops_update.main(["--apply", "--archive", str(archive), "--checksum-file", str(checksum), "--host", "peer", "--config-home", str(root / "config"), "--json"])
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
                result = llmops_update.main(["--apply", "--local-only", "--archive", str(archive), "--checksum-file", str(checksum), "--prefix", str(root), "--config-home", str(root / "config"), "--json"])
        self.assertEqual(result, 0)

    def test_release_policy_comes_from_products_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "current-config"
            config.mkdir()
            target = "candidate-next"
            repository = "example/toolkit"
            (config / "products.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "products": {
                            "llm-ops-kit": {
                                "latest_version": target,
                                "release_repository": repository,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                llmops_update.release_policy(root, None),
                (target, repository),
            )

    def test_update_defaults_to_every_catalog_host(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "LLM-Ops-Kit-candidate-next.tar.xz"
            archive.write_bytes(b"unused plan fixture")
            with (
                mock.patch.object(
                    llmops_update, "_select_hosts", return_value=[("peer", HOST)]
                ) as select_hosts,
                mock.patch.object(
                    llmops_update,
                    "_remote_preflight",
                    return_value={"host": "peer", "ok": True, "version": "current"},
                ),
            ):
                result = llmops_update.main(
                    ["--plan", "--archive", str(archive), "--config-home", str(root / "config"), "--json"]
                )
            self.assertEqual(result, 0)
            self.assertTrue(select_hosts.call_args.args[0].all_hosts)

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
        with mock.patch.object(llmops_update, "_run_remote", return_value=completed) as run_remote:
            result = llmops_update._remote_verify("peer", HOST, "beta-2", 10)
        self.assertEqual(result, {"version": "beta-2", "catalog_hash": "abc123", "config_hash": "def456"})
        self.assertIn(
            "LLMOPS_AUTO_UPDATE_ACTIVE=1",
            run_remote.call_args.args[1],
        )

    def test_remote_apply_reselects_target_when_old_peer_has_it_as_previous(self) -> None:
        completed = subprocess.CompletedProcess([], 0, "selected previous\n", "")
        verification = {"version": "beta-2", "catalog_hash": "abc123", "config_hash": "def456"}
        with (
            mock.patch.object(llmops_update, "_run_remote", return_value=completed) as run_remote,
            mock.patch.object(llmops_update, "_remote_verify", return_value=verification),
        ):
            stage = TransferStage("updates")
            result = llmops_update._remote_apply(
                "peer", HOST, stage.file_expression("a.tar.xz"), stage.file_expression("a.sha256"), "beta-2", 10, stage=stage
            )
        script = run_remote.call_args.args[1]
        self.assertIn('test "$previous" = "$target"', script)
        self.assertIn("update --rollback", script)
        self.assertEqual(result["version"], "beta-2")

    def test_verification_failure_rolls_back_the_updated_host(self) -> None:
        completed = subprocess.CompletedProcess([], 0, "installed\n", "")
        rollback = {"host": "peer", "ok": True, "output": "", "error": ""}
        with (
            mock.patch.object(llmops_update, "_run_remote", return_value=completed),
            mock.patch.object(llmops_update, "_remote_verify", side_effect=llmops_update.UpdateError("bad identity")),
            mock.patch.object(llmops_update, "_remote_rollback", return_value=rollback) as remote_rollback,
        ):
            with self.assertRaisesRegex(llmops_update.UpdateError, "verification rollback"):
                stage = TransferStage("updates")
                llmops_update._remote_apply(
                    "peer", HOST, stage.file_expression("a.tar.xz"), stage.file_expression("a.sha256"), "beta-2", 10, stage=stage
                )
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
                mock.patch.object(
                    llmops_update, "_run_remote", return_value=subprocess.CompletedProcess([], 0, "", "")
                ) as remote_command,
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
                        "--config-home",
                        str(root / "config"),
                    ]
                )
            self.assertEqual(result, 2)
            rollback.assert_called_once_with("first", first, 900)
            cleanup = [call for call in remote_command.call_args_list if 'rm -rf "$transfer"' in call.args[1]]
            self.assertEqual([call.args[0]["name"] for call in cleanup], ["second", "first"])
            self.assertTrue(archive.is_file())
            self.assertTrue(checksum.is_file())

    def test_success_cleans_stage_after_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "LLM-Ops-Kit-beta-2.tar.xz"
            archive.write_bytes(b"verified release")
            checksum = root / "selected.sha256"
            checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest(), encoding="utf-8")
            events: list[str] = []

            def remote(_host: dict[str, object], command: str, _timeout: int) -> subprocess.CompletedProcess[str]:
                if 'rm -rf "$transfer"' in command:
                    events.append("cleanup")
                elif 'trap ' in command:
                    events.append("apply")
                else:
                    events.append("create")
                return subprocess.CompletedProcess([], 0, "", "")

            def verify(*_args: object) -> dict[str, object]:
                events.append("verify")
                return {"version": "beta-2"}

            with (
                mock.patch.object(llmops_update, "_select_hosts", return_value=[("peer", HOST)]),
                mock.patch.object(llmops_update, "_remote_preflight", return_value={"version": "beta-1"}),
                mock.patch.object(llmops_update, "_run_remote", side_effect=remote),
                mock.patch.object(llmops_update, "_remote_verify", side_effect=verify),
                mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as scp,
            ):
                status = llmops_update.main(["--apply", "--archive", str(archive), "--checksum-file", str(checksum)])
            self.assertEqual(status, 0)
            self.assertEqual(events, ["create", "apply", "verify", "cleanup"])
            self.assertIn(".cache/llm-ops/updates/transfer-", scp.call_args.args[0][-1])
            self.assertTrue(archive.is_file())
            self.assertTrue(checksum.is_file())


class TransferStageTests(unittest.TestCase):
    def shell(self, home: Path, script: str, timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/sh", "-c", script],
            env={**os.environ, "HOME": str(home)},
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def test_stages_are_private_distinct_and_cleanup_preserves_siblings(self) -> None:
        with tempfile.TemporaryDirectory(prefix="llmops stage ") as temporary:
            home = Path(temporary)
            legacy = home / ".cache/llm-ops/updates/old"
            legacy.mkdir(parents=True)
            run = lambda script, timeout: self.shell(home, script, timeout)
            with transfer_stage("updates", run=run, host="test", timeout=10) as first:
                with transfer_stage("updates", run=run, host="test", timeout=10) as second:
                    self.assertNotEqual(first.relative, second.relative)
                    path = home / first.relative
                    self.assertEqual(path.stat().st_mode & 0o777, 0o700)
                    (path / "extracted").mkdir()
                    (path / "extracted/payload").write_text("temporary", encoding="utf-8")
                    self.assertEqual(run(first.use_command("exit 23"), 10).returncode, 23)
                    self.assertFalse(path.with_name(path.name + ".in-use").exists())
            self.assertFalse((home / first.relative).exists())
            self.assertFalse((home / second.relative).exists())
            self.assertTrue(legacy.is_dir())

    def test_cleanup_does_not_remove_stage_in_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            run = lambda script, timeout: self.shell(home, script, timeout)
            with self.assertLogs("llmops_kit.llmops_transfer_stage", level="WARNING") as logs:
                with transfer_stage("config", run=run, host="test", timeout=10) as stage:
                    path = home / stage.relative
                    path.with_name(path.name + ".in-use").mkdir()
            self.assertTrue(path.is_dir())
            self.assertIn("cleanup deferred", logs.output[0])

    def test_refuses_symlinked_cache_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            other = home / "outside"
            other.mkdir()
            (home / ".cache").symlink_to(other)
            run = lambda script, timeout: self.shell(home, script, timeout)
            with self.assertRaises(TransferStageError):
                with transfer_stage("updates", run=run, host="test", timeout=10):
                    self.fail("symlinked cache accepted")
            self.assertEqual(list(other.iterdir()), [])

    def test_bootstrap_verifies_then_extracts_in_its_own_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="llmops boot ") as temporary:
            home = Path(temporary)
            run = lambda script, timeout: self.shell(home, script, timeout)
            for checksum_ok in (True, False):
                with self.subTest(checksum_ok=checksum_ok), transfer_stage(
                    "updates", run=run, host="test", timeout=10
                ) as stage:
                    path = home / stage.relative
                    archive = path / "fixture.tar.xz"
                    checksum = path / "fixture.sha256"
                    installer = b"#!/bin/sh\nprintf 'bootstrap called\\n'\n"
                    member = tarfile.TarInfo("fixture/scripts/install-runtime.sh")
                    member.size = len(installer)
                    with tarfile.open(archive, "w:xz") as bundle:
                        bundle.addfile(member, io.BytesIO(installer))
                    digest = hashlib.sha256(archive.read_bytes()).hexdigest() if checksum_ok else "0" * 64
                    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
                    with (
                        mock.patch.object(llmops_update, "_run_remote", side_effect=lambda _host, script, timeout: run(script, timeout)),
                        mock.patch.object(llmops_update, "_remote_verify", return_value={"version": "beta-2"}) as verify,
                    ):
                        args = ("peer", HOST, stage.file_expression(archive.name), stage.file_expression(checksum.name), "beta-2", 10)
                        if checksum_ok:
                            result = llmops_update._remote_apply(*args, stage=stage)
                            self.assertEqual(result["output"], "fixture.tar.xz: OK\nbootstrap called")
                            verify.assert_called_once()
                        else:
                            with self.assertRaisesRegex(llmops_update.UpdateError, "remote update failed"):
                                llmops_update._remote_apply(*args, stage=stage)
                            self.assertFalse((path / "extracted").exists())
                            verify.assert_not_called()
                self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
