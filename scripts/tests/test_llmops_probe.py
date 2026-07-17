#!/usr/bin/env python3
"""Tests for read-only guided host probing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.lib.llmops_config import load_config
from scripts.lib.llmops_init import initialize
from scripts.lib.llmops_inventory import load_inventory
from scripts.lib.llmops_paths import resolve_paths
from scripts.lib.llmops_probe import probe_topology
from scripts.lib.llmops_topology import Topology, load_stacks


class ProbeTests(unittest.TestCase):
    def test_disabled_starter_is_probed_without_mutation(self) -> None:
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
            topology = Topology(load_stacks(paths), load_inventory(paths.inventory_file), paths, load_config(paths=paths))
            before = sorted(path.relative_to(paths.config_home) for path in paths.config_home.rglob("*"))
            result = probe_topology(topology)
            after = sorted(path.relative_to(paths.config_home) for path in paths.config_home.rglob("*"))
            self.assertTrue(result["ok"])
            self.assertEqual(before, after)
            self.assertTrue(any(item["check"] == "architecture" for item in result["checks"]))


if __name__ == "__main__":
    unittest.main()
