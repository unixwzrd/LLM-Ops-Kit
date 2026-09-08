#!/usr/bin/env python
"""Tests for canonical LLM-Ops-Kit component orchestration."""

from __future__ import annotations

import argparse
import json
import io
import os
import pwd
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from typing import Optional
from unittest import mock

from llmops_kit import __version__, entrypoint, llmops_cli
from llmops_kit.entrypoint import tui_authority_command
from llmops_kit.llmops_cli import _host_command as host_command
from llmops_kit.llmops_cli import _is_local_status_host as is_local_status_host
from llmops_kit.llmops_cli import _remote_status as remote_status
from llmops_kit.llmops_cli import _status_components as status_components
from llmops_kit.llmops_cli import _condition as condition
from llmops_kit.llmops_cli import _validate_host_operation as validate_host_operation
from llmops_kit.llmops_cli import stack_operations
from llmops_kit.llmops_config import load_config
from llmops_kit.llmops_drivers import CommandResult, ComponentObservation, ComponentRunner, DriverError, LogChannelRecord, _launchd_command, build_component_command, resolve_log_channels
from llmops_kit.llmops_executor import Executor, ExecutionError, Operation, component_plan, operation_batches, operation_lock, stack_plan
from llmops_kit.llmops_inventory import InventoryError, load_inventory
from llmops_kit.llmops_lifecycle_state import LifecycleStateStore
from llmops_kit.llmops_paths import resolve_paths
from llmops_kit.llmops_products import ProductInventory
from llmops_kit.llmops_topology import (
    Topology,
    TopologyError,
    dependency_closure,
    load_stacks,
    topological_order,
    validate_topology,
    write_host_snapshot,
)
from llmops_kit.llmops_topology_view import project_topology, render_dot, render_mermaid


class FakeRunner:
    """Stateful runner used to test orchestration without processes or SSH."""

    def __init__(
        self,
        running: Optional[set[str]] = None,
        fail_start: str = "",
        fail_stop: str = "",
        fail_health: str = "",
        stubborn_stop: str = "",
    ) -> None:
        self.running = set(running or set())
        self.fail_start = fail_start
        self.fail_stop = fail_stop
        self.fail_health = fail_health
        self.stubborn_stop = stubborn_stop
        self.calls: list[tuple[str, str]] = []

    def status(self, component):
        ok = component.qualified_id in self.running
        return CommandResult(component.qualified_id, "status", "fake", 0 if ok else 1, "", "")

    def is_running(self, component):
        return component.qualified_id in self.running

    def run(self, component, action):
        self.calls.append((component.qualified_id, action))
        if action == "start":
            if component.qualified_id == self.fail_start:
                return CommandResult(component.qualified_id, action, "fake", 1, "", "failed")
            self.running.add(component.qualified_id)
        elif action == "stop":
            if component.qualified_id == self.fail_stop:
                return CommandResult(component.qualified_id, action, "fake", 1, "", "failed")
            if component.qualified_id != self.stubborn_stop:
                self.running.discard(component.qualified_id)
        elif action == "restart":
            self.running.add(component.qualified_id)
        return CommandResult(component.qualified_id, action, "fake", 0, "", "")

    def wait_healthy(self, component):
        if component.qualified_id == self.fail_health:
            raise DriverError("readiness timed out")
        return CommandResult(component.qualified_id, "health", "fake", 0, "", "")

    def wait_stopped(self, component):
        if component.qualified_id in self.running:
            raise DriverError(
                f"{component.qualified_id}: stop command completed but component is still running"
            )
        return CommandResult(component.qualified_id, "status", "fake", 1, "", "")


