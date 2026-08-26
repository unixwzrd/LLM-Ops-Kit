#!/usr/bin/env python
"""Tests for repository-free release artifacts and bootstrap installation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER = REPO_ROOT / "scripts" / "build-release.py"
BOOTSTRAP = REPO_ROOT / "scripts" / "bootstrap-install.sh"
BASH = shutil.which("bash") or "/bin/bash"


class ReleaseDistributionTests(unittest.TestCase):
    def run_command(
        self,
        command: list[str],
        *,
        env: dict[str, str],
        expected: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        """Run command and assert its return code."""

        completed = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
        self.assertEqual(
            completed.returncode,
            expected,
            f"command failed: {' '.join(command)}\n{completed.stdout}\n{completed.stderr}",
        )
        return completed

    def committed_source(self, root: Path) -> Path:
        """Create a clean committed source tree containing the current work."""

        source = root / "source"
        source.mkdir()
        archive = root / "head.tar"
        with archive.open("wb") as stream:
            subprocess.run(["git", "-C", str(REPO_ROOT), "archive", "HEAD"], stdout=stream, check=True)
        with tarfile.open(archive) as bundle:
            bundle.extractall(source, filter="data")
        changed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--modified", "--others", "--exclude-standard"],
            capture_output=True,
            check=True,
        )
        current_files = [REPO_ROOT / item.decode() for item in changed.stdout.split(b"\0") if item]
        for path in current_files:
            if not path.is_file():
                continue
            relative = path.relative_to(REPO_ROOT)
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "-c",
                "user.name=LLM Ops Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-qm",
                "release fixture",
            ],
            check=True,
        )
        return source

    def archived_source(self, root: Path) -> Path:
        """Extract HEAD exactly as a release consumer receives it."""

        source = root / "archived-source"
        source.mkdir()
        archive = root / "head-only.tar"
        with archive.open("wb") as stream:
            subprocess.run(
                ["git", "-C", str(REPO_ROOT), "archive", "HEAD"],
                stdout=stream,
                check=True,
            )
        with tarfile.open(archive) as bundle:
            bundle.extractall(source, filter="data")
        self.assertFalse((source / ".git").exists())
        return source

    def test_runtime_artifact_installs_without_checkout(self) -> None:
        """Build, inspect, and install one release artifact."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.archived_source(root)
            output = root / "output"
            env = {**os.environ, "HOME": str(root / "home")}
            self.run_command(
                [
                    sys.executable,
                    str(source / "scripts" / "build-release.py"),
                    "--source",
                    str(source),
                    "--output-dir",
                    str(output),
                    "--version",
                    "test-v1",
                ],
                env=env,
            )
            artifact = output / "LLM-Ops-Kit-test-v1.tar.xz"
            checksum = output / "LLM-Ops-Kit-test-v1.tar.xz.sha256"
            manifest = output / "LLM-Ops-Kit-test-v1.manifest.json"
            self.assertTrue(artifact.is_file())
            self.assertTrue(checksum.is_file())
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["version"], "test-v1")
            with tarfile.open(artifact, "r:xz") as bundle:
                names = bundle.getnames()
            self.assertIn("LLM-Ops-Kit-test-v1/scripts/llmops", names)
            self.assertIn("LLM-Ops-Kit-test-v1/release-manifest.json", names)
            self.assertNotIn("LLM-Ops-Kit-test-v1/scripts/build-release.py", names)
            self.assertNotIn("LLM-Ops-Kit-test-v1/scripts/precheck", names)
            self.assertFalse(any("tests" in Path(name).parts for name in names))
            self.assertFalse(any(name.endswith((".env", ".pyc", ".DS_Store")) for name in names))
            self.assertFalse(any(Path(name).name == ".gitignore" for name in names))
            self.assertTrue(any("markupsafe" in name.lower() and "arm64" in name for name in names))
            self.assertTrue(any("markupsafe" in name.lower() and "x86_64" in name for name in names))
            self.assertTrue((output / "install-llmops").is_file())
            self.assertTrue((output / "install-llmops.sha256").is_file())

            install = root / "install"
            public_bin = root / "bin"
            state = root / "state"
            env["LLMOPS_HOME"] = str(install)
            env["LLMOPS_BIN_DIR"] = str(install / "bin")
            env["LLMOPS_STATE_HOME"] = str(state)
            self.run_command(
                [
                    BASH,
                    str(source / "scripts" / "bootstrap-install.sh"),
                    "--archive",
                    str(artifact),
                    "--checksum-file",
                    str(checksum),
                    "--prefix",
                    str(install),
                    "--public-bin-dir",
                    str(public_bin),
                    "--state-home",
                    str(state),
                ],
                env=env,
            )
            self.assertEqual((install / "current").resolve(), (install / "releases" / "test-v1").resolve())
            self.assertFalse((install / "current" / "scripts" / "precheck").exists())
            self.assertFalse((install / "current" / "scripts" / "build-release.py").exists())
            help_result = self.run_command([str(public_bin / "llmops"), "--help"], env=env)
            self.assertIn("Show aggregate local and remote component status", help_result.stdout)
            self.assertIn("Check, plan, or apply verified local and remote releases", help_result.stdout)

            update_output = root / "update-output"
            self.run_command(
                [
                    sys.executable,
                    str(source / "scripts" / "build-release.py"),
                    "--source",
                    str(source),
                    "--output-dir",
                    str(update_output),
                    "--version",
                    "test-v2",
                ],
                env=env,
            )
            update_artifact = update_output / "LLM-Ops-Kit-test-v2.tar.xz"
            update_checksum = update_output / "LLM-Ops-Kit-test-v2.tar.xz.sha256"
            plan = self.run_command(
                [
                    str(public_bin / "llmops"),
                    "update",
                    "--plan",
                    "--local-only",
                    "--archive",
                    str(update_artifact),
                    "--checksum-file",
                    str(update_checksum),
                    "--prefix",
                    str(install),
                    "--public-bin-dir",
                    str(public_bin),
                    "--state-home",
                    str(state),
                    "--json",
                ],
                env=env,
            )
            self.assertEqual(json.loads(plan.stdout)["available"], "test-v2")
            self.assertEqual((install / "current").resolve(), (install / "releases" / "test-v1").resolve())
            self.run_command(
                [
                    str(public_bin / "llmops"),
                    "update",
                    "--apply",
                    "--local-only",
                    "--archive",
                    str(update_artifact),
                    "--checksum-file",
                    str(update_checksum),
                    "--prefix",
                    str(install),
                    "--public-bin-dir",
                    str(public_bin),
                    "--state-home",
                    str(state),
                ],
                env=env,
            )
            self.assertEqual((install / "current").resolve(), (install / "releases" / "test-v2").resolve())
            self.assertEqual((install / "previous").resolve(), (install / "releases" / "test-v1").resolve())

    def test_bootstrap_rejects_tampered_archive(self) -> None:
        """Reject an archive whose digest does not match its checksum file."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.committed_source(root)
            output = root / "output"
            env = {**os.environ, "HOME": str(root / "home")}
            self.run_command(
                [
                    sys.executable,
                    str(source / "scripts" / "build-release.py"),
                    "--source",
                    str(source),
                    "--output-dir",
                    str(output),
                    "--version",
                    "tamper-test",
                ],
                env=env,
            )
            artifact = output / "LLM-Ops-Kit-tamper-test.tar.xz"
            artifact.write_bytes(artifact.read_bytes() + b"tampered")
            completed = self.run_command(
                [
                    BASH,
                    str(source / "scripts" / "bootstrap-install.sh"),
                    "--archive",
                    str(artifact),
                    "--checksum-file",
                    str(output / "LLM-Ops-Kit-tamper-test.tar.xz.sha256"),
                    "--prefix",
                    str(root / "install"),
                ],
                env=env,
                expected=2,
            )
            self.assertIn("checksum mismatch", completed.stderr)
            self.assertFalse((root / "install").exists())


if __name__ == "__main__":
    unittest.main()
