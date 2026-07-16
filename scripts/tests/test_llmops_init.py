#!/usr/bin/env python3
"""Tests for non-destructive LLM-Ops-Kit starter configuration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.lib.llmops_config import load_config
from scripts.lib.llmops_init import InitError, initialize
from scripts.lib.llmops_inventory import load_inventory
from scripts.lib.llmops_paths import resolve_paths
from scripts.lib.llmops_topology import Topology, load_stacks, validate_topology


class InitTests(unittest.TestCase):
    def paths(self, root: Path):
        return resolve_paths(
            {
                "HOME": str(root),
                "LLMOPS_CONFIG_HOME": str(root / "config"),
                "LLMOPS_DATA_HOME": str(root / "data"),
                "LLMOPS_STATE_HOME": str(root / "state"),
                "LLMOPS_CACHE_HOME": str(root / "cache"),
            }
        )

    def test_single_host_preset_is_valid_and_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.paths(Path(tmp))
            initialize(paths, preset="single-host", user="operator")
            topology = Topology(
                stacks=load_stacks(paths),
                hosts=load_inventory(paths.inventory_file),
                paths=paths,
                config=load_config(paths=paths),
            )
            self.assertEqual(validate_topology(topology), [])
            self.assertFalse(any(item.enabled for item in topology.all_components()))

    def test_local_lan_preset_uses_two_ssh_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.paths(Path(tmp))
            initialize(
                paths,
                preset="local-lan",
                user="operator",
                model_host="models.local",
                agent_host="agents.local",
            )
            hosts = load_inventory(paths.inventory_file)
            self.assertEqual(sorted(hosts), ["agent-host", "model-host"])
            self.assertTrue(all(host.transport == "ssh" for host in hosts.values()))

    def test_init_refuses_to_overwrite_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.paths(Path(tmp))
            initialize(paths, preset="single-host", user="operator")
            with self.assertRaisesRegex(InitError, "refusing to overwrite"):
                initialize(paths, preset="single-host", user="operator")


if __name__ == "__main__":
    unittest.main()
