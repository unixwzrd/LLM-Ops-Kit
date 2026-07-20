#!/usr/bin/env python
"""Adapter registry and conformance tests."""

from __future__ import annotations

import unittest
from unittest import mock

from llmops_kit.llmops_adapters import AdapterManifest, discover_adapters, validate_adapters
from llmops_kit.llmops_cli import main as cli_main


class FakeEntryPoint:
    name = "fixture"
    value = "fixture:register"

    @staticmethod
    def load():
        return lambda: [
            AdapterManifest(
                "fixture",
                "1.0.0",
                drivers=("fixture-driver",),
                platforms=("darwin",),
            )
        ]


class AdapterRegistryTests(unittest.TestCase):
    def test_external_adapter_registers_without_core_changes(self) -> None:
        registry = discover_adapters(entry_points=[FakeEntryPoint()])
        self.assertIn("fixture", registry)
        self.assertEqual(registry["fixture"].drivers, ("fixture-driver",))

    def test_builtin_drivers_have_exactly_one_adapter(self) -> None:
        registry = discover_adapters(entry_points=[])
        drivers = {
            "agent",
            "command",
            "launchd",
            "model-proxy",
            "modelctl",
            "process",
            "ssh-tunnel",
            "tts-bridge",
        }
        self.assertEqual(validate_adapters(registry, drivers), [])

    def test_adapter_doctor_does_not_require_configuration(self) -> None:
        with mock.patch.dict("os.environ", {"LLMOPS_CONFIG_HOME": "/does/not/exist"}, clear=False):
            self.assertEqual(cli_main(["adapter", "doctor", "--json"]), 0)


if __name__ == "__main__":
    unittest.main()
