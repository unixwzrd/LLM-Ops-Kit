#!/usr/bin/env python
"""Dependency-aware component planning and lifecycle execution."""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

try:
    from llmops_drivers import CommandResult, ComponentRunner, DriverError
    from llmops_lifecycle_state import LifecycleStateError, LifecycleStateStore
    from llmops_topology import (
        Component,
        Stack,
        Topology,
        TopologyError,
        dependency_closure,
        dependent_closure,
        topological_order,
    )
except ModuleNotFoundError:  # pragma: no cover
    from .llmops_drivers import CommandResult, ComponentRunner, DriverError
    from .llmops_lifecycle_state import LifecycleStateError, LifecycleStateStore
    from .llmops_topology import (
        Component,
        Stack,
        Topology,
        TopologyError,
        dependency_closure,
        dependent_closure,
        topological_order,
    )


class ExecutionError(RuntimeError):
    """Raised when a planned lifecycle operation fails."""


@dataclass(frozen=True)
class Operation:
    """One ordered component lifecycle operation."""

    component: Component
    action: str

    def as_dict(self) -> dict[str, str]:
        """Return a stable JSON-compatible operation."""

        return {
            "component": self.component.qualified_id,
            "host": self.component.host,
            "driver": self.component.driver,
            "action": self.action,
        }


@dataclass(frozen=True)
class MutationPlan:
    """A component plan plus currently active dependent impact."""

    operations: tuple[Operation, ...]
    active_dependents: tuple[Component, ...] = ()

    @property
    def requires_force(self) -> bool:
        """Return whether a target-only stop would disrupt dependents."""

        return bool(self.active_dependents)


def component_plan(
    topology: Topology,
    component: Component,
    action: str,
    *,
    cascade: bool = False,
    no_deps: bool = False,
) -> list[Operation]:
    """Build an ordered plan for one component action."""

    if not component.enabled:
        raise TopologyError(f"{component.qualified_id}: component is disabled")
    stack = topology.stacks[component.stack]
    if action == "start":
        selected = {component.qualified_id} if no_deps else dependency_closure(stack, component)
        return [Operation(item, "start") for item in topological_order(stack, subset=selected) if item.enabled]
    if action == "stop":
        selected = dependent_closure(stack, component) if cascade else {component.qualified_id}
        return [
            Operation(item, "stop")
            for item in reversed(topological_order(stack, subset=selected))
            if item.enabled
        ]
    if action == "restart":
        if not cascade:
            return [Operation(component, "restart")]
        selected = dependent_closure(stack, component)
        ordered = [item for item in topological_order(stack, subset=selected) if item.enabled]
        dependents = [item for item in ordered if item.qualified_id != component.qualified_id]
        return (
            [Operation(item, "stop") for item in reversed(dependents)]
            + [Operation(component, "restart")]
            + [Operation(item, "start") for item in dependents]
        )
    if action in {"status", "logs"}:
        return [Operation(component, action)]
    raise TopologyError(f"unsupported component action: {action}")


def stack_plan(stack: Stack, action: str) -> list[Operation]:
    """Build an ordered plan for a complete stack action."""

    ordered = [item for item in topological_order(stack) if item.enabled]
    lifecycle_components = [item for item in ordered if item.ownership == "managed"]
    if action == "start":
        return [Operation(item, "start") for item in lifecycle_components]
    if action == "stop":
        return [Operation(item, "stop") for item in reversed(lifecycle_components)]
    if action == "restart":
        return [Operation(item, "stop") for item in reversed(lifecycle_components)] + [
            Operation(item, "start") for item in lifecycle_components
        ]
    if action == "status":
        return [Operation(item, "status") for item in ordered]
    raise TopologyError(f"unsupported stack action: {action}")


