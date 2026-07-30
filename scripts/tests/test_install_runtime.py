#!/usr/bin/env python
"""Isolated installer, upgrade, repair, and uninstall tests."""

from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "scripts" / "install-runtime.sh"
UNINSTALLER = REPO_ROOT / "scripts" / "uninstall-runtime.sh"
BUILDER = REPO_ROOT / "scripts" / "build-release.py"


class InstallerTests(unittest.TestCase):
    def run_command(self, command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            self.fail(f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout}\n{completed.stderr}")
        return completed

    def release_source(self, root: Path, version: str) -> Path:
        output = root / f"artifact-{version}"
        subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--output-dir",
                str(output),
                "--version",
                version,
                "--allow-dirty",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        extracted = root / f"source-{version}"
        extracted.mkdir()
        with tarfile.open(output / f"LLM-Ops-Kit-{version}.tar.xz", "r:xz") as bundle:
            bundle.extractall(extracted, filter="data")
        return extracted / f"LLM-Ops-Kit-{version}"

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
                "LLMOPS_UV_BIN": shutil.which("uv") or "uv",
            }
            source = self.release_source(home, "installer-test")
            common = [
                "/usr/local/bin/bash",
                str(INSTALLER),
                "--source",
                str(source),
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
            self.assertIn("Show aggregate local and remote component status", help_result.stdout)
            self.assertIn("Show or reconcile canonical configuration", help_result.stdout)
            self.run_command([str(public_bin / "llmops"), "init", "--preset", "single-host"], env)
            inventory = json.loads((config / "inventory.json").read_text(encoding="utf-8"))
            self.assertEqual(inventory["hosts"][0]["install_root"], str(install))
            self.assertEqual(inventory["hosts"][0]["public_bin_dir"], str(public_bin))
            self.run_command([str(public_bin / "llmops"), "doctor"], env)

            shutil.copytree(config, install / "current" / "config")
            self.run_command(common + ["--release-id", "release-2"], env)
            self.assertEqual((install / "current").resolve(), (install / "releases" / "release-2").resolve())
            self.assertEqual((install / "previous").resolve(), (install / "releases" / "release-1").resolve())
            self.assertTrue((install / "current-config").is_symlink())
            retained = install / "releases" / "release-2" / "retained-marker"
            retained.write_text("preserve existing immutable release\n", encoding="utf-8")
            duplicate = subprocess.run(common + ["--release-id", "release-2"], env=env, capture_output=True, text=True, check=False)
            self.assertEqual(duplicate.returncode, 2)
            self.assertIn("release already exists", duplicate.stderr)
            self.assertEqual(retained.read_text(encoding="utf-8"), "preserve existing immutable release\n")
            default_env = {key: value for key, value in env.items() if key != "LLMOPS_CONFIG_HOME"}
            shown = self.run_command([str(public_bin / "llmops"), "config", "show", "--json"], default_env)
            self.assertEqual(Path(json.loads(shown.stdout)["paths"]["config_home"]).resolve(), (install / "current-config").resolve())

            prior = install / "releases" / "release-1"
            (prior / "scripts").mkdir(exist_ok=True)
            prior_llmops = prior / "scripts" / "llmops"
            prior_llmops.write_text("#!/bin/sh\necho pre-beta\n", encoding="utf-8")
            prior_llmops.chmod(0o755)
            shutil.rmtree(prior / "app")
            self.run_command(common + ["--rollback"], env)
            self.assertEqual((install / "current").resolve(), prior.resolve())
            self.assertEqual((public_bin / "llmops").resolve(), prior_llmops.resolve())
            self.assertEqual(json.loads((install / "install.json").read_text(encoding="utf-8"))["active_release"], str(prior))
            self.run_command(common + ["--rollback"], env)
            self.assertEqual((install / "current").resolve(), (install / "releases" / "release-2").resolve())
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

    def test_unsupported_platform_fails_before_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            uname = fake_bin / "uname"
            uname.write_text("#!/bin/sh\necho Linux\n", encoding="utf-8")
            uname.chmod(0o755)
            install = root / "install"
            completed = subprocess.run(
                [
                    "/usr/local/bin/bash",
                    str(INSTALLER),
                    "--source",
                    str(REPO_ROOT),
                    "--prefix",
                    str(install),
                    "--release-id",
                    "unsupported-test",
                ],
                env={**os.environ, "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("this beta supports macOS only", completed.stderr)
            self.assertFalse(install.exists())

    def test_release_archive_is_installable_and_proxy_render_uses_application_python(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.release_source(root, "archive-test")
            self.assertFalse((source / "bin").exists())
            env = {
                **os.environ,
                "HOME": str(root / "home"),
                "LLMOPS_HOME": str(root / "install"),
                "LLMOPS_CONFIG_HOME": str(root / "config"),
                "LLMOPS_STATE_HOME": str(root / "state"),
                "LLMOPS_UV_BIN": shutil.which("uv") or "uv",
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
            self.assertTrue((root / "install" / "current" / "app" / "bin" / "python").is_file())
            runtime_wrapper = (root / "install" / "current" / "bin" / "modelctl").read_text(encoding="utf-8")
            self.assertIn("current-config", runtime_wrapper)
            payload = root / "payload.json"
            payload.write_text(
                json.dumps({"messages": [{"role": "user", "content": "test"}]}),
                encoding="utf-8",
            )
            self.run_command(
                [str(root / "install" / "bin" / "model-proxy"), "render", "--input", str(payload)],
                env,
            )

            minimal = root / "minimal"
            minimal_env = {
                **env,
                "LLMOPS_HOME": str(minimal / "install"),
                "LLMOPS_CONFIG_HOME": str(minimal / "config"),
                "LLMOPS_STATE_HOME": str(minimal / "state"),
            }
            self.run_command(
                [
                    "/usr/local/bin/bash",
                    str(source / "scripts" / "install-runtime.sh"),
                    "--source",
                    str(source),
                    "--prefix",
                    str(minimal / "install"),
                    "--public-bin-dir",
                    str(minimal / "bin"),
                    "--state-home",
                    str(minimal / "state"),
                    "--release-id",
                    "minimal-test",
                    "--minimal",
                ],
                minimal_env,
            )
            self.run_command([str(minimal / "bin" / "llmops"), "adapter", "doctor"], minimal_env)
            textual = subprocess.run(
                [str(minimal / "install" / "current" / "app" / "bin" / "python"), "-c", "import importlib.util; raise SystemExit(importlib.util.find_spec('textual') is not None)"],
                env=minimal_env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(textual.returncode, 0)
            tui = subprocess.run(
                [str(minimal / "bin" / "llmops"), "tui"],
                env=minimal_env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(tui.returncode, 2)
            self.assertIn("Textual is not installed", tui.stdout)

    def test_shipped_shell_scripts_are_compatible_with_macos_bash(self) -> None:
        unsupported_case_expansion = re.compile(r"\$\{[^}\n]+(?:,,|\^\^)[^}\n]*\}")
        for path in (REPO_ROOT / "scripts").rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if not text.startswith("#!") or "bash" not in text.splitlines()[0]:
                continue
            self.assertIsNone(
                unsupported_case_expansion.search(text),
                f"{path.relative_to(REPO_ROOT)} uses Bash 4 case expansion",
            )

    def test_model_restart_archives_existing_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "state" / "logs" / "tts-server-test.log"
            log.parent.mkdir(parents=True)
            log.write_text("prior crash evidence\n", encoding="utf-8")
            original_inode = log.stat().st_ino
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
            self.assertEqual(log.stat().st_ino, original_inode)

    def test_size_rotation_preserves_active_log_inode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "state" / "logs" / "model.log"
            log.parent.mkdir(parents=True)
            log.write_text("oversized log\n", encoding="utf-8")
            original_inode = log.stat().st_ino
            env = {
                **os.environ,
                "HOME": str(root),
                "LLMOPS_STATE_HOME": str(root / "state"),
            }
            self.run_command(
                [
                    "/usr/local/bin/bash",
                    "-c",
                    '. "$1"; rotate_log_if_needed "$2" 1',
                    "_",
                    str(REPO_ROOT / "scripts" / "lib" / "common.sh"),
                    str(log),
                ],
                env,
            )
            archived = list(log.parent.glob("model.log.*"))
            self.assertEqual(len(archived), 1)
            self.assertEqual(archived[0].read_text(encoding="utf-8"), "oversized log\n")
            self.assertEqual(log.read_text(encoding="utf-8"), "")
            self.assertEqual(log.stat().st_ino, original_inode)


if __name__ == "__main__":
    unittest.main()
