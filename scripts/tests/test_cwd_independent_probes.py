"""Profile probes must not import from an unavailable caller working directory."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from unittest import mock

from llmops_kit.llmops_drivers import CommandResult, ComponentRunner, DriverError
from test_llmops_control import ControlFixture


ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash") or "/bin/bash"


class WorkingDirectoryProbeTests(unittest.TestCase):
    def test_profile_resolution_avoids_failing_cwd_import_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            caller = root / "caller"
            bootstrap = root / "bootstrap"
            caller.mkdir()
            bootstrap.mkdir()
            # Reproduce iCloud FileFinder failure without touching cloud storage.
            (bootstrap / "sitecustomize.py").write_text(
                "import importlib._bootstrap_external as ext, os\n"
                "original = ext.FileFinder._fill_cache\n"
                "blocked = os.path.realpath(os.environ['PROBE_BLOCKED_CWD'])\n"
                "def fill(self):\n"
                "    if os.path.realpath(self.path) == blocked:\n"
                "        raise TimeoutError(60, 'simulated unavailable working directory', blocked)\n"
                "    return original(self)\n"
                "ext.FileFinder._fill_cache = fill\n",
                encoding="utf-8",
            )
            profile = caller / "profile.json"
            profile.write_text(json.dumps({
                "schema_version": 2, "name": "probe-fixture", "type": "llm",
                "model_path": str(root / "fixture.gguf"),
            }), encoding="utf-8")
            env = {**os.environ, "HOME": str(root), "PROBE_BLOCKED_CWD": str(caller),
                   "PYTHONPATH": os.pathsep.join((str(bootstrap), str(ROOT / "src"))),
                   "LLMOPS_CONFIG_HOME": str(root / "config"),
                   "LLMOPS_STATE_HOME": str(root / "state"),
                   "LLMOPS_PYTHON_BIN": sys.executable}
            env.pop("PYTHONSAFEPATH", None)
            bare = subprocess.run(
                [sys.executable, "-m", "llmops_kit.llmops_profiles", "model", "probe-fixture",
                 "--profile-path", str(profile), "--resolve-references"],
                cwd=caller, env=env, capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(bare.returncode, 0)
            self.assertIn("TimeoutError", bare.stderr)
            command = (f". {shlex.quote(str(ROOT / 'scripts/lib/common.sh'))}; "
                       "source_json_model_profile_defaults probe-fixture profile.json")
            safe = subprocess.run([BASH, "-c", "set -e; " + command], cwd=caller,
                                  env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(safe.returncode, 0, safe.stdout + safe.stderr)


class ProbeFailureLifecycleTests(ControlFixture):
    def test_shell_profile_failure_is_unknown_not_stopped(self) -> None:
        base = self.topology.resolve_component("sample:chat")
        for driver in ("modelctl", "model-proxy", "tts-bridge"):
            with self.subTest(driver=driver):
                component = replace(base, driver=driver)
                result = CommandResult(component.qualified_id, "status", "fixture", 1, "",
                                       "Could not import runpy module\nTraceback (most recent call last):\nTimeoutError: unavailable working directory")
                self.assertEqual(ComponentRunner.lifecycle_from_result(component, result), "unknown")
                with mock.patch.object(ComponentRunner, "status", return_value=result):
                    with self.assertRaises(DriverError):
                        ComponentRunner(self.topology).is_running(component)

    def test_explicit_stopped_model_status_still_means_stopped(self) -> None:
        component = self.topology.resolve_component("sample:chat")
        for status in ("status=stopped", "status=stale", "stopped", "not running"):
            result = CommandResult(component.qualified_id, "status", "fixture", 1,
                                   f"fixture-model: {status}\n  running=false", "")
            self.assertEqual(ComponentRunner.lifecycle_from_result(component, result), "stopped")


if __name__ == "__main__":
    unittest.main()