class ControlFixture(unittest.TestCase):
    def setUp(self) -> None:
        user_patcher = mock.patch("llmops_kit.llmops_drivers.pwd.getpwuid")
        current_user = user_patcher.start()
        current_user.return_value.pw_name = "operator"
        self.addCleanup(user_patcher.stop)
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
            {
                "schema_version": 2,
                "runtime": {"allow_command_driver": False},
                "control": {"authority_host": "model-host"},
            },
        )
        self.write_json(
            self.paths.inventory_file,
            {
                "schema_version": 2,
                "defaults": {
                    "user": "operator",
                    "port": 22,
                    "install_root": "~/.local/llm-ops",
                    "config_profile": "default",
                    "transport": "local",
                },
                "hosts": [
                    {"name": "model-host", "role": "llm", "host": "localhost", "control_host": "model.local", "trusted_control": True},
                    {"name": "agent-host", "role": "agent", "host": "localhost", "control_host": "agent.local", "trusted_control": True},
                ],
            },
        )
        for directory in (self.paths.models_dir, self.paths.agents_dir, self.paths.services_dir):
            directory.mkdir(parents=True)
        self.write_json(
            self.paths.models_dir / "chat.json",
            {
                "schema_version": 2,
                "template_id": "llama-cpp",
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
                "schema_version": 2,
                "template_id": "llama-cpp",
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
            {"schema_version": 2, "template_id": "model-proxy", "name": "proxy", "runtime": {"listen_host": "127.0.0.1", "listen_port": 11434, "upstream_host": "127.0.0.1", "upstream_port": 11433}},
        )
        self.write_json(
            self.paths.agents_dir / "sample-agent.json",
            {"schema_version": 2, "template_id": "generic-agent", "name": "sample-agent", "actions": {action: ["/usr/bin/true"] for action in ("start", "stop", "restart", "status")}, "environment": {}, "log_path": "~/.hermes/logs/gateway.log"},
        )
        self.write_json(
            self.paths.stacks_dir / "sample.json",
            {
                "schema_version": 2,
                "name": "sample",
                "components": [
                    {
                        "id": "chat",
                        "host": "model-host",
                        "driver": "modelctl",
                        "template_id": "llama-cpp",
                        "profile": "chat",
                        "tags": ["model", "chat"],
                    },
                    {
                        "id": "embedding",
                        "host": "model-host",
                        "driver": "modelctl",
                        "template_id": "llama-cpp",
                        "profile": "embedding",
                    },
                    {
                        "id": "proxy",
                        "host": "agent-host",
                        "driver": "model-proxy",
                        "template_id": "model-proxy",
                        "profile": "proxy",
                        "depends_on": ["chat"],
                    },
                    {
                        "id": "agent",
                        "host": "agent-host",
                        "driver": "agent",
                        "template_id": "generic-agent",
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
    def test_host_snapshot_filters_product_bindings_by_role(self) -> None:
        self.write_json(
            self.paths.products_file,
            {
                "schema_version": 1,
                "products": {
                    "llama-cpp": {"installed_version": "b1057", "update_state": "review"},
                    "llm-ops-kit": {
                        "installed_version": __version__,
                        "latest_version": __version__,
                        "update_state": "current",
                        "auto_update": True,
                        "release_repository": "example/llm-ops-kit",
                    },
                    "agent": {
                        "installed_version": "1.0",
                        "update_state": "current",
                    },
                },
                "components": {
                    "sample:chat": "llama-cpp",
                    "sample:agent": "agent",
                },
                "history": [
                    {
                        "product_id": "llama-cpp",
                        "installed_version": "b1000",
                        "recorded_at": "2026-07-20",
                    },
                    {
                        "product_id": "llama-cpp",
                        "installed_version": "b1057",
                        "recorded_at": "2026-07-27",
                    }
                ],
            },
        )
        self.topology.hosts["model-host"] = replace(
            self.topology.hosts["model-host"], trusted_control=False
        )
        self.topology.config.data["control"]["authority_host"] = "agent-host"
        destination = self.root / "snapshot"
        write_host_snapshot(
            self.topology, host_name="model-host", destination=destination
        )
        products = json.loads(
            (destination / "products.json").read_text(encoding="utf-8")
        )
        self.assertEqual(products["components"], {"sample:chat": "llama-cpp"})
        self.assertEqual(set(products["products"]), {"llama-cpp", "llm-ops-kit"})
        self.assertTrue(products["products"]["llm-ops-kit"]["auto_update"])
        self.assertEqual(products["history"], [])

    def test_trusted_snapshot_preserves_product_history(self) -> None:
        self.write_json(
            self.paths.products_file,
            {
                "schema_version": 1,
                "products": {
                    "llama-cpp": {
                        "installed_version": "b1057",
                        "update_state": "review",
                    },
                    "agent": {"installed_version": "1.0", "update_state": "current"},
                },
                "components": {
                    "sample:chat": "llama-cpp",
                    "sample:agent": "agent",
                },
                "history": [
                    {
                        "product_id": "llama-cpp",
                        "installed_version": "b1057",
                        "recorded_at": "2026-07-27",
                        "previous_version": "b1000",
                        "rollback": "previous binary",
                    }
                ],
            },
        )
        destination = self.root / "trusted-snapshot"
        write_host_snapshot(
            self.topology, host_name="model-host", destination=destination
        )
        products = json.loads(
            (destination / "products.json").read_text(encoding="utf-8")
        )
        self.assertEqual(set(products["products"]), {"agent", "llama-cpp"})
        self.assertEqual(products["history"][0]["previous_version"], "b1000")
        inventory = ProductInventory.load(destination / "products.json")
        self.assertEqual(inventory.history[0].rollback, "previous binary")

    def test_product_history_command_filters_product(self) -> None:
        self.write_json(
            self.paths.products_file,
            {
                "schema_version": 1,
                "products": {
                    "llama-cpp": {
                        "installed_version": "b1057",
                        "update_state": "review",
                    },
                    "agent": {"installed_version": "1.0", "update_state": "current"},
                },
                "components": {"sample:chat": "llama-cpp"},
                "history": [
                    {
                        "product_id": "llama-cpp",
                        "installed_version": "b1000",
                        "recorded_at": "2026-07-20",
                    },
                    {
                        "product_id": "llama-cpp",
                        "installed_version": "b1057",
                        "recorded_at": "2026-07-27",
                    },
                    {
                        "product_id": "agent",
                        "installed_version": "1.0",
                        "recorded_at": "2026-07-26",
                    },
                ],
            },
        )
        args = argparse.Namespace(
            product_action="history", product_id="llama-cpp", json=True
        )
        output = io.StringIO()
        with (
            mock.patch.object(
                llmops_cli, "CURRENT_TOPOLOGY", self.topology, create=True
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(llmops_cli.cmd_product(args), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(
            [item["installed_version"] for item in payload], ["b1000", "b1057"]
        )

        args = argparse.Namespace(
            product_action="history",
            product_id=None,
            json=False,
            newest=True,
            tsv=True,
        )
        output = io.StringIO()
        with (
            mock.patch.object(
                llmops_cli, "CURRENT_TOPOLOGY", self.topology, create=True
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(llmops_cli.cmd_product(args), 0)
        lines = output.getvalue().splitlines()
        self.assertEqual(
            lines[0].split("\t"),
            [
                "product_id",
                "installed_version",
                "recorded_at",
                "previous_version",
                "stack",
                "host",
                "execution_user",
                "operation_id",
                "artifact_identity",
                "validation",
                "rollback",
            ],
        )
        self.assertEqual(len(lines), 3)
        self.assertIn("agent\t1.0\t2026-07-26", lines[1])
        self.assertIn("llama-cpp\tb1057\t2026-07-27", lines[2])
        self.assertNotIn("product_id=", output.getvalue())

        args = argparse.Namespace(
            product_action="history",
            product_id="llama-cpp",
            json=False,
            newest=False,
            tsv=False,
        )
        output = io.StringIO()
        with (
            mock.patch.object(
                llmops_cli, "CURRENT_TOPOLOGY", self.topology, create=True
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(llmops_cli.cmd_product(args), 0)
        rendered = output.getvalue()
        self.assertIn("Product", rendered)
        self.assertIn("Instal", rendered)
        self.assertIn("version", rendered)
        self.assertIn("b1057", rendered)
        self.assertNotIn("product_id=", rendered)

    def test_public_entrypoint_reports_installed_version(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(entrypoint.main(["--version"]), 0)
        self.assertEqual(output.getvalue().strip(), __version__)

    def test_auto_update_target_requires_manifest_approval(self) -> None:
        target_version = f"{__version__}.next"
        release_repository = "example/llm-ops-kit"
        products = self.config_home / "products.json"
        self.write_json(
            products,
            {
                "schema_version": 1,
                "products": {
                    "llm-ops-kit": {
                        "latest_version": target_version,
                        "auto_update": True,
                        "release_repository": release_repository,
                    }
                },
            },
        )
        self.assertEqual(
            entrypoint._auto_update_target(self.config_home),
            (target_version, release_repository),
        )
        document = json.loads(products.read_text(encoding="utf-8"))
        document["products"]["llm-ops-kit"]["auto_update"] = False
        self.write_json(products, document)
        self.assertEqual(entrypoint._auto_update_target(self.config_home), ("", ""))
        document["products"]["llm-ops-kit"]["auto_update"] = True
        del document["products"]["llm-ops-kit"]["release_repository"]
        self.write_json(products, document)
        self.assertEqual(entrypoint._auto_update_target(self.config_home), ("", ""))

    def test_auto_update_applies_manifest_target_and_returns_new_entrypoint(self) -> None:
        target_version = f"{__version__}.next"
        release_repository = "example/llm-ops-kit"
        self.write_json(
            self.config_home / "products.json",
            {
                "schema_version": 1,
                "products": {
                    "llm-ops-kit": {
                        "latest_version": target_version,
                        "auto_update": True,
                        "release_repository": release_repository,
                    }
                },
            },
        )
        install_base = self.root / "install"
        updated = install_base / "current" / "app" / "bin" / "llmops"
        updated.parent.mkdir(parents=True)
        updated.write_text("#!/bin/sh\n", encoding="utf-8")
        with (
            mock.patch.object(
                entrypoint.llmops_update, "current_version", return_value=__version__
            ),
            mock.patch.object(
                entrypoint.llmops_update, "main", return_value=0
            ) as apply_update,
            mock.patch.dict(
                os.environ,
                {
                    "LLMOPS_PUBLIC_BIN_DIR": str(self.root / "bin"),
                    "LLMOPS_STATE_HOME": str(self.root / "state"),
                },
                clear=False,
            ),
        ):
            selected = entrypoint._auto_update(
                install_base, self.config_home, ["status"]
            )
        self.assertEqual(selected, updated)
        arguments = apply_update.call_args.args[0]
        self.assertIn("--apply", arguments)
        self.assertEqual(arguments[arguments.index("--version") + 1], target_version)
        self.assertNotIn("LLMOPS_AUTO_UPDATE_ACTIVE", os.environ)

    def test_auto_update_skips_explicit_update_and_rollback_commands(self) -> None:
        with mock.patch.object(entrypoint, "_auto_update_target") as target:
            self.assertIsNone(
                entrypoint._auto_update(
                    self.root / "install", self.config_home, ["update", "--check"]
                )
            )
            self.assertIsNone(
                entrypoint._auto_update(
                    self.root / "install", self.config_home, ["rollback"]
                )
            )
        target.assert_not_called()

    def test_auto_update_failure_is_nonfatal_and_redacted(self) -> None:
        target_version = f"{__version__}.next"
        self.write_json(
            self.config_home / "products.json",
            {
                "schema_version": 1,
                "products": {
                    "llm-ops-kit": {
                        "latest_version": target_version,
                        "auto_update": True,
                        "release_repository": "example/llm-ops-kit",
                    }
                },
            },
        )
        error = io.StringIO()
        with (
            mock.patch.object(
                entrypoint.llmops_update, "current_version", return_value=__version__
            ),
            mock.patch.object(entrypoint.llmops_update, "main", return_value=2),
            redirect_stderr(error),
        ):
            self.assertIsNone(
                entrypoint._auto_update(
                    self.root / "install", self.config_home, ["status"]
                )
            )
        self.assertIn(f"automatic update to {target_version} failed", error.getvalue())
        self.assertNotIn("products.json", error.getvalue())

    def test_tui_routes_from_trusted_peer_to_authority(self) -> None:
        catalog = {
            "schema_version": 1,
            "authority_host": "model-host",
            "trusted_control_hosts": ["agent-host", "model-host"],
            "hosts": [
                {
                    "name": "model-host",
                    "host": "model.local",
                    "user": "operator",
                    "port": 22,
                    "public_bin_dir": "~/.local/bin",
                }
            ],
            "components": [],
        }
        self.write_json(self.paths.config_home / "catalog.json", catalog)
        self.write_json(
            self.paths.config_home / "resolved.json",
            {"schema_version": 1, "host": "agent-host", "files": []},
        )
        command = tui_authority_command(self.paths.config_home, [])
        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command[:3], ["ssh", "-q", "-t"])
        self.assertIn("operator@model.local", command)
        self.assertIn("LLMOPS_TUI_AUTHORITY_ROUTED=1", command[-1])
        self.assertIn("llmops tui", command[-1])

    def test_load_inventory_supports_local_and_ssh_hosts(self) -> None:
        hosts = load_inventory(self.paths.inventory_file)
        self.assertEqual(sorted(hosts), ["agent-host", "model-host"])
        self.assertEqual(hosts["model-host"].transport, "local")
        self.assertEqual(hosts["model-host"].control_host, "model.local")
        self.assertEqual(hosts["model-host"].destination, "operator@model.local")

    @mock.patch("llmops_kit.llmops_drivers.os.geteuid", return_value=501)
    @mock.patch("llmops_kit.llmops_drivers.pwd.getpwuid")
    def test_local_transport_uses_ssh_for_different_execution_user(self, getpwuid, _geteuid) -> None:
        getpwuid.return_value.pw_name = "controller"
        component = self.topology.resolve_component("sample:chat")

        host = ComponentRunner(self.topology)._host(component)

        self.assertEqual(host.user, "operator")
        self.assertEqual(host.transport, "ssh")
        self.assertEqual(host.control_host, "model.local")

    def test_inventory_rejects_duplicate_hosts(self) -> None:
        raw = json.loads(self.paths.inventory_file.read_text(encoding="utf-8"))
        raw["hosts"].append(dict(raw["hosts"][0]))
        self.write_json(self.paths.inventory_file, raw)
        with self.assertRaisesRegex(InventoryError, "duplicate host"):
            load_inventory(self.paths.inventory_file)

    def test_inventory_rejects_non_boolean_trusted_control(self) -> None:
        raw = json.loads(self.paths.inventory_file.read_text(encoding="utf-8"))
        raw["hosts"][0]["trusted_control"] = "yes"
        self.write_json(self.paths.inventory_file, raw)
        with self.assertRaisesRegex(InventoryError, "trusted_control must be a boolean"):
            load_inventory(self.paths.inventory_file)

    def test_inventory_rejects_non_boolean_peer_observable(self) -> None:
        raw = json.loads(self.paths.inventory_file.read_text(encoding="utf-8"))
        raw["hosts"][0]["peer_observable"] = "no"
        self.write_json(self.paths.inventory_file, raw)
        with self.assertRaisesRegex(InventoryError, "peer_observable must be a boolean"):
            load_inventory(self.paths.inventory_file)


class TopologyTests(ControlFixture):
    def test_stack_loads_and_validates(self) -> None:
        self.assertEqual(validate_topology(self.topology), [])
        self.assertEqual(len(self.topology.all_components()), 4)

    def test_short_component_resolution_requires_unique_id(self) -> None:
        self.assertEqual(self.topology.resolve_component("chat").qualified_id, "sample:chat")
        self.assertEqual(self.topology.resolve_component("sample:chat").profile, "chat")

    def test_catalog_short_component_routes_to_owning_host(self) -> None:
        catalog = {
            "schema_version": 1,
            "trusted_control_hosts": ["model-host"],
            "hosts": [
                {
                    "name": "agent-host",
                    "host": "agent.local",
                    "user": "operator",
                    "port": 22,
                    "public_bin_dir": "~/.local/bin",
                }
            ],
            "components": [
                {
                    "id": "sample:proxy",
                    "component_id": "proxy",
                    "host": "agent-host",
                }
            ],
        }
        args = type(
            "Args",
            (),
            {
                "component": "proxy",
                "component_command": "restart",
                "json": True,
                "cascade": False,
                "no_deps": False,
                "force": False,
            },
        )()
        with (
            mock.patch.object(llmops_cli, "_load_observer_catalog", return_value=catalog),
            mock.patch.object(llmops_cli, "_current_snapshot_host", return_value="model-host"),
            mock.patch.object(llmops_cli, "_execute_host_operation", return_value=0) as execute,
        ):
            self.assertEqual(llmops_cli.cmd_remote_component(args), 0)
        host_name, command = execute.call_args.args
        self.assertEqual(host_name, "agent-host")
        self.assertIn("operator@agent.local", command)
        self.assertIn("component restart sample:proxy --json", command[-1])

    def test_schema_mutation_routes_to_designated_authority(self) -> None:
        catalog = {
            "schema_version": 1,
            "authority_host": "model-host",
            "trusted_control_hosts": ["agent-host", "model-host"],
            "hosts": [
                {
                    "name": "model-host",
                    "host": "model.local",
                    "user": "operator",
                    "port": 22,
                    "public_bin_dir": "~/.local/bin",
                }
            ],
            "components": [],
        }
        args = type(
            "Args",
            (),
            {
                "command": "component",
                "component_command": "configure",
                "json": False,
            },
        )()
        with (
            mock.patch.object(llmops_cli, "_load_observer_catalog", return_value=catalog),
            mock.patch.object(llmops_cli, "_current_snapshot_host", return_value="agent-host"),
            mock.patch.object(llmops_cli, "_execute_host_operation", return_value=0) as execute,
        ):
            result = llmops_cli._route_authority_operation(
                args,
                ["component", "configure", "sample:chat", "--plan"],
                config_home=self.paths.config_home,
            )
        self.assertEqual(result, 0)
        host_name, command = execute.call_args.args
        self.assertEqual(host_name, "model-host")
        self.assertIn("operator@model.local", command)
        self.assertIn("component configure sample:chat --plan", command[-1])

    def test_component_tags_are_loaded(self) -> None:
        self.assertEqual(self.topology.resolve_component("chat").tags, ("model", "chat"))

    def test_effective_component_reports_profile_host_and_resolved_values(self) -> None:
        llmops_cli.CURRENT_TOPOLOGY = self.topology
        payload = llmops_cli._effective_component(self.topology.resolve_component("chat"))
        self.assertEqual(payload["component"], "sample:chat")
        self.assertEqual(payload["execution_user"], "operator")
        self.assertEqual(payload["resolved"]["MODEL"], "/models/chat.gguf")
        self.assertTrue(payload["profile_path"].endswith("models/chat.json"))

    def test_reconcile_uses_mutable_authority_not_active_snapshot(self) -> None:
        authority = mock.Mock()
        authority.hosts = {"model-host": self.topology.hosts["model-host"]}
        args = type(
            "Args",
            (),
            {"host": ["model-host"], "all_hosts": False, "apply": False, "yes": False, "json": True},
        )()
        output = io.StringIO()
        with (
            mock.patch("llmops_kit.llmops_cli.desired_topology", return_value=authority),
            mock.patch("llmops_kit.llmops_cli.reconcile_plan", return_value=([], {})) as plan,
            redirect_stdout(output),
        ):
            self.assertEqual(llmops_cli.cmd_config_reconcile(args), 0)
        plan.assert_called_once_with(authority, ["model-host"])

    def test_profile_creation_plans_against_mutable_authority(self) -> None:
        llmops_cli.CURRENT_TOPOLOGY = self.topology
        args = argparse.Namespace(
            profile_action="create",
            profile="worker",
            template="standalone",
            values=None,
            expected_hash=None,
            plan=True,
            apply=False,
            yes=False,
            json=True,
        )
        output = io.StringIO()
        with (
            mock.patch.object(
                llmops_cli,
                "resolve_authority_config_home",
                return_value=self.paths.config_home,
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(llmops_cli.cmd_profile(args), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(
            Path(payload["path"]).parent,
            self.paths.services_dir,
        )

    def test_model_proxy_log_channels_resolve_on_component_host(self) -> None:
        component = self.topology.resolve_component("proxy")
        command = build_component_command(
            self.topology,
            component,
            "logs",
            log_channel="rendered-prompt",
        )
        self.assertIn(str(self.paths.logs_dir / "model-proxy.rendered.log"), command)

    def test_log_channels_are_template_driven_and_host_qualified(self) -> None:
        component = self.topology.resolve_component("proxy")
        records = resolve_log_channels(self.topology, component)
        self.assertEqual(
            [record.channel for record in records],
            ["raw-request", "raw-response", "rendered-prompt", "service"],
        )
        rendered = next(record for record in records if record.channel == "rendered-prompt")
        self.assertEqual(rendered.host, "agent-host")
        self.assertEqual(rendered.execution_user, "operator")
        self.assertEqual(
            rendered.path,
            str(self.paths.logs_dir / "model-proxy.rendered.log"),
        )

    def test_log_channel_inspection_reports_file_metadata_and_missing_files(self) -> None:
        component = replace(
            self.topology.resolve_component("proxy"),
            execution_user=pwd.getpwuid(os.geteuid()).pw_name,
        )
        path = self.paths.logs_dir / "model-proxy.rendered.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("first\nsecond\n", encoding="utf-8")
        records = ComponentRunner(self.topology).list_logs(component)
        rendered = next(record for record in records if record.channel == "rendered-prompt")
        raw_request = next(record for record in records if record.channel == "raw-request")
        self.assertTrue(rendered.available)
        self.assertTrue(rendered.readable)
        self.assertEqual(rendered.size, path.stat().st_size)
        self.assertIsNotNone(rendered.modified_at)
        self.assertFalse(raw_request.available)

    def test_templates_without_logs_return_an_empty_channel_catalog(self) -> None:
        component = replace(
            self.topology.resolve_component("agent"),
            template_id="external-http",
        )
        self.assertEqual(resolve_log_channels(self.topology, component), ())

    def test_log_reads_are_bounded(self) -> None:
        component = self.topology.resolve_component("agent")
        with self.assertRaisesRegex(DriverError, "between 1 and 10000"):
            build_component_command(self.topology, component, "logs", log_lines=10_001)

    def test_component_log_parser_supports_list_read_and_follow_modes(self) -> None:
        parser = llmops_cli.build_parser()
        listed = parser.parse_args(["component", "logs", "agent", "--list"])
        followed = parser.parse_args(
            ["component", "logs", "agent", "--channel", "stdout", "--lines", "500", "--follow"]
        )
        self.assertTrue(listed.list_channels)
        self.assertFalse(listed.follow)
        self.assertEqual(followed.channel, "stdout")
        self.assertEqual(followed.lines, 500)
        self.assertTrue(followed.follow)
        with self.assertRaises(SystemExit):
            parser.parse_args(["component", "logs", "agent", "--list", "--follow"])

    def test_component_log_list_json_uses_shared_records(self) -> None:
        llmops_cli.CURRENT_TOPOLOGY = self.topology
        record = LogChannelRecord(
            component="sample:agent",
            channel="service",
            host="agent-host",
            execution_user="operator",
            path="~/.hermes/logs/gateway.log",
            available=True,
            readable=True,
            size=42,
            modified_at=123,
        )
        args = argparse.Namespace(
            component="agent",
            action="logs",
            list_channels=True,
            follow=False,
            channel="service",
            lines=200,
            json=True,
        )
        output = io.StringIO()
        with (
            mock.patch.object(ComponentRunner, "list_logs", return_value=(record,)),
            redirect_stdout(output),
        ):
            self.assertEqual(llmops_cli.cmd_component_status(args), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload[0]["path"], "~/.hermes/logs/gateway.log")
        self.assertEqual(payload[0]["execution_user"], "operator")

    def test_follow_reaps_transport_on_keyboard_interrupt(self) -> None:
        component = replace(
            self.topology.resolve_component("agent"),
            execution_user=pwd.getpwuid(os.geteuid()).pw_name,
        )
        process = mock.Mock(pid=4321)
        process.wait.side_effect = [KeyboardInterrupt, 0]
        with (
            mock.patch("llmops_kit.llmops_drivers.subprocess.Popen", return_value=process),
            mock.patch("llmops_kit.llmops_drivers.os.killpg") as kill_group,
        ):
            self.assertEqual(
                ComponentRunner(self.topology).follow_logs(component, lines=10),
                130,
            )
        kill_group.assert_called_once()

    def test_log_path_expands_execution_user_home(self) -> None:
        component = self.topology.resolve_component("agent")
        command = build_component_command(self.topology, component, "logs")
        self.assertEqual(command, 'tail -n 200 "$HOME"/.hermes/logs/gateway.log')

    def test_modelctl_tts_log_resolves_to_tts_server_log(self) -> None:
        component = self.topology.resolve_component("embedding")
        component = replace(component, profile="QwenTTS")
        self.write_json(
            self.paths.models_dir / "QwenTTS.json",
            {
                "schema_version": 2,
                "template_id": "modelctl",
                "name": "QwenTTS",
                "type": "tts",
                "environment": {"MODEL_TYPE": "tts"},
            },
        )
        command = build_component_command(self.topology, component, "logs")
        self.assertIn(str(self.paths.logs_dir / "tts-server-QwenTTS.log"), command)

    @mock.patch("llmops_kit.llmops_drivers.ComponentRunner.probe_health")
    @mock.patch("llmops_kit.llmops_drivers.ComponentRunner.status")
    def test_running_typed_driver_status_failure_is_degraded(
        self,
        status: mock.Mock,
        probe_health: mock.Mock,
    ) -> None:
        component = self.topology.resolve_component("proxy")
        status.return_value = CommandResult(
            component.qualified_id,
            "status",
            "model-proxy status",
            1,
            "model-proxy: running pid=123\nupstream_health=down",
            "",
        )
        probe_health.return_value = CommandResult(
            component.qualified_id,
            "health",
            "curl listener",
            0,
            "",
            "",
        )
        observation = ComponentRunner(self.topology).inspect(component)
        self.assertEqual(observation.lifecycle, "running")
        self.assertEqual(observation.health, "degraded")

    def test_observed_runtime_uses_live_process_command(self) -> None:
        component = self.topology.resolve_component("proxy")
        lifecycle = CommandResult(component.qualified_id, "status", "status", 0, "model-proxy: running pid=42", "")
        runtime = CommandResult(
            component.qualified_id,
            "runtime",
            "ps",
            0,
            "/opt/llm-ops/releases/0.9.0b6/scripts/model_proxy_tap.py",
            "",
        )
        observation = ComponentObservation("running", "healthy", "observed", lifecycle, lifecycle, runtime)
        self.assertEqual(llmops_cli._observed_runtime(observation), "0.9.0b6")

    def test_runtime_command_reads_elapsed_time_for_supported_pid_formats(self) -> None:
        component = self.topology.resolve_component("proxy")
        runner = ComponentRunner(self.topology)
        completed = subprocess.CompletedProcess([], 0, "01:02 command\n", "")
        for output in ("model-proxy: running pid=42", "pid = 42", "Main PID: 42 (service)"):
            with self.subTest(output=output), mock.patch(
                "llmops_kit.llmops_drivers.subprocess.run", return_value=completed
            ) as run:
                result = runner.runtime_command(
                    component,
                    CommandResult(component.qualified_id, "status", "status", 0, output, ""),
                )
                self.assertIsNotNone(result)
                self.assertEqual(result.stdout, "01:02 command")
                self.assertIn("ps -p 42 -o etime= -o command=", run.call_args.args[0][-1])

    def test_model_start_runtime_precedes_current_wrapper_runtime(self) -> None:
        component = self.topology.resolve_component("chat")
        lifecycle = CommandResult(
            component.qualified_id,
            "status",
            "modelctl status",
            0,
            (
                "started_runtime_root=/opt/llm-ops/releases/0.9.0b9\n"
                "RUNTIME_ROOT=/opt/llm-ops/releases/0.9.0b10"
            ),
            "",
        )
        observation = ComponentObservation("running", "healthy", "observed", lifecycle)
        self.assertEqual(llmops_cli._observed_runtime(observation), "0.9.0b9")

    def test_elapsed_seconds_and_uptime_format(self) -> None:
        self.assertEqual(llmops_cli._elapsed_seconds("42:03"), 2523)
        self.assertEqual(llmops_cli._elapsed_seconds("02:03:04"), 7384)
        self.assertEqual(llmops_cli._elapsed_seconds("3-02:03:04"), 266584)
        self.assertIsNone(llmops_cli._elapsed_seconds("not-an-etime"))
        self.assertEqual(llmops_cli._format_uptime(266584, "running"), "3d 02h")
        self.assertEqual(llmops_cli._format_uptime(3723, "running"), "1h 02m")
        self.assertEqual(llmops_cli._format_uptime(None, "stopped"), "-")

    def test_degraded_component_retains_process_uptime(self) -> None:
        component = self.topology.resolve_component("proxy")
        lifecycle = CommandResult(
            component.qualified_id,
            "status",
            "status",
            1,
            "model-proxy: running pid=42\nhealth=down",
            "",
        )
        runtime = CommandResult(
            component.qualified_id,
            "runtime",
            "ps",
            0,
            "1-02:03:04 /opt/llm-ops/current/scripts/model_proxy_tap.py",
            "",
        )
        observation = ComponentObservation(
            "running", "degraded", "observed", lifecycle, lifecycle, runtime
        )
        seconds, started_at, source = llmops_cli._uptime_fields(observation, "running")
        self.assertEqual(seconds, 93784)
        self.assertRegex(started_at, r"Z$")
        self.assertEqual(source, "process")

    def test_component_tags_must_be_nonempty_strings(self) -> None:
        stack = json.loads((self.paths.stacks_dir / "sample.json").read_text(encoding="utf-8"))
        stack["components"][0]["tags"] = [""]
        self.write_json(self.paths.stacks_dir / "sample.json", stack)
        with self.assertRaisesRegex(TopologyError, "tags must be nonempty strings"):
            load_stacks(self.paths)

    def test_status_selector_matches_profile_stack_driver_and_tag(self) -> None:
        status_components.__globals__["CURRENT_TOPOLOGY"] = self.topology
        self.assertEqual([item.component_id for item in status_components("chat", include_disabled=False)], ["chat"])
        self.assertEqual([item.component_id for item in status_components("model", include_disabled=False)], ["chat"])
        self.assertEqual(len(status_components("sample", include_disabled=False)), 4)
        self.assertEqual(len(status_components("modelctl", include_disabled=False)), 2)

    def test_condition_preserves_lifecycle_health_and_observability(self) -> None:
        common = {"desired_lifecycle": "running"}
        self.assertEqual(condition(lifecycle="running", health="healthy", observability="observed", drift="none", **common), "ok")
        self.assertEqual(condition(lifecycle="running", health="degraded", observability="observed", drift="none", **common), "attention")
        self.assertEqual(condition(lifecycle="stopped", health="not-applicable", observability="observed", drift="none", **common), "error")
        self.assertEqual(condition(lifecycle="stopped", desired_lifecycle="stopped", health="not-applicable", observability="observed", drift="none"), "down")
        self.assertEqual(condition(lifecycle="unknown", health="unknown", observability="authority-only", drift="unknown", **common), "unobserved")
        self.assertEqual(condition(lifecycle="unknown", health="unknown", observability="unreachable", drift="unknown", **common), "error")

    def test_proxy_lifecycle_remains_running_when_health_status_fails(self) -> None:
        proxy = self.topology.resolve_component("proxy")
        result = CommandResult(
            proxy.qualified_id,
            "status",
            "model-proxy status",
            1,
            "model-proxy: running pid=123\nhealth=down",
            "",
        )
        self.assertEqual(ComponentRunner.lifecycle_from_result(proxy, result), "running")

    def test_process_status_with_empty_pid_is_stopped(self) -> None:
        component = replace(self.topology.resolve_component("agent"), driver="process")
        result = CommandResult(
            component.qualified_id,
            "status",
            "status",
            0,
            "hermes-dashboard: running pid=",
            "cat: dashboard.pid: No such file or directory",
        )
        self.assertEqual(ComponentRunner.lifecycle_from_result(component, result), "stopped")

    @mock.patch("llmops_kit.llmops_drivers.subprocess.run")
    def test_component_action_timeout_returns_bounded_failure(self, run: mock.Mock) -> None:
        component = self.topology.resolve_component("chat")
        run.side_effect = subprocess.TimeoutExpired(["modelctl", "chat", "start"], 900)
        result = ComponentRunner(self.topology).run(component, "start")
        self.assertEqual(result.returncode, 124)
        self.assertIn("start timed out after 900 seconds", result.stderr)
        self.assertEqual(run.call_args.kwargs["timeout"], 900)

    def test_readiness_fails_immediately_when_component_exits(self) -> None:
        component = self.topology.resolve_component("chat")
        runner = ComponentRunner(self.topology)
        runner.probe_health = mock.Mock(
            return_value=CommandResult(component.qualified_id, "health", "curl", 7, "", "refused")
        )
        runner.status = mock.Mock(
            return_value=CommandResult(component.qualified_id, "status", "modelctl status", 1, "", "")
        )
        with self.assertRaisesRegex(DriverError, "exited before readiness"):
            runner.wait_healthy(component)
        runner.probe_health.assert_called_once_with(component)
        runner.status.assert_called_once_with(component)

    def test_status_record_has_no_legacy_status_alias(self) -> None:
        self.write_json(
            self.paths.products_file,
            {
                "schema_version": 1,
                "products": {
                    "model-proxy": {
                        "installed_version": "2.3.1",
                        "latest_version": "2.4.0",
                        "update_state": "available",
                        "last_verified": "2026-07-27",
                        "version_strategy": "observed-runtime",
                    }
                },
                "components": {"sample:proxy": "model-proxy"},
            },
        )
        proxy = self.topology.resolve_component("proxy")
        result = CommandResult(
            proxy.qualified_id,
            "status",
            "/tmp/releases/0.9.0b4/bin/model-proxy status",
            1,
            "model-proxy: running pid=123\nhealth=down",
            "",
        )
        observation = ComponentObservation("running", "degraded", "observed", result, result)
        args = type(
            "Args",
            (),
            {
                "selector": "proxy",
                "all": True,
                "verbose": False,
                "workers": 1,
                "status_host": None,
                "local": True,
            },
        )()
        llmops_cli.CURRENT_TOPOLOGY = self.topology
        with mock.patch("llmops_kit.llmops_cli.ComponentRunner.inspect", return_value=observation):
            payload = llmops_cli._collect_status(args)
        self.assertNotIn("status", payload[0])
        self.assertEqual(payload[0]["lifecycle"], "running")
        self.assertEqual(payload[0]["health"], "degraded")
        self.assertEqual(payload[0]["uptime"], "unknown")
        self.assertIsNone(payload[0]["uptime_seconds"])
        self.assertEqual(payload[0]["condition"], "attention")
        self.assertEqual(payload[0]["execution_user"], "operator")
        self.assertEqual(payload[0]["component_version"], "0.9.0b4")
        self.assertEqual(payload[0]["version_strategy"], "observed-runtime")
        self.assertEqual(payload[0]["latest_version"], "2.4.0")
        self.assertEqual(payload[0]["update_state"], "available")
        self.assertEqual(payload[0]["observed_runtime"], "0.9.0b4")

        output = io.StringIO()
        with redirect_stdout(output):
            llmops_cli._human_status(payload)
        self.assertIn("RUN AS", output.getvalue().splitlines()[0])

    def test_topology_projection_is_bounded_to_immediate_relationships(self) -> None:
        projection = project_topology(self.topology, component="proxy")
        self.assertEqual(
            {item["id"] for item in projection["components"]},
            {"sample:chat", "sample:proxy", "sample:agent"},
        )
        self.assertIn("flowchart LR", render_mermaid(projection))
        self.assertIn('"sample:chat" -> "sample:proxy"', render_dot(projection))

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
                "template_id": "standalone",
                "profile": "custom",
            }
        )
        self.write_json(
            self.paths.services_dir / "custom.json",
            {"schema_version": 2, "template_id": "standalone", "name": "custom", "actions": {action: ["/usr/bin/true"] for action in ("start", "stop", "restart", "status")}, "environment": {}},
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
        self.write_json(
            self.paths.models_dir / "chat.json",
            {"schema_version": 2, "template_id": "llama-cpp", "name": "chat", "type": "llm"},
        )
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

    def test_launchd_start_and_restart_bootstrap_an_unloaded_managed_job(self) -> None:
        component = self.topology.resolve_component("agent")
        profile = {
            "label": "org.example.test",
            "plist": "~/Library/LaunchAgents/org.example.test.plist",
        }
        for action in ("start", "restart"):
            command = _launchd_command(profile, component, action)
            self.assertIn("if launchctl print gui/$(id -u)", command)
            self.assertIn("elif launchctl print user/$(id -u)", command)
            self.assertIn("launchctl bootstrap gui/$(id -u)", command)
            self.assertIn('"$HOME"/Library/LaunchAgents/org.example.test.plist', command)
            self.assertIn("|| exit $?", command)
            self.assertIn("launchctl kickstart -k", command)

    def test_unloaded_managed_launchd_job_without_plist_fails_explicitly(self) -> None:
        command = _launchd_command(
            {"label": "org.example.test"},
            self.topology.resolve_component("agent"),
            "restart",
        )
        self.assertIn("no plist is configured", command)
        self.assertIn("exit 1", command)

    def test_launchd_stop_start_restart_fixture_is_symmetric(self) -> None:
        component = self.topology.resolve_component("agent")
        launchctl = self.root / "launchctl"
        state = self.root / "launchd-loaded"
        calls = self.root / "launchd-calls"
        plist = self.root / "org.example.test.plist"
        plist.write_text("fixture", encoding="utf-8")
        state.write_text("loaded", encoding="utf-8")
        launchctl.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$1\" >> \"$LLMOPS_TEST_CALLS\"\n"
            "case \"$1\" in\n"
            "  print) test -e \"$LLMOPS_TEST_STATE\" ;;\n"
            "  bootstrap) test -e \"$3\" && : > \"$LLMOPS_TEST_STATE\" ;;\n"
            "  kickstart) test -e \"$LLMOPS_TEST_STATE\" ;;\n"
            "  bootout) rm -f \"$LLMOPS_TEST_STATE\" ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        launchctl.chmod(0o755)
        profile = {"label": "org.example.test", "plist": str(plist)}
        environment = {
            **os.environ,
            "PATH": f"{self.root}:{os.environ['PATH']}",
            "LLMOPS_TEST_STATE": str(state),
            "LLMOPS_TEST_CALLS": str(calls),
        }
        for action in ("stop", "start", "restart", "stop", "restart"):
            completed = subprocess.run(
                ["/bin/sh", "-c", _launchd_command(profile, component, action)],
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(state.exists())
        self.assertEqual(
            calls.read_text(encoding="utf-8").splitlines(),
            [
                "print",
                "bootout",
                "print",
                "print",
                "bootstrap",
                "kickstart",
                "print",
                "kickstart",
                "print",
                "bootout",
                "print",
                "print",
                "bootstrap",
                "kickstart",
            ],
        )

    def test_launchd_uses_user_domain_when_gui_domain_is_hidden_over_ssh(self) -> None:
        component = self.topology.resolve_component("agent")
        launchctl = self.root / "launchctl"
        calls = self.root / "launchd-calls"
        launchctl.write_text(
            "#!/bin/sh\n"
            "printf '%s %s\\n' \"$1\" \"$2\" >> \"$LLMOPS_TEST_CALLS\"\n"
            "case \"$1 $2\" in\n"
            "  'print gui/'*) exit 113 ;;\n"
            "  'print user/'*) exit 0 ;;\n"
            "  'kickstart -k') exit 0 ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        launchctl.chmod(0o755)
        environment = {
            **os.environ,
            "PATH": f"{self.root}:{os.environ['PATH']}",
            "LLMOPS_TEST_CALLS": str(calls),
        }
        profile = {"label": "org.example.test", "plist": "unused.plist"}
        for action in ("status", "start"):
            completed = subprocess.run(
                ["/bin/sh", "-c", _launchd_command(profile, component, action)],
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
        call_lines = calls.read_text(encoding="utf-8").splitlines()
        self.assertEqual(sum("print gui/" in line for line in call_lines), 2)
        self.assertEqual(sum("print user/" in line for line in call_lines), 2)
        self.assertTrue(any("kickstart -k" in line for line in call_lines))
        self.assertFalse(any("bootstrap" in line for line in call_lines))

    def test_launchd_bootstrap_permission_failure_is_explicit(self) -> None:
        component = self.topology.resolve_component("agent")
        launchctl = self.root / "launchctl"
        calls = self.root / "launchd-calls"
        plist = self.root / "org.example.test.plist"
        plist.write_text("fixture", encoding="utf-8")
        launchctl.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$1\" >> \"$LLMOPS_TEST_CALLS\"\n"
            "case \"$1\" in\n"
            "  print) exit 1 ;;\n"
            "  bootstrap) printf '%s\\n' 'Bootstrap failed: Operation not permitted' >&2; exit 77 ;;\n"
            "  kickstart) exit 0 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        launchctl.chmod(0o755)
        completed = subprocess.run(
            [
                "/bin/sh",
                "-c",
                _launchd_command(
                    {"label": "org.example.test", "plist": str(plist)},
                    component,
                    "start",
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
            env={
                **os.environ,
                "PATH": f"{self.root}:{os.environ['PATH']}",
                "LLMOPS_TEST_CALLS": str(calls),
            },
        )
        self.assertEqual(completed.returncode, 77)
        self.assertIn("Operation not permitted", completed.stderr)
        self.assertEqual(
            calls.read_text(encoding="utf-8").splitlines(),
            ["print", "print", "bootstrap"],
        )

    @mock.patch("llmops_kit.llmops_drivers.subprocess.run")
    def test_launchd_timeout_returns_bounded_failure(self, run: mock.Mock) -> None:
        component = self.topology.resolve_component("agent")
        run.side_effect = subprocess.TimeoutExpired(["launchctl", "kickstart"], 900)
        result = ComponentRunner(self.topology).run(component, "start")
        self.assertEqual(result.returncode, 124)
        self.assertIn("start timed out after 900 seconds", result.stderr)

    def test_trusted_host_snapshot_contains_complete_topology(self) -> None:
        destination = self.root / "snapshot"
        write_host_snapshot(self.topology, host_name="model-host", destination=destination)
        self.assertTrue((destination / "models/chat.json").is_file())
        self.assertTrue((destination / "models/embedding.json").is_file())
        self.assertTrue((destination / "services/proxy.json").is_file())
        self.assertTrue((destination / "agents/sample-agent.json").is_file())
        self.assertTrue((destination / "inventory.json").is_file())
        self.assertTrue((destination / "stacks/sample.json").is_file())
        inventory = json.loads((destination / "inventory.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {item["name"]: item["transport"] for item in inventory["hosts"]},
            {"agent-host": "ssh", "model-host": "local"},
        )
        complete_stack = json.loads((destination / "stacks/sample.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [item["id"] for item in complete_stack["components"]],
            ["chat", "embedding", "proxy", "agent"],
        )
        self.assertEqual(
            {item["id"]: item["host"] for item in complete_stack["components"]},
            {"chat": "model-host", "embedding": "model-host", "proxy": "agent-host", "agent": "agent-host"},
        )
        resolved = json.loads((destination / "resolved.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [item["id"] for item in resolved["components"]],
            ["sample:chat", "sample:embedding", "sample:proxy", "sample:agent"],
        )

    def test_untrusted_host_snapshot_is_role_filtered(self) -> None:
        inventory = json.loads(self.paths.inventory_file.read_text(encoding="utf-8"))
        inventory["hosts"][0]["trusted_control"] = False
        self.write_json(self.paths.inventory_file, inventory)
        config = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
        config["control"]["authority_host"] = "agent-host"
        self.write_json(self.paths.config_file, config)
        topology = Topology(
            stacks=load_stacks(self.paths),
            hosts=load_inventory(self.paths.inventory_file),
            paths=self.paths,
            config=load_config(paths=self.paths),
        )
        destination = self.root / "untrusted-snapshot"
        write_host_snapshot(topology, host_name="model-host", destination=destination)
        self.assertTrue((destination / "models/chat.json").is_file())
        self.assertTrue((destination / "models/embedding.json").is_file())
        self.assertFalse((destination / "services/proxy.json").exists())
        self.assertFalse((destination / "agents/sample-agent.json").exists())
        inventory_snapshot = json.loads((destination / "inventory.json").read_text(encoding="utf-8"))
        self.assertEqual([item["name"] for item in inventory_snapshot["hosts"]], ["model-host"])
        local_stack = json.loads((destination / "stacks/sample.json").read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in local_stack["components"]], ["chat", "embedding"])
        resolved = json.loads((destination / "resolved.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [item["id"] for item in resolved["components"]],
            ["sample:chat", "sample:embedding"],
        )

    def test_host_snapshots_share_complete_secret_free_catalog(self) -> None:
        model = self.root / "model-snapshot"
        agent = self.root / "agent-snapshot"
        write_host_snapshot(self.topology, host_name="model-host", destination=model)
        write_host_snapshot(self.topology, host_name="agent-host", destination=agent)
        self.assertEqual(
            (model / "catalog.json").read_bytes(),
            (agent / "catalog.json").read_bytes(),
        )
        catalog = json.loads((model / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [item["id"] for item in catalog["components"]],
            ["sample:chat", "sample:embedding", "sample:proxy", "sample:agent"],
        )
        self.assertEqual(
            {item["name"]: item["host"] for item in catalog["hosts"]},
            {"agent-host": "agent.local", "model-host": "model.local"},
        )
        self.assertNotIn("ssh_key", (model / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["authority_host"], "model-host")
        self.assertEqual(catalog["trusted_control_hosts"], ["agent-host", "model-host"])
        self.assertTrue(all(item["peer_observable"] for item in catalog["hosts"]))

    def test_host_operation_uses_absolute_peer_command(self) -> None:
        validate_host_operation(["component", "restart", "chat"])
        command = host_command(
            {
                "host": "model.local",
                "user": "operator",
                "port": 22,
                "public_bin_dir": "~/.local/bin",
            },
            ["component", "restart", "chat"],
            json_output=False,
        )
        self.assertEqual(command[-2], "operator@model.local")
        self.assertEqual(command[-1], '"$HOME"/.local/bin/llmops component restart chat')

    def test_host_operation_rejects_arbitrary_commands_and_config_overrides(self) -> None:
        with self.assertRaisesRegex(TopologyError, "not allowed"):
            validate_host_operation(["sh", "-c", "true"])
        with self.assertRaisesRegex(TopologyError, "cannot override"):
            validate_host_operation(["status", "--config-home", "/tmp/other"])

    def test_remote_status_uses_absolute_command_and_local_mode(self) -> None:
        args = type(
            "Args",
            (),
            {"all": False, "verbose": False, "host_timeout": 10},
        )()
        host = {
            "host": "model.local",
            "user": "operator",
            "port": 22,
            "public_bin_dir": "~/.local/bin",
        }
        completed = mock.Mock(returncode=0, stdout="[]\n", stderr="")
        with mock.patch.object(remote_status.__globals__["subprocess"], "run", return_value=completed) as run:
            payload, error = remote_status("model-host", host, None, args)
        self.assertEqual(payload, [])
        self.assertEqual(error, "")
        command = run.call_args.args[0]
        self.assertIn("operator@model.local", command)
        self.assertIn('"$HOME"/.local/bin/llmops status --host model-host --local --json', command[-1])

    def test_snapshot_host_uses_remote_status_for_a_different_execution_user(self) -> None:
        host = {"name": "model-host", "user": "service-user"}
        with mock.patch("llmops_kit.llmops_cli.pwd.getpwuid") as current_user:
            current_user.return_value.pw_name = "operator"
            self.assertFalse(is_local_status_host("model-host", host, "model-host"))
            host["user"] = "operator"
            self.assertTrue(is_local_status_host("model-host", host, "model-host"))

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
    def test_stack_status_defaults_to_only_configured_stack(self) -> None:
        stack_operations.__globals__["CURRENT_TOPOLOGY"] = self.topology
        args = type("Args", (), {"stack": None, "action": "status"})()
        operations = stack_operations(args)
        self.assertEqual(len(operations), 4)
        self.assertTrue(all(operation.action == "status" for operation in operations))

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

    def test_stack_stop_is_exact_reverse_of_start(self) -> None:
        stack = self.topology.stacks["sample"]
        started = [item.component.qualified_id for item in stack_plan(stack, "start")]
        stopped = [item.component.qualified_id for item in stack_plan(stack, "stop")]
        self.assertEqual(stopped, list(reversed(started)))

    def test_stack_lifecycle_batches_independent_components(self) -> None:
        stack = self.topology.stacks["sample"]
        start_batches = [
            [operation.component.component_id for operation in batch]
            for batch in operation_batches(stack_plan(stack, "start"))
        ]
        stop_batches = [
            [operation.component.component_id for operation in batch]
            for batch in operation_batches(stack_plan(stack, "stop"))
        ]
        self.assertEqual(start_batches, [["chat", "embedding"], ["proxy"], ["agent"]])
        self.assertEqual(stop_batches, [["agent"], ["embedding", "proxy"], ["chat"]])

    @mock.patch("llmops_kit.llmops_drivers.subprocess.run")
    def test_stack_lifecycle_skips_externally_owned_components_but_explicit_action_runs(
        self,
        run: mock.Mock,
    ) -> None:
        stack_config = json.loads((self.paths.stacks_dir / "sample.json").read_text(encoding="utf-8"))
        stack_config["components"][0]["ownership"] = "external"
        self.write_json(self.paths.stacks_dir / "sample.json", stack_config)
        topology = Topology(
            stacks=load_stacks(self.paths),
            hosts=self.topology.hosts,
            paths=self.paths,
            config=self.topology.config,
        )
        stack = topology.stacks["sample"]

        for action in ("start", "stop", "restart"):
            planned = stack_plan(stack, action)
            self.assertNotIn("sample:chat", [item.component.qualified_id for item in planned])

        status_components = [
            item.component.qualified_id for item in stack_plan(stack, "status")
        ]
        self.assertIn("sample:chat", status_components)

        chat = topology.resolve_component("chat")
        run.return_value = subprocess.CompletedProcess([], 0, "restarted\n", "")
        runner = ComponentRunner(topology)
        result = runner.run(chat, "restart")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "restarted")
        run.assert_called_once()

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
    def test_stack_executes_independent_wave_concurrently(self) -> None:
        barrier = threading.Barrier(2)

        class ConcurrentRunner(FakeRunner):
            def run(self, component, action):
                if action == "start" and component.component_id in {"chat", "embedding"}:
                    barrier.wait(timeout=5)
                return super().run(component, action)

        executor = Executor(self.topology, runner=ConcurrentRunner())
        executor.execute(stack_plan(self.topology.stacks["sample"], "start"))

    def test_failed_start_wave_rolls_back_successful_sibling(self) -> None:
        runner = FakeRunner(fail_start="sample:chat")
        executor = Executor(self.topology, runner=runner)

        with self.assertRaisesRegex(ExecutionError, "sample:chat: start failed"):
            executor.execute(stack_plan(self.topology.stacks["sample"], "start"))

        self.assertEqual(runner.running, set())
        self.assertIn(("sample:embedding", "stop"), runner.calls)

    def test_stack_execution_reports_live_progress(self) -> None:
        events: list[tuple[str, str]] = []
        runner = FakeRunner()
        executor = Executor(
            self.topology,
            runner=runner,
            progress=lambda event, operation: events.append(
                (event, operation.component.component_id)
            ),
        )

        executor.execute(stack_plan(self.topology.stacks["sample"], "start"))

        self.assertIn(("starting", "chat"), events)
        self.assertIn(("starting", "embedding"), events)
        self.assertIn(("ready", "chat"), events)
        self.assertIn(("ready", "agent"), events)
        self.assertLess(events.index(("ready", "chat")), events.index(("starting", "proxy")))
        self.assertLess(events.index(("ready", "proxy")), events.index(("starting", "agent")))

    def test_idempotent_stop_persists_requested_down_state(self) -> None:
        runner = FakeRunner()
        executor = Executor(self.topology, runner=runner)
        chat = self.topology.resolve_component("chat")
        executor.execute(component_plan(self.topology, chat, "stop"))
        states = LifecycleStateStore(self.paths.lifecycle_state_file).load()
        self.assertEqual(states["sample:chat"], "stopped")
        self.assertNotIn(("sample:chat", "stop"), runner.calls)

    def test_start_persists_requested_running_state(self) -> None:
        runner = FakeRunner()
        executor = Executor(self.topology, runner=runner)
        chat = self.topology.resolve_component("chat")
        executor.execute(component_plan(self.topology, chat, "start"))
        states = LifecycleStateStore(self.paths.lifecycle_state_file).load()
        self.assertEqual(states["sample:chat"], "running")

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

    def test_failed_start_releases_lifecycle_lock(self) -> None:
        runner = FakeRunner(fail_start="sample:chat")
        executor = Executor(self.topology, runner=runner)
        chat = self.topology.resolve_component("chat")
        with self.assertRaisesRegex(ExecutionError, "start failed"):
            executor.execute(component_plan(self.topology, chat, "start"))
        with operation_lock(self.paths.run_dir / "orchestrator.lock"):
            pass

    def test_failed_readiness_rolls_back_the_started_component(self) -> None:
        runner = FakeRunner(fail_health="sample:chat")
        executor = Executor(self.topology, runner=runner)
        chat = self.topology.resolve_component("chat")
        with self.assertRaisesRegex(Exception, "readiness timed out"):
            executor.execute(component_plan(self.topology, chat, "start"))
        self.assertNotIn("sample:chat", runner.running)
        self.assertIn(("sample:chat", "stop"), runner.calls)

    def test_stack_stop_continues_after_failure_and_persists_successes(self) -> None:
        stack = self.topology.stacks["sample"]
        components = {item.qualified_id for item in stack.components.values()}
        LifecycleStateStore(self.paths.lifecycle_state_file).save(
            {component: "running" for component in components}
        )
        runner = FakeRunner(running=components, fail_stop="sample:proxy")
        executor = Executor(self.topology, runner=runner)

        with self.assertRaisesRegex(ExecutionError, "sample:proxy: stop failed"):
            executor.execute(stack_plan(stack, "stop"))

        expected = [item.component.qualified_id for item in stack_plan(stack, "stop")]
        attempted = [component for component, action in runner.calls if action == "stop"]
        self.assertEqual(attempted, expected)
        self.assertEqual(runner.running, {"sample:proxy"})
        states = LifecycleStateStore(self.paths.lifecycle_state_file).load()
        self.assertEqual(states["sample:proxy"], "running")
        self.assertTrue(
            all(states[component] == "stopped" for component in components - {"sample:proxy"})
        )

    def test_stop_fails_when_component_survives_successful_command(self) -> None:
        runner = FakeRunner(running={"sample:chat"}, stubborn_stop="sample:chat")
        executor = Executor(self.topology, runner=runner)
        chat = self.topology.resolve_component("chat")

        with self.assertRaisesRegex(ExecutionError, "component is still running"):
            executor.execute(component_plan(self.topology, chat, "stop"))

        self.assertIn("sample:chat", runner.running)

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
