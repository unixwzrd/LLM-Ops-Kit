#!/usr/bin/env python3
"""Tests for canonical LLM-Ops-Kit component orchestration."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))

from llmops_config import load_config
from llmops_drivers import CommandResult, DriverError, _launchd_command
from llmops_executor import Executor, ExecutionError, Operation, component_plan, stack_plan
from llmops_inventory import InventoryError, load_inventory
from llmops_paths import resolve_paths
from llmops_topology import (
    Topology,
    TopologyError,
    dependency_closure,
    load_stacks,
    topological_order,
    validate_topology,
    write_host_snapshot,
)


class FakeRunner:
    """Stateful runner used to test orchestration without processes or SSH."""

    def __init__(self, running: Optional[set[str]] = None, fail_start: str = "", fail_health: str = "") -> None:
        self.running = set(running or set())
        self.fail_start = fail_start
        self.fail_health = fail_health
        self.calls: list[tuple[str, str]] = []

    def status(self, component):
        ok = component.qualified_id in self.running
        return CommandResult(component.qualified_id, "status", "fake", 0 if ok else 1, "", "")

    def run(self, component, action):
        self.calls.append((component.qualified_id, action))
        if action == "start":
            if component.qualified_id == self.fail_start:
                return CommandResult(component.qualified_id, action, "fake", 1, "", "failed")
            self.running.add(component.qualified_id)
        elif action == "stop":
            self.running.discard(component.qualified_id)
        elif action == "restart":
            self.running.add(component.qualified_id)
        return CommandResult(component.qualified_id, action, "fake", 0, "", "")

    def wait_healthy(self, component):
        if component.qualified_id == self.fail_health:
            raise DriverError("readiness timed out")
        return CommandResult(component.qualified_id, "health", "fake", 0, "", "")


class ControlFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.config_home = self.root / "config"
        self.config_home.mkdir()
        self.paths = resolve_paths(
            {
                "HOME": str(self.root),
                "LLMOPS_CONFIG_HOME": str(self.config_home),
                "LLMOPS_DATA_HOME": str(self.root / "data"),
                "LLMOPS_STATE_HOME": str(self.root / "state"),
                "LLMOPS_CACHE_HOME": str(self.root / "cache"),
            }
        )
        self.write_json(
            self.paths.config_file,
            {"schema_version": 1, "runtime": {"allow_command_driver": False}},
        )
        self.write_json(
            self.paths.inventory_file,
            {
                "schema_version": 1,
                "defaults": {
                    "user": "operator",
                    "port": 22,
                    "install_root": "~/.local/llm-ops",
                    "config_profile": "default",
                    "transport": "local",
                },
                "hosts": [
                    {"name": "model-host", "role": "llm", "host": "localhost"},
                    {"name": "agent-host", "role": "agent", "host": "localhost"},
                ],
            },
        )
        for directory in (self.paths.models_dir, self.paths.agents_dir, self.paths.services_dir):
            directory.mkdir(parents=True)
        self.write_json(
            self.paths.models_dir / "chat.json",
            {
                "schema_version": 1,
                "name": "chat",
                "type": "llm",
                "model_path": "/models/chat.gguf",
                "runtime": {"host": "127.0.0.1", "port": 11434, "threads": 4},
                "llama": {"ctx_size": 4096, "gpu_layers": "all", "batch_size": 512, "ubatch_size": 512},
            },
        )
        self.write_json(
            self.paths.models_dir / "embedding.json",
            {
                "schema_version": 1,
                "name": "embedding",
                "type": "embedding",
                "model_path": "/models/embedding.gguf",
                "runtime": {"host": "127.0.0.1", "port": 11435, "threads": 4},
                "llama": {"ctx_size": 512, "gpu_layers": "all", "batch_size": 512, "ubatch_size": 512},
                "environment": {"MODEL_PROFILE": "embedding", "MODEL_TYPE": "embedding", "MODEL": "/models/embedding.gguf", "HOST": "127.0.0.1", "PORT": 11435, "THREADS": 4, "THREADS_BATCH": 4, "CTX_SIZE": 512, "GPU_LAYERS": "all", "BATCH_SIZE": 512, "UBATCH_SIZE": 512, "POOLING": "mean"},
            },
        )
        self.write_json(
            self.paths.services_dir / "proxy.json",
            {"schema_version": 1, "runtime": {"listen_host": "127.0.0.1", "listen_port": 11434, "upstream_host": "127.0.0.1", "upstream_port": 11433}},
        )
        self.write_json(
            self.paths.agents_dir / "sample-agent.json",
            {"schema_version": 1, "actions": {action: ["/usr/bin/true"] for action in ("start", "stop", "restart", "status")}},
        )
        self.write_json(
            self.paths.stacks_dir / "sample.json",
            {
                "schema_version": 1,
                "name": "sample",
                "components": [
                    {
                        "id": "chat",
                        "host": "model-host",
                        "driver": "modelctl",
                        "profile": "chat",
                    },
                    {
                        "id": "embedding",
                        "host": "model-host",
                        "driver": "modelctl",
                        "profile": "embedding",
                    },
                    {
                        "id": "proxy",
                        "host": "agent-host",
                        "driver": "model-proxy",
                        "profile": "proxy",
                        "depends_on": ["chat"],
                    },
                    {
                        "id": "agent",
                        "host": "agent-host",
                        "driver": "agent",
                        "profile": "sample-agent",
                        "depends_on": ["proxy", "embedding"],
                    },
                ],
            },
        )
        self.topology = Topology(
            stacks=load_stacks(self.paths),
            hosts=load_inventory(self.paths.inventory_file),
            paths=self.paths,
            config=load_config(paths=self.paths),
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @staticmethod
    def write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class InventoryTests(ControlFixture):
    def test_load_inventory_supports_local_and_ssh_hosts(self) -> None:
        hosts = load_inventory(self.paths.inventory_file)
        self.assertEqual(sorted(hosts), ["agent-host", "model-host"])
        self.assertEqual(hosts["model-host"].transport, "local")

    def test_inventory_rejects_duplicate_hosts(self) -> None:
        raw = json.loads(self.paths.inventory_file.read_text(encoding="utf-8"))
        raw["hosts"].append(dict(raw["hosts"][0]))
        self.write_json(self.paths.inventory_file, raw)
        with self.assertRaisesRegex(InventoryError, "duplicate host"):
            load_inventory(self.paths.inventory_file)


class TopologyTests(ControlFixture):
    def test_stack_loads_and_validates(self) -> None:
        self.assertEqual(validate_topology(self.topology), [])
        self.assertEqual(len(self.topology.all_components()), 4)

    def test_short_component_resolution_requires_unique_id(self) -> None:
        self.assertEqual(self.topology.resolve_component("chat").qualified_id, "sample:chat")
        self.assertEqual(self.topology.resolve_component("sample:chat").profile, "chat")

    def test_topological_order_is_dependency_first(self) -> None:
        order = [item.component_id for item in topological_order(self.topology.stacks["sample"])]
        self.assertLess(order.index("chat"), order.index("proxy"))
        self.assertLess(order.index("proxy"), order.index("agent"))
        self.assertLess(order.index("embedding"), order.index("agent"))

    def test_cycle_is_rejected(self) -> None:
        stack = json.loads((self.paths.stacks_dir / "sample.json").read_text(encoding="utf-8"))
        stack["components"][0]["depends_on"] = ["agent"]
        self.write_json(self.paths.stacks_dir / "sample.json", stack)
        topology = Topology(
            stacks=load_stacks(self.paths),
            hosts=self.topology.hosts,
            paths=self.paths,
            config=self.topology.config,
        )
        self.assertTrue(any("cycle" in error for error in validate_topology(topology)))

    def test_command_driver_requires_explicit_feature_gate(self) -> None:
        stack = json.loads((self.paths.stacks_dir / "sample.json").read_text(encoding="utf-8"))
        stack["components"].append(
            {
                "id": "custom",
                "host": "agent-host",
                "driver": "command",
                "profile": "custom",
            }
        )
        self.write_json(
            self.paths.services_dir / "custom.json",
            {"schema_version": 1, "actions": {action: ["/usr/bin/true"] for action in ("start", "stop", "restart", "status")}},
        )
        self.write_json(self.paths.stacks_dir / "sample.json", stack)
        topology = Topology(
            stacks=load_stacks(self.paths),
            hosts=self.topology.hosts,
            paths=self.paths,
            config=self.topology.config,
        )
        self.assertTrue(any("allow_command_driver" in error for error in validate_topology(topology)))

    def test_profile_runtime_contract_is_validated(self) -> None:
        self.write_json(self.paths.models_dir / "chat.json", {"schema_version": 1, "name": "chat", "type": "llm"})
        errors = validate_topology(self.topology)
        self.assertTrue(any("missing required runtime value: MODEL" in error for error in errors))

    def test_nested_runtime_port_conflict_is_rejected(self) -> None:
        stack = json.loads((self.paths.stacks_dir / "sample.json").read_text(encoding="utf-8"))
        stack["components"][2]["host"] = "model-host"
        self.write_json(self.paths.stacks_dir / "sample.json", stack)
        topology = Topology(
            stacks=load_stacks(self.paths),
            hosts=self.topology.hosts,
            paths=self.paths,
            config=self.topology.config,
        )
        self.assertTrue(any("port conflict" in error for error in validate_topology(topology)))

    def test_launchd_stop_is_idempotent_when_service_is_unloaded(self) -> None:
        command = _launchd_command(
            {"label": "org.example.test"},
            self.topology.resolve_component("agent"),
            "stop",
        )
        self.assertIn("if launchctl print", command)
        self.assertIn("launchctl bootout", command)

    def test_host_snapshot_contains_only_profiles_used_on_host(self) -> None:
        destination = self.root / "snapshot"
        write_host_snapshot(self.topology, host_name="model-host", destination=destination)
        self.assertTrue((destination / "models/chat.json").is_file())
        self.assertTrue((destination / "models/embedding.json").is_file())
        self.assertFalse((destination / "services/proxy.json").exists())
        self.assertTrue((destination / "inventory.json").is_file())
        self.assertTrue((destination / "stacks/sample.json").is_file())
        local_stack = json.loads((destination / "stacks/sample.json").read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in local_stack["components"]], ["chat", "embedding"])
        resolved = json.loads((destination / "resolved.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [item["id"] for item in resolved["components"]],
            ["sample:chat", "sample:embedding"],
        )

    def test_host_snapshot_rejects_embedded_secret_values(self) -> None:
        profile = json.loads((self.paths.models_dir / "chat.json").read_text(encoding="utf-8"))
        profile["api_key"] = "plaintext"
        self.write_json(self.paths.models_dir / "chat.json", profile)
        with self.assertRaisesRegex(TopologyError, "contains secret value"):
            write_host_snapshot(
                self.topology,
                host_name="model-host",
                destination=self.root / "snapshot",
            )


class PlannerTests(ControlFixture):
    def test_component_start_includes_dependencies(self) -> None:
        agent = self.topology.resolve_component("agent")
        plan = component_plan(self.topology, agent, "start")
        actions = [(item.component.component_id, item.action) for item in plan]
        self.assertEqual(actions[-1], ("agent", "start"))
        self.assertIn(("chat", "start"), actions)
        self.assertIn(("embedding", "start"), actions)
        self.assertIn(("proxy", "start"), actions)

    def test_restart_is_target_only_by_default(self) -> None:
        chat = self.topology.resolve_component("chat")
        plan = component_plan(self.topology, chat, "restart")
        self.assertEqual([(item.component.component_id, item.action) for item in plan], [("chat", "restart")])

    def test_cascade_restart_stops_and_restarts_dependents(self) -> None:
        chat = self.topology.resolve_component("chat")
        plan = component_plan(self.topology, chat, "restart", cascade=True)
        actions = [(item.component.component_id, item.action) for item in plan]
        self.assertEqual(actions.count(("chat", "restart")), 1)
        self.assertIn(("proxy", "stop"), actions)
        self.assertIn(("proxy", "start"), actions)
        self.assertIn(("agent", "stop"), actions)
        self.assertIn(("agent", "start"), actions)

    def test_stack_stop_is_reverse_dependency_order(self) -> None:
        actions = [
            (item.component.component_id, item.action)
            for item in stack_plan(self.topology.stacks["sample"], "stop")
        ]
        self.assertLess(actions.index(("agent", "stop")), actions.index(("proxy", "stop")))
        self.assertLess(actions.index(("proxy", "stop")), actions.index(("chat", "stop")))

    def test_disabled_component_cannot_be_operated_directly(self) -> None:
        stack = json.loads((self.paths.stacks_dir / "sample.json").read_text(encoding="utf-8"))
        stack["components"][0]["enabled"] = False
        self.write_json(self.paths.stacks_dir / "sample.json", stack)
        topology = Topology(
            stacks=load_stacks(self.paths),
            hosts=self.topology.hosts,
            paths=self.paths,
            config=self.topology.config,
        )
        with self.assertRaisesRegex(TopologyError, "component is disabled"):
            component_plan(topology, topology.resolve_component("chat"), "start")


class ExecutorTests(ControlFixture):
    def test_start_is_idempotent_and_preserves_preexisting_components(self) -> None:
        runner = FakeRunner(running={"sample:chat"})
        executor = Executor(self.topology, runner=runner)
        agent = self.topology.resolve_component("agent")
        executor.execute(component_plan(self.topology, agent, "start"))
        self.assertNotIn(("sample:chat", "start"), runner.calls)
        self.assertEqual(
            runner.running,
            {"sample:chat", "sample:embedding", "sample:proxy", "sample:agent"},
        )

    def test_failed_start_rolls_back_only_components_started_by_invocation(self) -> None:
        runner = FakeRunner(running={"sample:chat"}, fail_start="sample:agent")
        executor = Executor(self.topology, runner=runner)
        agent = self.topology.resolve_component("agent")
        with self.assertRaisesRegex(Exception, "start failed"):
            executor.execute(component_plan(self.topology, agent, "start"))
        self.assertEqual(runner.running, {"sample:chat"})
        self.assertNotIn(("sample:chat", "stop"), runner.calls)

    def test_failed_readiness_rolls_back_the_started_component(self) -> None:
        runner = FakeRunner(fail_health="sample:chat")
        executor = Executor(self.topology, runner=runner)
        chat = self.topology.resolve_component("chat")
        with self.assertRaisesRegex(Exception, "readiness timed out"):
            executor.execute(component_plan(self.topology, chat, "start"))
        self.assertNotIn("sample:chat", runner.running)
        self.assertIn(("sample:chat", "stop"), runner.calls)

    def test_active_dependents_reports_only_running_components(self) -> None:
        runner = FakeRunner(running={"sample:proxy", "sample:agent"})
        executor = Executor(self.topology, runner=runner)
        chat = self.topology.resolve_component("chat")
        self.assertEqual(
            [item.qualified_id for item in executor.active_dependents(chat)],
            ["sample:proxy", "sample:agent"],
        )

    def test_leaf_component_has_no_active_dependents(self) -> None:
        runner = FakeRunner(running={"sample:chat", "sample:embedding", "sample:proxy", "sample:agent"})
        executor = Executor(self.topology, runner=runner)
        agent = self.topology.resolve_component("agent")
        self.assertEqual(executor.active_dependents(agent), [])

    def test_read_only_inspection_does_not_create_operation_lock(self) -> None:
        runner = FakeRunner(running={"sample:chat"})
        executor = Executor(self.topology, runner=runner)
        chat = self.topology.resolve_component("chat")
        results = executor.inspect([Operation(chat, "status")])
        self.assertTrue(results[0].ok)
        self.assertFalse((self.paths.run_dir / "orchestrator.lock").exists())

    def test_read_only_inspection_rejects_mutation(self) -> None:
        executor = Executor(self.topology, runner=FakeRunner())
        chat = self.topology.resolve_component("chat")
        with self.assertRaisesRegex(ExecutionError, "read-only inspection"):
            executor.inspect([Operation(chat, "start")])


if __name__ == "__main__":
    unittest.main()
