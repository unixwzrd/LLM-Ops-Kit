#!/usr/bin/env python
"""Dependency-aware component planning and lifecycle execution."""

from __future__ import annotations

import fcntl
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

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


def operation_batches(operations: list[Operation]) -> list[list[Operation]]:
    """Group lifecycle operations into dependency-safe concurrent waves."""

    batches: list[list[Operation]] = []
    offset = 0
    while offset < len(operations):
        action = operations[offset].action
        end = offset
        while end < len(operations) and operations[end].action == action:
            end += 1
        group = list(operations[offset:end])
        if action not in {"start", "stop"}:
            batches.extend([[operation] for operation in group])
            offset = end
            continue

        pending = group
        while pending:
            pending_ids = {operation.component.qualified_id for operation in pending}
            if action == "start":
                ready = [
                    operation
                    for operation in pending
                    if not pending_ids.intersection(operation.component.depends_on)
                ]
            else:
                pending_dependencies = {
                    dependency
                    for operation in pending
                    for dependency in operation.component.depends_on
                }
                ready = [
                    operation
                    for operation in pending
                    if operation.component.qualified_id not in pending_dependencies
                ]
            if not ready:
                raise ExecutionError("lifecycle plan contains an unresolved dependency cycle")
            batches.append(ready)
            ready_ids = {id(operation) for operation in ready}
            pending = [operation for operation in pending if id(operation) not in ready_ids]
        offset = end
    return batches


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

    def __init__(
        self,
        topology: Topology,
        runner: Optional[ComponentRunner] = None,
        progress: Optional[Callable[[str, Operation], None]] = None,
    ) -> None:
        self.topology = topology
        self.runner = runner or ComponentRunner(topology)
        self.progress = progress

    def _report(self, event: str, operation: Operation) -> None:
        """Emit an optional synchronous lifecycle progress event."""

        if self.progress is not None:
            self.progress(event, operation)

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
        """Execute dependency-safe waves, rolling back newly started components on failure."""

        results: list[CommandResult] = []
        started: list[Component] = []
        stop_failures: list[str] = []
        best_effort_stop = bool(operations) and all(
            operation.action == "stop" for operation in operations
        )
        lock_path = self.topology.paths.run_dir / "orchestrator.lock"
        state_store = LifecycleStateStore(self.topology.paths.lifecycle_state_file)
        with operation_lock(lock_path):
            try:
                desired = state_store.load()
                for batch in operation_batches(operations):
                    pending_event = {
                        "start": "starting",
                        "stop": "stopping",
                        "restart": "restarting",
                    }.get(batch[0].action, "running")
                    for operation in batch:
                        self._report(pending_event, operation)
                    with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                        futures = {
                            pool.submit(self._execute_operation, operation): index
                            for index, operation in enumerate(batch)
                        }
                        ordered_outcomes: list[
                            Optional[
                                tuple[
                                    Operation,
                                    Optional[CommandResult],
                                    bool,
                                    Optional[Exception],
                                ]
                            ]
                        ] = [None] * len(batch)
                        for future in as_completed(futures):
                            outcome = future.result()
                            ordered_outcomes[futures[future]] = outcome
                            operation, result, _, failure = outcome
                            if failure is not None:
                                event = "failed"
                            elif operation.action == "start":
                                event = "ready" if result is not None else "already running"
                            elif operation.action == "stop":
                                event = "stopped" if result is not None else "already stopped"
                            elif operation.action == "restart":
                                event = "ready"
                            else:
                                event = "complete"
                            self._report(event, operation)
                    outcomes = [outcome for outcome in ordered_outcomes if outcome is not None]
                    batch_failure: Optional[Exception] = None
                    for operation, result, newly_started, failure in outcomes:
                        component = operation.component
                        if result is not None:
                            results.append(result)
                        if newly_started:
                            started.append(component)
                        if failure is not None:
                            if operation.action == "stop" and best_effort_stop:
                                stop_failures.append(str(failure))
                                continue
                            if batch_failure is None:
                                batch_failure = failure
                            continue
                        if operation.action in {"start", "restart"}:
                            desired[component.qualified_id] = "running"
                        elif operation.action == "stop":
                            desired[component.qualified_id] = "stopped"
                            state_store.save(desired)
                    if batch_failure is not None:
                        raise batch_failure
                if stop_failures:
                    raise ExecutionError("; ".join(stop_failures))
                if any(operation.action in {"start", "stop", "restart"} for operation in operations):
                    state_store.save(desired)
            except (DriverError, ExecutionError, LifecycleStateError):
                for component in reversed(started):
                    self.runner.run(component, "stop")
                raise
        return results

    def _execute_operation(
        self,
        operation: Operation,
    ) -> tuple[Operation, Optional[CommandResult], bool, Optional[Exception]]:
        """Execute one operation inside a dependency wave."""

        component = operation.component
        action = operation.action
        try:
            if action == "start":
                if self.runner.is_running(component):
                    return operation, None, False, None
                result = self.runner.run(component, "start")
                if not result.ok:
                    return operation, result, False, ExecutionError(
                        f"{component.qualified_id}: start failed: {result.stderr or result.stdout}"
                    )
                try:
                    self.runner.wait_healthy(component)
                except (DriverError, ExecutionError, LifecycleStateError) as exc:
                    return operation, result, True, exc
                return operation, result, True, None
            if action == "restart":
                result = self.runner.run(component, "restart")
                if not result.ok:
                    return operation, result, False, ExecutionError(
                        f"{component.qualified_id}: restart failed: {result.stderr or result.stdout}"
                    )
                try:
                    self.runner.wait_healthy(component)
                except (DriverError, ExecutionError, LifecycleStateError) as exc:
                    return operation, result, False, exc
                return operation, result, False, None
            if action == "stop":
                if not self.runner.is_running(component):
                    return operation, None, False, None
                result = self.runner.run(component, "stop")
                if not result.ok:
                    return operation, result, False, ExecutionError(
                        f"{component.qualified_id}: stop failed: {result.stderr or result.stdout}"
                    )
                try:
                    self.runner.wait_stopped(component)
                except (DriverError, ExecutionError, LifecycleStateError) as exc:
                    return operation, result, False, exc
                return operation, result, False, None
            return operation, self.runner.run(component, action), False, None
        except (DriverError, ExecutionError, LifecycleStateError) as exc:
            return operation, None, False, exc

    def inspect(self, operations: list[Operation]) -> list[CommandResult]:
        """Execute read-only status or log operations without taking the lifecycle lock."""

        results: list[CommandResult] = []
        for operation in operations:
            if operation.action not in {"status", "logs"}:
                raise ExecutionError(f"read-only inspection cannot run {operation.action}")
            results.append(self.runner.run(operation.component, operation.action))
        return results
