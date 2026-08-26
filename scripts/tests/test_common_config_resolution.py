#!/usr/bin/env python
"""Tests for shell runtime path resolution."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


COMMON = Path(__file__).resolve().parents[1] / "lib" / "common.sh"
BASH = shutil.which("bash") or "/bin/bash"


class CommonConfigResolutionTests(unittest.TestCase):
    def test_installed_snapshot_precedes_xdg_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = root / "install"
            snapshot = install / "current" / "config"
            snapshot.mkdir(parents=True)
            (snapshot / "config.json").write_text("{}\n", encoding="utf-8")
            env = {
                **os.environ,
                "HOME": str(root),
                "LLMOPS_HOME": str(install),
                "XDG_CONFIG_HOME": str(root / "xdg"),
            }
            env.pop("LLMOPS_CONFIG_HOME", None)
            completed = subprocess.run(
                [
                    BASH,
                    "-c",
                    f'. "{COMMON}"; printf "%s\\n" "$LLMOPS_CONFIG_HOME"',
                ],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(completed.stdout.strip(), str(snapshot))


if __name__ == "__main__":
    unittest.main()
