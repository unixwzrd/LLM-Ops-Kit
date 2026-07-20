#!/usr/bin/env python
from __future__ import annotations

import unittest
from pathlib import Path

from llmops_kit.llmops_paths import resolve_paths


class LlmOpsPathTests(unittest.TestCase):
    def test_default_paths_are_platform_neutral(self) -> None:
        paths = resolve_paths({"HOME": "/home/example"})
        self.assertEqual(paths.config_home, Path("/home/example/.config/llm-ops"))
        self.assertEqual(paths.data_home, Path("/home/example/.local/share/llm-ops"))
        self.assertEqual(paths.state_home, Path("/home/example/.local/state/llm-ops"))
        self.assertEqual(paths.cache_home, Path("/home/example/.cache/llm-ops"))
        self.assertEqual(paths.logs_dir, Path("/home/example/.local/state/llm-ops/logs"))
        self.assertEqual(paths.services_dir, Path("/home/example/.config/llm-ops/services"))
        self.assertEqual(paths.gguf_metadata_cache_dir, Path("/home/example/.cache/llm-ops/gguf-metadata"))

    def test_xdg_paths_are_honored(self) -> None:
        paths = resolve_paths(
            {
                "HOME": "/home/example",
                "XDG_CONFIG_HOME": "/xdg/config",
                "XDG_DATA_HOME": "/xdg/data",
                "XDG_STATE_HOME": "/xdg/state",
                "XDG_CACHE_HOME": "/xdg/cache",
            }
        )
        self.assertEqual(paths.config_home, Path("/xdg/config/llm-ops"))
        self.assertEqual(paths.data_home, Path("/xdg/data/llm-ops"))
        self.assertEqual(paths.state_home, Path("/xdg/state/llm-ops"))
        self.assertEqual(paths.cache_home, Path("/xdg/cache/llm-ops"))

    def test_llmops_specific_paths_override_xdg_paths(self) -> None:
        paths = resolve_paths(
            {
                "HOME": "/home/example",
                "XDG_CONFIG_HOME": "/xdg/config",
                "XDG_DATA_HOME": "/xdg/data",
                "XDG_STATE_HOME": "/xdg/state",
                "XDG_CACHE_HOME": "/xdg/cache",
                "LLMOPS_CONFIG_HOME": "/custom/config",
                "LLMOPS_DATA_HOME": "/custom/data",
                "LLMOPS_STATE_HOME": "/custom/state",
                "LLMOPS_CACHE_HOME": "/custom/cache",
            }
        )
        self.assertEqual(paths.config_home, Path("/custom/config"))
        self.assertEqual(paths.data_home, Path("/custom/data"))
        self.assertEqual(paths.state_home, Path("/custom/state"))
        self.assertEqual(paths.cache_home, Path("/custom/cache"))


if __name__ == "__main__":
    unittest.main()
