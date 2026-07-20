#!/usr/bin/env python
"""TUI contract tests that do not require a terminal."""

from __future__ import annotations

import unittest
import tempfile
import json
from pathlib import Path

from llmops_kit.llmops_init import initialize
from llmops_kit.llmops_paths import resolve_paths
from llmops_kit.llmops_tui import build_application, equivalent_command


class TuiContractTests(unittest.TestCase):
    def test_mutation_has_equivalent_cli(self) -> None:
        self.assertEqual(
            equivalent_command("restart", "example:model"),
            "llmops component restart example:model",
        )


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
            self.assertEqual((paths.stacks_dir / "starter.json").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
