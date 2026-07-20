#!/usr/bin/env python
"""Typed component commands and host transport for LLM-Ops-Kit."""

from __future__ import annotations

import json
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    from llmops_inventory import HostRecord
    from llmops_topology import Component, Topology, TopologyError, load_profile
except ModuleNotFoundError:  # pragma: no cover
    from .llmops_inventory import HostRecord
    from .llmops_topology import Component, Topology, TopologyError, load_profile


class DriverError(RuntimeError):
    """Raised when a component command cannot be built or completed."""


@dataclass(frozen=True)
class CommandResult:
    """Result of one component command."""

    component: str
    action: str
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        """Return whether the command exited successfully."""

        return self.returncode == 0

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible result."""

        return {
            "component": self.component,
            "action": self.action,
            "command": self.command,
            "returncode": self.returncode,
            "ok": self.ok,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def _remote_root(path: str) -> str:
    if path == "~":
        return '"$HOME"'
    if path.startswith("~/"):
        return '"$HOME"/' + shlex.quote(path[2:])
    return shlex.quote(path)


def _managed_binary(host: HostRecord, name: str) -> str:
    return f"{_remote_root(host.install_root)}/bin/{shlex.quote(name)}"


def _require_actions(profile: dict[str, Any], component: Component) -> dict[str, list[str]]:
    raw = profile.get("actions")
    if not isinstance(raw, dict):
        raise DriverError(f"{component.qualified_id}: profile actions must be an object")
    actions: dict[str, list[str]] = {}
    for action, argv in raw.items():
        if not isinstance(action, str) or not isinstance(argv, list) or not argv:
            raise DriverError(f"{component.qualified_id}: every action must be a nonempty argv array")
        if any(not isinstance(token, str) or not token for token in argv):
            raise DriverError(f"{component.qualified_id}: action {action} contains an invalid argv token")
        actions[action] = argv
    return actions


def _launchd_command(profile: dict[str, Any], component: Component, action: str) -> str:
    label = profile.get("label")
    if not isinstance(label, str) or not label:
        raise DriverError(f"{component.qualified_id}: launchd profile requires label")
    domain = f'gui/$(id -u)/{shlex.quote(label)}'
    plist = profile.get("plist")
    if plist is not None and (not isinstance(plist, str) or not plist):
        raise DriverError(f"{component.qualified_id}: launchd plist must be a path string")
    if action == "status":
        return f"launchctl print {domain}"
    if action == "start":
        if plist:
            plist_expr = _remote_root(plist)
            return (
                f"launchctl print {domain} >/dev/null 2>&1 || "
                f"launchctl bootstrap gui/$(id -u) {plist_expr}; "
                f"launchctl kickstart -k {domain}"
            )
        return f"launchctl kickstart -k {domain}"
    if action == "stop":
        return (
            f"if launchctl print {domain} >/dev/null 2>&1; then "
            f"launchctl bootout {domain}; fi"
        )
    if action == "restart":
        return f"launchctl kickstart -k {domain}"
    raise DriverError(f"{component.qualified_id}: unsupported launchd action: {action}")


def build_component_command(topology: Topology, component: Component, action: str) -> str:
    """Build a safe remote shell command for one typed component action."""

    if action not in {"start", "stop", "restart", "status", "logs"}:
        raise DriverError(f"unsupported component action: {action}")
    host = topology.hosts[component.host]
    profile = load_profile(topology.paths, component)
    if component.driver == "modelctl":
        if action == "logs":
            raise DriverError(f"{component.qualified_id}: model logs require a profile log_path")
        binary = _managed_binary(host, "modelctl")
        return f"{binary} {shlex.quote(component.profile)} {shlex.quote(action)}"
    if component.driver in {"model-proxy", "tts-bridge"}:
        if action == "logs":
            log_path = profile.get("log_path", profile.get("log"))
            if not isinstance(log_path, str) or not log_path:
                raise DriverError(f"{component.qualified_id}: profile does not define log_path")
            return f"tail -n 100 {shlex.quote(log_path)}"
        binary = _managed_binary(host, component.driver)
        return f"{binary} {shlex.quote(action)}"
    if component.driver == "agent":
        actions = _require_actions(profile, component)
        argv = actions.get(action)
        if argv is None:
            if action == "logs":
                log_path = profile.get("log_path")
                if isinstance(log_path, str) and log_path:
                    return f"tail -n 100 {shlex.quote(log_path)}"
            raise DriverError(
                f"{component.qualified_id}: agent profile does not define action: {action}"
            )
        return shlex.join(argv)
    if component.driver in {"launchd", "ssh-tunnel"}:
        if action == "logs":
            log_path = profile.get("log_path", profile.get("stdout"))
            if not isinstance(log_path, str) or not log_path:
                raise DriverError(f"{component.qualified_id}: profile does not define log_path")
            return f"tail -n 100 {shlex.quote(log_path)}"
        return _launchd_command(profile, component, action)
    if component.driver in {"process", "command"}:
        actions = _require_actions(profile, component)
        argv = actions.get(action)
        if argv is None:
            if action == "logs":
                log_path = profile.get("log_path")
                if isinstance(log_path, str) and log_path:
                    return f"tail -n 100 {shlex.quote(log_path)}"
            raise DriverError(f"{component.qualified_id}: profile does not define action: {action}")
        return shlex.join(argv)
    raise DriverError(f"{component.qualified_id}: unsupported driver: {component.driver}")


class ComponentRunner:
    """Execute typed component commands through local or SSH transport."""

    def __init__(self, topology: Topology) -> None:
        self.topology = topology

    def run(self, component: Component, action: str) -> CommandResult:
        """Run one component action and capture output."""

        if component.ownership == "external" and action in {"start", "stop", "restart"}:
            raise DriverError(f"{component.qualified_id}: externally owned component is read-only")
        script = build_component_command(self.topology, component, action)
        host = self.topology.hosts[component.host]
        command = ["/bin/sh", "-c", script] if host.transport == "local" else host.ssh_base() + [script]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        return CommandResult(
            component=component.qualified_id,
            action=action,
            command=" ".join(shlex.quote(token) for token in command),
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )

    def status(self, component: Component) -> CommandResult:
        """Return the component's driver status result."""

        return self.run(component, "status")

    def wait_healthy(self, component: Component) -> CommandResult:
        """Wait for the configured readiness check to pass."""

        health = component.health
        if health.kind == "none":
            return CommandResult(component.qualified_id, "health", "none", 0, "", "")
        deadline = time.monotonic() + health.timeout_seconds
        last: Optional[CommandResult] = None
        while time.monotonic() < deadline:
            if health.kind == "driver":
                last = self.status(component)
            else:
                host = self.topology.hosts[component.host]
                if health.kind == "http":
                    script = f"curl -fsS --max-time 3 {shlex.quote(health.target)} >/dev/null"
                else:
                    target_host, separator, target_port = health.target.rpartition(":")
                    if not separator or not target_host or not target_port.isdigit():
                        raise DriverError(
                            f"{component.qualified_id}: TCP health target must be host:port"
                        )
                    script = f"nc -z -w 3 {shlex.quote(target_host)} {int(target_port)}"
                command = (
                    ["/bin/sh", "-c", script]
                    if host.transport == "local"
                    else host.ssh_base() + [script]
                )
                completed = subprocess.run(command, capture_output=True, text=True, check=False)
                last = CommandResult(
                    component.qualified_id,
                    "health",
                    " ".join(shlex.quote(token) for token in command),
                    completed.returncode,
                    completed.stdout.strip(),
                    completed.stderr.strip(),
                )
            if last.ok:
                return last
            time.sleep(1.0)
        detail = last.stderr or last.stdout if last is not None else "no health result"
        raise DriverError(f"{component.qualified_id}: readiness timed out: {detail}")