@contextmanager
def operation_lock(path: Path) -> Iterator[None]:
    """Serialize mutating orchestration commands."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ExecutionError(f"another lifecycle operation holds {path}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Executor:
    """Execute component plans with idempotence and bounded rollback."""

    def __init__(self, topology: Topology, runner: Optional[ComponentRunner] = None) -> None:
        self.topology = topology
        self.runner = runner or ComponentRunner(topology)

    def active_dependents(self, component: Component) -> list[Component]:
        """Return running downstream dependents, excluding the target."""

        stack = self.topology.stacks[component.stack]
        selected = dependent_closure(stack, component) - {component.qualified_id}
        ordered = topological_order(stack, subset=selected)
        return [item for item in ordered if self.runner.is_running(item)]

    def prepare_component(
        self,
        component: Component,
        action: str,
        *,
        cascade: bool = False,
        no_deps: bool = False,
    ) -> MutationPlan:
        """Build a component plan and calculate its current operational impact."""

        dependents: tuple[Component, ...] = ()
        if action == "stop" and not cascade:
            dependents = tuple(self.active_dependents(component))
        operations = component_plan(
            self.topology,
            component,
            action,
            cascade=cascade,
            no_deps=no_deps,
        )
        return MutationPlan(tuple(operations), dependents)

    def execute_component(
        self,
        component: Component,
        action: str,
        *,
        cascade: bool = False,
        no_deps: bool = False,
        force: bool = False,
    ) -> list[CommandResult]:
        """Safely prepare and execute a component lifecycle mutation."""

        prepared = self.prepare_component(
            component,
            action,
            cascade=cascade,
            no_deps=no_deps,
        )
        if prepared.requires_force and not force:
            names = ", ".join(item.qualified_id for item in prepared.active_dependents)
            raise ExecutionError(
                f"{component.qualified_id}: active dependents: {names}; use --force or --cascade"
            )
        return self.execute(list(prepared.operations))

    def execute(self, operations: list[Operation]) -> list[CommandResult]:
        """Execute a plan, rolling back only newly started components on failure."""

        results: list[CommandResult] = []
        started: list[Component] = []
        lock_path = self.topology.paths.run_dir / "orchestrator.lock"
        state_store = LifecycleStateStore(self.topology.paths.lifecycle_state_file)
        with operation_lock(lock_path):
            try:
                desired = state_store.load()
                for operation in operations:
                    component = operation.component
                    action = operation.action
                    if action == "start":
                        if self.runner.is_running(component):
                            desired[component.qualified_id] = "running"
                            continue
                        result = self.runner.run(component, "start")
                        results.append(result)
                        if not result.ok:
                            raise ExecutionError(
                                f"{component.qualified_id}: start failed: {result.stderr or result.stdout}"
                            )
                        started.append(component)
                        self.runner.wait_healthy(component)
                        desired[component.qualified_id] = "running"
                    elif action == "restart":
                        result = self.runner.run(component, "restart")
                        results.append(result)
                        if not result.ok:
                            raise ExecutionError(
                                f"{component.qualified_id}: restart failed: {result.stderr or result.stdout}"
                            )
                        self.runner.wait_healthy(component)
                        desired[component.qualified_id] = "running"
                    elif action == "stop":
                        if not self.runner.is_running(component):
                            desired[component.qualified_id] = "stopped"
                            continue
                        result = self.runner.run(component, "stop")
                        results.append(result)
                        if not result.ok:
                            raise ExecutionError(
                                f"{component.qualified_id}: stop failed: {result.stderr or result.stdout}"
                            )
                        desired[component.qualified_id] = "stopped"
                    else:
                        results.append(self.runner.run(component, action))
                if any(operation.action in {"start", "stop", "restart"} for operation in operations):
                    state_store.save(desired)
            except (DriverError, ExecutionError, LifecycleStateError):
                for component in reversed(started):
                    self.runner.run(component, "stop")
                raise
        return results

    def inspect(self, operations: list[Operation]) -> list[CommandResult]:
        """Execute read-only status or log operations without taking the lifecycle lock."""

        results: list[CommandResult] = []
        for operation in operations:
            if operation.action not in {"status", "logs"}:
                raise ExecutionError(f"read-only inspection cannot run {operation.action}")
            results.append(self.runner.run(operation.component, operation.action))
        return results
