import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llmops_kit import llmops_autosync as sync


class AutomaticSyncTests(unittest.TestCase):
    def test_scope(self):
        with patch.object(sync, "_run") as run:
            for command in ("plan", "update", "rollback", "help"):
                sync.sync_for_command(argparse.Namespace(command=command))
            for override in ({"config_home": "/disposable"}, {"inventory": "/disposable"},
                             {"local": True}, {"plan": True}, {"status_host": "peer"}):
                sync.sync_for_command(argparse.Namespace(command="status", **override))
            sync.sync_for_command(argparse.Namespace(command="stack", stack_command="plan"))
            self.assertFalse(run.called)
            args = argparse.Namespace(command="status")
            sync.sync_for_command(args)
            self.assertTrue(args.autosync_lifecycle)
            run.assert_called_once_with("sync")

    def test_only_verified_program_can_run(self):
        if os.geteuid() == 0:
            self.skipTest("authority hooks never run as root")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / "auto-sync.py"
            program = b"print('reviewed')\n"
            script.write_bytes(program)
            script.chmod(0o600)
            policy = root / "auto-sync.json"
            policy.write_text(json.dumps({"schema_version": 1, "program_sha256": hashlib.sha256(program).hexdigest()}))
            policy.chmod(0o600)
            with patch.dict(os.environ, {"LLMOPS_AUTOSYNC_ACTIVE": "0"}), patch.object(sync, "_install_root", return_value=root), patch.object(
                sync.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"", b"")
            ) as run:
                sync._run("sync")
                self.assertEqual(run.call_args.kwargs["input"], program)
                script.chmod(0o644)
                sync._run("sync")
                script.chmod(0o600)
                script.write_bytes(b"print('not reviewed')\n")
                sync._run("sync")
                self.assertEqual(run.call_count, 1)

    def test_recursion_guard(self):
        with patch.dict(os.environ, {"LLMOPS_AUTOSYNC_ACTIVE": "1"}), patch.object(sync, "_install_root") as root:
            sync._run("sync")
            root.assert_not_called()


if __name__ == "__main__":
    unittest.main()
