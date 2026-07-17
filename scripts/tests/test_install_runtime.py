#!/usr/bin/env python3
"""Isolated installer, upgrade, repair, and uninstall tests."""

from __future__ import annotations

import os
import json
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "scripts" / "install-runtime.sh"
UNINSTALLER = REPO_ROOT / "scripts" / "uninstall-runtime.sh"


class InstallerTests(unittest.TestCase):
    def run_command(self, command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            self.fail(f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout}\n{completed.stderr}")
        return completed

    def test_fresh_upgrade_repair_uninstall_and_purge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            install = home / "install"
            public_bin = home / "bin"
            config = home / "config"
            data = home / "data"
            state = home / "state"
            cache = home / "cache"
            env = {
                **os.environ,
                "HOME": str(home),
                "LLMOPS_HOME": str(install),
                "LLMOPS_BIN_DIR": str(install / "bin"),
                "LLMOPS_CONFIG_HOME": str(config),
                "LLMOPS_DATA_HOME": str(data),
                "LLMOPS_STATE_HOME": str(state),
                "LLMOPS_CACHE_HOME": str(cache),
            }
            common = [
                "/usr/local/bin/bash",
                str(INSTALLER),
                "--source",
                str(REPO_ROOT),
                "--prefix",
                str(install),
                "--public-bin-dir",
                str(public_bin),
                "--state-home",
                str(state),
            ]
            self.run_command(common + ["--release-id", "release-1"], env)
            self.assertEqual((install / "current").resolve(), (install / "releases" / "release-1").resolve())
            self.assertFalse((install / "previous").exists())
            self.assertTrue((public_bin / "llmops").is_symlink())
            help_result = self.run_command([str(public_bin / "llmops"), "--help"], env)
            self.assertIn("status          Show aggregate component status", help_result.stdout)
            self.assertIn("deploy          Build and atomically deploy", help_result.stdout)
            self.run_command([str(public_bin / "llmops"), "init", "--preset", "single-host"], env)
            self.run_command([str(public_bin / "llmops"), "doctor"], env)

            self.run_command(common + ["--release-id", "release-2"], env)
            self.assertEqual((install / "current").resolve(), (install / "releases" / "release-2").resolve())
            self.assertEqual((install / "previous").resolve(), (install / "releases" / "release-1").resolve())
            self.run_command(common + ["--repair"], env)
            self.run_command(common + ["--repair"], env)

            uninstall = [
                "/usr/local/bin/bash",
                str(UNINSTALLER),
                "--prefix",
                str(install),
                "--public-bin-dir",
                str(public_bin),
                "--config-home",
                str(config),
                "--data-home",
                str(data),
                "--state-home",
                str(state),
                "--cache-home",
                str(cache),
            ]
            self.run_command(uninstall, env)
            self.assertFalse(install.exists())
            self.assertTrue(config.exists())

            self.run_command(common + ["--release-id", "release-3"], env)
            self.run_command(uninstall + ["--purge"], env)
            for path in (install, config, data, state, cache):
                self.assertFalse(path.exists(), str(path))

    def test_git_archive_is_installable_and_proxy_render_uses_python(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            shutil.copytree(
                REPO_ROOT / "scripts",
                repository / "scripts",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(["git", "-C", str(repository), "add", "scripts"], check=True)
            subprocess.run(
                [
                    "git", "-C", str(repository),
                    "-c", "user.name=LLM Ops Test",
                    "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "archive fixture",
                ],
                check=True,
            )
            archive = root / "source.tar"
            with archive.open("wb") as stream:
                subprocess.run(["git", "-C", str(repository), "archive", "HEAD"], stdout=stream, check=True)
            source = root / "source"
            source.mkdir()
            with tarfile.open(archive) as bundle:
                bundle.extractall(source)
            self.assertFalse((source / "bin").exists())
            env = {
                **os.environ,
                "HOME": str(root / "home"),
                "LLMOPS_HOME": str(root / "install"),
                "LLMOPS_CONFIG_HOME": str(root / "config"),
                "LLMOPS_STATE_HOME": str(root / "state"),
            }
            install = [
                "/usr/local/bin/bash",
                str(source / "scripts" / "install-runtime.sh"),
                "--source", str(source),
                "--prefix", str(root / "install"),
                "--public-bin-dir", str(root / "public-bin"),
                "--state-home", str(root / "state"),
                "--release-id", "archive-test",
            ]
            self.run_command(install, env)
            payload = root / "payload.json"
            payload.write_text(
                json.dumps({"messages": [{"role": "user", "content": "test"}]}),
                encoding="utf-8",
            )
            self.run_command(
                [str(root / "install" / "bin" / "model-proxy"), "render", "--input", str(payload)],
                env,
            )

    def test_model_restart_archives_existing_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "state" / "logs" / "tts-server-test.log"
            log.parent.mkdir(parents=True)
            log.write_text("prior crash evidence\n", encoding="utf-8")
            env = {
                **os.environ,
                "HOME": str(root),
                "LLMOPS_STATE_HOME": str(root / "state"),
            }
            self.run_command(
                [
                    "/usr/local/bin/bash",
                    "-c",
                    '. "$1"; archive_log_for_restart "$2"; prepare_log_file "$2"',
                    "_",
                    str(REPO_ROOT / "scripts" / "lib" / "common.sh"),
                    str(log),
                ],
                env,
            )
            archived = list(log.parent.glob("tts-server-test.log.*"))
            self.assertEqual(len(archived), 1)
            self.assertEqual(archived[0].read_text(encoding="utf-8"), "prior crash evidence\n")
            self.assertEqual(log.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
