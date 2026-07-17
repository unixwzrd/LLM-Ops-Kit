#!/usr/bin/env python3
"""Isolated installer, upgrade, repair, and uninstall tests."""

from __future__ import annotations

import os
import subprocess
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


if __name__ == "__main__":
    unittest.main()
