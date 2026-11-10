"""Tests for optional, constrained operator routing without real SSH."""

import json
import os
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from llmops_kit import llmops_cli
from llmops_kit.llmops_config import ConfigError


class OperatorRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.record = {"host": "operator.example", "user": "ops", "identity_file": "/tmp/key",
                       "known_hosts_file": "/tmp/known", "executable": "/opt/operator gate"}
        (self.root / "catalog.json").write_text("{}", encoding="utf-8")
        self.write_config()

    def write_config(self):
        (self.root / "config.json").write_text(
            json.dumps({"control": {"service_operator": self.record}}), encoding="utf-8")

    def route(self, argv):
        normalized = llmops_cli.normalize_global_options(argv)
        args = llmops_cli.build_parser().parse_args(normalized)
        return llmops_cli._route_operator_operation(args, normalized, config_home=self.root)

    @mock.patch.dict(os.environ, {"LLMOPS_OPERATOR_DISPATCHED": "0"})
    @mock.patch("llmops_kit.llmops_cli.subprocess.run")
    def test_allowlist_and_exact_remote_arguments(self, run):
        run.return_value.returncode = 7
        for argv in (["status", "--json"], ["plan"], ["stack", "list"],
                     ["stack", "plan", "start", "my stack"], ["stack", "start"],
                     ["stack", "stop"], ["stack", "restart"], ["stack", "status"],
                     ["component", "plan", "start", "a;echo bad"],
                     ["component", "start", "a"], ["component", "stop", "a"],
                     ["component", "restart", "a"], ["component", "status", "a"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.route(argv), 7)
                command = run.call_args.args[0]
                self.assertEqual(shlex.split(command[-1]), [self.record["executable"], *llmops_cli.normalize_global_options(argv)])
                self.assertIn("StrictHostKeyChecking=yes", command)
                self.assertIn("IdentitiesOnly=yes", command)
                self.assertIn("ClearAllForwardings=yes", command)
                self.assertEqual(run.call_args.kwargs, {"check": False})

    @mock.patch("llmops_kit.llmops_cli.subprocess.run")
    def test_exclusions_and_recursion_guard(self, run):
        for argv in (["status", "--local"], ["status", "--config-home", "/tmp/x"],
                     ["status", "--inventory=/tmp/x"], ["component", "logs", "a"],
                     ["component", "list"], ["config", "show"]):
            with self.subTest(argv=argv):
                self.assertIsNone(self.route(argv))
        with mock.patch.dict(os.environ, {"LLMOPS_OPERATOR_DISPATCHED": "1"}):
            self.assertIsNone(self.route(["status"]))
        run.assert_not_called()

    @mock.patch("llmops_kit.llmops_cli._route_authority_operation")
    @mock.patch("llmops_kit.llmops_cli.subprocess.run")
    def test_main_dispatches_before_authority(self, run, authority):
        run.return_value.returncode = 3
        with mock.patch.dict(os.environ, {"LLMOPS_CONFIG_HOME": str(self.root),
                                         "LLMOPS_OPERATOR_DISPATCHED": "0"}):
            self.assertEqual(llmops_cli.main(["stack", "start", "--json"]), 3)
        authority.assert_not_called()

    @mock.patch("llmops_kit.llmops_cli.subprocess.run")
    def test_absence_and_invalid_records(self, run):
        self.record = None
        self.write_config()
        self.assertIsNone(self.route(["status"]))
        for field, value in (("host", "-evil"), ("user", "a@b"), ("port", 0),
                             ("identity_file", "relative"), ("known_hosts_file", ""),
                             ("executable", "relative")):
            with self.subTest(field=field):
                self.setUp_record(field, value)
                with self.assertRaises(ConfigError):
                    self.route(["status"])
        run.assert_not_called()

    def setUp_record(self, field, value):
        self.record = {"host": "operator.example", "user": "ops", "identity_file": "/tmp/key",
                       "known_hosts_file": "/tmp/known", "executable": "/opt/gate"}
        self.record[field] = value
        self.write_config()


if __name__ == "__main__":
    unittest.main()
