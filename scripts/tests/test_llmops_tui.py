#!/usr/bin/env python
"""TUI contract tests that do not require a terminal."""

from __future__ import annotations

import argparse
import unittest
import tempfile
import json
from pathlib import Path
from unittest import mock

from llmops_kit import llmops_cli
from llmops_kit.llmops_init import initialize
from llmops_kit.llmops_paths import resolve_paths
from llmops_kit.llmops_tui import build_application, equivalent_command


class TuiContractTests(unittest.TestCase):
    def test_mutation_has_equivalent_cli(self) -> None:
        self.assertEqual(
            equivalent_command("restart", "example:model"),
            "llmops component restart example:model",
        )

    def test_shared_status_preserves_authority_only_semantics(self) -> None:
        catalog = {
            "schema_version": 1,
            "trusted_control_hosts": ["control-host"],
            "hosts": [{"name": "desktop-host", "peer_observable": False}],
            "components": [
                {
                    "id": "example:desktop-tunnel",
                    "component_id": "desktop-tunnel",
                    "host": "desktop-host",
                    "driver": "ssh-tunnel",
                    "profile": "desktop-tunnel",
                    "enabled": True,
                    "tags": ["tunnel"],
                }
            ],
        }
        args = argparse.Namespace(
            selector=None,
            all=False,
            verbose=False,
            workers=8,
            host_timeout=20,
            status_host=None,
            local=False,
        )
        with (
            mock.patch.object(llmops_cli, "_load_observer_catalog", return_value=catalog),
            mock.patch.object(llmops_cli, "_current_snapshot_host", return_value="control-host"),
        ):
            payload = llmops_cli._collect_status(args)
        self.assertEqual(payload[0]["status"], "authority-only")


class TuiApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_headless_views_and_mutation_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = resolve_paths(
                {
                    "HOME": str(root),
                    "LLMOPS_CONFIG_HOME": str(root / "config"),
                    "LLMOPS_DATA_HOME": str(root / "data"),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                    "LLMOPS_CACHE_HOME": str(root / "cache"),
                }
            )
            initialize(paths, preset="single-host", user="operator")
            stack_path = paths.stacks_dir / "starter.json"
            stack = json.loads(stack_path.read_text(encoding="utf-8"))
            stack["components"][0]["enabled"] = True
            stack_path.write_text(json.dumps(stack, indent=2) + "\n", encoding="utf-8")
            original = (paths.stacks_dir / "starter.json").read_bytes()
            app = build_application(str(paths.config_home), None)
            with mock.patch.object(llmops_cli, "_collect_status", wraps=llmops_cli._collect_status) as collect:
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause(1)
                    table = app.query_one("#components")
                    self.assertEqual(table.row_count, 3)
                    await pilot.press("v")
                    await pilot.pause()
                    self.assertEqual(table.row_count, 1)
                    await pilot.press("v")
                    await pilot.pause()
                    await pilot.press("s")
                    await pilot.pause()
                    self.assertIn(
                        "llmops component start starter:chat",
                        str(app.screen.query_one("#equivalent-command").render()),
                    )
                    await pilot.click("#cancel")
                    await pilot.pause()
                collect.assert_called()
            self.assertEqual((paths.stacks_dir / "starter.json").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
