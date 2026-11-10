#!/usr/bin/env python
"""Cross-stack lifecycle safety with shared infrastructure and two agents."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from unittest import mock

from llmops_kit import llmops_cli
from llmops_kit.llmops_drivers import CommandResult, ComponentRunner, DriverError
from llmops_kit.llmops_executor import Executor, ExecutionError, component_plan, stack_plan
from llmops_kit.llmops_topology import Stack, Topology, TopologyError, topological_order
from test_llmops_control import ControlFixture, FakeRunner


class SharedStackPlanningTests(ControlFixture):
    """Use only disposable fixtures, never live services or network calls."""

    def setUp(self) -> None:
        super().setUp()
        original = self.topology
        model = replace(original.resolve_component("sample:chat"), stack="shared", depends_on=())
        fresh = replace(
            original.resolve_component("sample:agent"),
            stack="fresh",
            depends_on=(model.qualified_id,),
        )
        legacy = replace(fresh, stack="legacy")
        dashboard = replace(fresh, component_id="dashboard", depends_on=(fresh.qualified_id,))
        stacks = {
            "shared": Stack("shared", self.root / "shared.json", {"chat": model}),
            "fresh": Stack("fresh", self.root / "fresh.json", {"agent": fresh, "dashboard": dashboard}),
            "legacy": Stack("legacy", self.root / "legacy.json", {"agent": legacy}),
        }
        self.topology = Topology(stacks=stacks, hosts=original.hosts, paths=original.paths, config=original.config)

    def test_cross_stack_start_includes_shared_before_agent_without_sibling(self) -> None:
        operations = stack_plan(self.topology.stacks["fresh"], "start", topology=self.topology)
        self.assertEqual(
            [op.component.qualified_id for op in operations],
            ["shared:chat", "fresh:agent", "fresh:dashboard"],
        )
        self.assertFalse(operations[0].rollback_on_failure)
        self.assertTrue(all(op.rollback_on_failure for op in operations[1:]))

    def test_component_start_includes_cross_stack_prerequisite(self) -> None:
        dashboard = self.topology.resolve_component("fresh:dashboard")
        operations = component_plan(self.topology, dashboard, "start")
        self.assertEqual([op.component.qualified_id for op in operations],
                         ["shared:chat", "fresh:agent", "fresh:dashboard"])

    def test_failed_component_start_keeps_newly_started_shared_dependency(self) -> None:
        runner = FakeRunner(fail_start="fresh:agent")
        dashboard = self.topology.resolve_component("fresh:dashboard")
        with self.assertRaises(ExecutionError):
            Executor(self.topology, runner=runner).execute_component(dashboard, "start")
        self.assertIn("shared:chat", runner.running)
        self.assertNotIn(("shared:chat", "stop"), runner.calls)

    def test_agent_stop_and_restart_never_stop_shared_or_sibling(self) -> None:
        for action in ("stop", "restart"):
            with self.subTest(action=action):
                operations = stack_plan(self.topology.stacks["fresh"], action, topology=self.topology)
                stopped = {op.component.qualified_id for op in operations if op.action == "stop"}
                self.assertEqual(stopped, {"fresh:agent", "fresh:dashboard"})
                self.assertNotIn("legacy:agent", {op.component.qualified_id for op in operations})
                if action == "restart":
                    self.assertIn("shared:chat", {op.component.qualified_id for op in operations if op.action == "start"})

    def test_full_system_start_and_stop_are_unique_and_dependency_ordered(self) -> None:
        parser = llmops_cli.build_parser()
        with mock.patch.object(llmops_cli, "CURRENT_TOPOLOGY", self.topology, create=True):
            starts = llmops_cli.stack_operations(parser.parse_args(["stack", "start", "--all"]))
            stops = llmops_cli.stack_operations(parser.parse_args(["stack", "stop", "--all"]))
        start_ids = [op.component.qualified_id for op in starts]
        stop_ids = [op.component.qualified_id for op in stops]
        self.assertEqual(len(start_ids), len(set(start_ids)))
        self.assertEqual(set(start_ids), {item.qualified_id for item in self.topology.all_components()})
        self.assertEqual(stop_ids, list(reversed(start_ids)))
        self.assertLess(start_ids.index("shared:chat"), start_ids.index("fresh:agent"))
        self.assertLess(start_ids.index("shared:chat"), start_ids.index("legacy:agent"))

    def test_all_plan_parser_and_status_all_are_explicit(self) -> None:
        parser = llmops_cli.build_parser()
        plan = parser.parse_args(["stack", "plan", "start", "--all"])
        self.assertTrue(plan.all_stacks)
        self.assertIsNone(plan.stack)
        args = parser.parse_args(["stack", "status", "--all"])
        self.assertTrue(args.all_stacks)
        with mock.patch.object(llmops_cli, "CURRENT_TOPOLOGY", self.topology, create=True), \
             mock.patch.object(llmops_cli, "_collect_status", return_value=[] ) as collect, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(llmops_cli.cmd_stack_run(args), 0)
        self.assertIsNone(collect.call_args.args[0].selector)

    def test_named_stack_and_all_are_mutually_exclusive(self) -> None:
        args = llmops_cli.build_parser().parse_args(["stack", "start", "fresh", "--all"])
        with mock.patch.object(llmops_cli, "CURRENT_TOPOLOGY", self.topology, create=True):
            with self.assertRaises(TopologyError):
                llmops_cli.stack_operations(args)

    def test_unknown_cross_stack_dependency_is_rejected(self) -> None:
        legacy = self.topology.resolve_component("legacy:agent")
        stack = replace(self.topology.stacks["legacy"],
                        components={"agent": replace(legacy, depends_on=("missing:chat",))})
        topology = replace(self.topology, stacks={**self.topology.stacks, "legacy": stack})
        with self.assertRaisesRegex(TopologyError, "dependency not found"):
            topological_order(topology)

    def test_disabled_shared_prerequisite_cannot_be_silently_skipped(self) -> None:
        shared = self.topology.resolve_component("shared:chat")
        stack = replace(self.topology.stacks["shared"],
                        components={"chat": replace(shared, enabled=False)})
        topology = replace(self.topology, stacks={**self.topology.stacks, "shared": stack})
        dashboard = topology.resolve_component("fresh:dashboard")
        with self.assertRaisesRegex(TopologyError, "disabled"):
            component_plan(topology, dashboard, "start")
        with self.assertRaisesRegex(TopologyError, "disabled"):
            stack_plan(topology.stacks["fresh"], "start", topology=topology)

    def test_cross_stack_cycle_is_rejected(self) -> None:
        shared = self.topology.resolve_component("shared:chat")
        stack = replace(self.topology.stacks["shared"],
                        components={"chat": replace(shared, depends_on=("legacy:agent",))})
        topology = replace(self.topology, stacks={**self.topology.stacks, "shared": stack})
        with self.assertRaisesRegex(TopologyError, "cycle"):
            topological_order(topology)

    def test_shared_stop_refuses_if_other_stack_is_running(self) -> None:
        runner = FakeRunner(running={"shared:chat", "legacy:agent"})
        operations = stack_plan(self.topology.stacks["shared"], "stop", topology=self.topology)
        with self.assertRaisesRegex(ExecutionError, "active dependents"):
            Executor(self.topology, runner=runner).execute(operations)
        self.assertEqual(runner.calls, [])
        self.assertIn("shared:chat", runner.running)

    def test_shared_stop_refuses_unobservable_other_stack(self) -> None:
        class UnknownRunner(FakeRunner):
            def status(self, component):
                if component.qualified_id == "legacy:agent":
                    return CommandResult(component.qualified_id, "status", "fake", 255, "", "unreachable")
                return super().status(component)

            def lifecycle_from_result(self, component, result):
                if result.returncode == 255:
                    return "unknown"
                return "running" if result.returncode == 0 else "stopped"

        runner = UnknownRunner(running={"shared:chat"})
        operations = stack_plan(self.topology.stacks["shared"], "stop", topology=self.topology)
        with self.assertRaisesRegex(ExecutionError, "dependent state"):
            Executor(self.topology, runner=runner).execute(operations)
        self.assertEqual(runner.calls, [])
        self.assertIn("shared:chat", runner.running)

    def test_explicit_force_can_stop_shared_even_when_dependent_runs(self) -> None:
        runner = FakeRunner(running={"shared:chat", "legacy:agent"})
        shared = self.topology.resolve_component("shared:chat")
        Executor(self.topology, runner=runner).execute_component(shared, "stop", force=True)
        self.assertNotIn("shared:chat", runner.running)
        self.assertIn("legacy:agent", runner.running)

    def test_explicit_force_skips_unobservable_consumer_for_target_only_stop(self) -> None:
        class UnobservableConsumer(FakeRunner):
            def is_running(self, component):
                if component.qualified_id == "legacy:agent":
                    raise DriverError("legacy consumer state unknown")
                return super().is_running(component)

        runner = UnobservableConsumer(running={"shared:chat"})
        shared = self.topology.resolve_component("shared:chat")
        Executor(self.topology, runner=runner).execute_component(shared, "stop", force=True)
        self.assertNotIn("shared:chat", runner.running)
        self.assertEqual(runner.calls, [("shared:chat", "stop")])

    def test_failed_agent_start_keeps_newly_started_shared_dependency(self) -> None:
        runner = FakeRunner(fail_start="fresh:agent")
        operations = stack_plan(self.topology.stacks["fresh"], "start", topology=self.topology)
        with self.assertRaises(ExecutionError):
            Executor(self.topology, runner=runner).execute(operations)
        self.assertIn("shared:chat", runner.running)
        self.assertNotIn(("shared:chat", "stop"), runner.calls)
        self.assertNotIn(("fresh:dashboard", "start"), runner.calls)

    def test_running_but_unhealthy_prerequisite_blocks_agent(self) -> None:
        runner = FakeRunner(running={"shared:chat"}, fail_health="shared:chat")
        operations = stack_plan(self.topology.stacks["fresh"], "start", topology=self.topology)
        with self.assertRaises(DriverError):
            Executor(self.topology, runner=runner).execute(operations)
        self.assertNotIn(("fresh:agent", "start"), runner.calls)
        self.assertIn("shared:chat", runner.running)

    def test_timeout_and_transport_errors_never_report_a_stopped_target(self) -> None:
        runner = ComponentRunner(self.topology)
        target = self.topology.resolve_component("shared:chat")
        for returncode in (2, 124, 126, 127, 255):
            with self.subTest(returncode=returncode):
                result = CommandResult(target.qualified_id, "status", "fake", returncode, "", "unreachable")
                self.assertEqual(runner.lifecycle_from_result(target, result), "unknown")
                with mock.patch.object(runner, "status", return_value=result):
                    with self.assertRaisesRegex(DriverError, "unknown|unreachable"):
                        runner.is_running(target)

    def test_pid_mismatch_and_running_unknown_markers_are_not_stopped(self) -> None:
        runner = ComponentRunner(self.topology)
        target = self.topology.resolve_component("shared:chat")
        for marker in ("status=pid_mismatch", "running=unknown"):
            with self.subTest(marker=marker):
                result = CommandResult(target.qualified_id, "status", "fake", 1, f"model: {marker}", "")
                self.assertEqual(runner.lifecycle_from_result(target, result), "unknown")
                with mock.patch.object(runner, "status", return_value=result):
                    with self.assertRaisesRegex(DriverError, "unknown"):
                        runner.is_running(target)

    def test_launchd_specific_missing_job_is_stopped_but_other_errors_are_unknown(self) -> None:
        runner = ComponentRunner(self.topology)
        target = replace(self.topology.resolve_component("fresh:agent"), driver="launchd")
        missing = CommandResult(target.qualified_id, "status", "fake", 113, "", "Could not find service")
        other = CommandResult(target.qualified_id, "status", "fake", 113, "", "domain unavailable")
        self.assertEqual(runner.lifecycle_from_result(target, missing), "stopped")
        self.assertEqual(runner.lifecycle_from_result(target, other), "unknown")

    def test_unknown_target_stop_is_not_reported_as_already_stopped(self) -> None:
        runner = ComponentRunner(self.topology)
        target = self.topology.resolve_component("legacy:agent")
        result = CommandResult(target.qualified_id, "status", "fake", 255, "", "unreachable")
        with mock.patch.object(runner, "status", return_value=result), \
             mock.patch.object(runner, "run") as run:
            with self.assertRaisesRegex(ExecutionError, "unknown|unreachable"):
                Executor(self.topology, runner=runner).execute_component(target, "stop")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
