#!/usr/bin/env python
"""Typed component commands and host transport for LLM-Ops-Kit."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, replace
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


@dataclass(frozen=True)
class ComponentObservation:
    """Independent lifecycle and readiness observation for one component."""

    lifecycle: str
    health: str
    observability: str
    lifecycle_result: CommandResult
    health_result: Optional[CommandResult] = None
    runtime_result: Optional[CommandResult] = None

    @property
    def running(self) -> bool:
        """Return whether the managed process or service is running."""

        return self.lifecycle == "running"


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


def _systemd_command(profile: dict[str, Any], component: Component, action: str) -> str:
    unit = profile.get("unit")
    if not isinstance(unit, str) or not unit.endswith(".service"):
        raise DriverError(f"{component.qualified_id}: systemd profile requires a .service unit")
    verbs = {"start": "start", "stop": "stop", "restart": "restart", "status": "status"}
    if action == "logs":
        return f"journalctl --user -u {shlex.quote(unit)} -n 100 --no-pager"
    if action not in verbs:
        raise DriverError(f"{component.qualified_id}: unsupported systemd action: {action}")
    return f"systemctl --user {verbs[action]} {shlex.quote(unit)}"


def _log_path(topology: Topology, component: Component, profile: dict[str, Any], channel: str) -> str:
    """Resolve a component log channel on the component host."""

    logging = profile.get("logging", {})
    if not isinstance(logging, dict):
        raise DriverError(f"{component.qualified_id}: profile logging must be an object")
    if component.driver == "model-proxy":
        paths = {
            "service": profile.get("log_path", profile.get("log")),
            "raw-request": logging.get("raw_request_log", str(topology.paths.logs_dir / "model-proxy.raw.log")),
            "rendered-prompt": logging.get("rendered_prompt_log", str(topology.paths.logs_dir / "model-proxy.rendered.log")),
            "raw-response": logging.get("raw_response_log", str(topology.paths.logs_dir / "model-proxy.raw.log")),
        }
    else:
        paths = {
            "service": profile.get("log_path", profile.get("log", profile.get("stdout"))),
        }
    path = paths.get(channel)
    if not isinstance(path, str) or not path:
        choices = ", ".join(sorted(paths))
        raise DriverError(
            f"{component.qualified_id}: log channel {channel!r} is unavailable; choose: {choices}"
        )
    return path


def build_component_command(
    topology: Topology,
    component: Component,
    action: str,
    *,
    log_channel: str = "service",
) -> str:
    """Build a safe remote shell command for one typed component action."""

    if action not in {"start", "stop", "restart", "status", "logs"}:
        raise DriverError(f"unsupported component action: {action}")
    host = topology.hosts[component.host]
    profile = load_profile(topology.paths, component)
    if component.driver == "modelctl":
        if action == "logs":
            log_path = profile.get("log_path")
            if not isinstance(log_path, str) or not log_path:
                log_path = str(topology.paths.logs_dir / f"llama-server-{component.profile.replace('.', '_')}.log")
            return f"tail -n 100 {shlex.quote(log_path)}"
        binary = _managed_binary(host, "modelctl")
        return f"{binary} {shlex.quote(component.profile)} {shlex.quote(action)}"
    if component.driver in {"model-proxy", "tts-bridge"}:
        if action == "logs":
            log_path = _log_path(topology, component, profile, log_channel)
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
        if profile.get("template_id") == "rtk":
            executable = profile.get("executable")
            if not isinstance(executable, str) or not executable:
                raise DriverError(f"{component.qualified_id}: RTK profile requires executable")
            if action == "status":
                resolved = _remote_root(executable)
                return f"test -x {resolved} && {resolved} --version"
            raise DriverError(f"{component.qualified_id}: tool lifecycle action is not applicable: {action}")
        actions = _require_actions(profile, component)
        argv = actions.get(action)
        if argv is None:
            if action == "logs":
                log_path = profile.get("log_path")
                if isinstance(log_path, str) and log_path:
                    return f"tail -n 100 {shlex.quote(log_path)}"
            raise DriverError(f"{component.qualified_id}: profile does not define action: {action}")
        return shlex.join(argv)
    if component.driver == "systemd":
        return _systemd_command(profile, component, action)
    raise DriverError(f"{component.qualified_id}: unsupported driver: {component.driver}")


class ComponentRunner:
    """Execute typed component commands through local or SSH transport."""

    def __init__(self, topology: Topology) -> None:
        self.topology = topology

    def _host(self, component: Component) -> HostRecord:
        host = self.topology.hosts[component.host]
        return replace(host, user=component.execution_user) if component.execution_user else host

    def run(
        self,
        component: Component,
        action: str,
        *,
        log_channel: str = "service",
    ) -> CommandResult:
        """Run one component action and capture output."""

        if component.ownership == "external" and action in {"start", "stop", "restart"}:
            raise DriverError(f"{component.qualified_id}: externally owned component is read-only")
        script = build_component_command(
            self.topology,
            component,
            action,
            log_channel=log_channel,
        )
        host = self._host(component)
        command = ["/bin/sh", "-c", script] if host.transport == "local" else host.ssh_base() + [script]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=getattr(component.timeouts, action),
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                component=component.qualified_id,
                action=action,
                command=" ".join(shlex.quote(token) for token in command),
                returncode=124,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr=f"{action} timed out after {getattr(component.timeouts, action)} seconds",
            )
        return CommandResult(
            component=component.qualified_id,
            action=action,
            command=" ".join(shlex.quote(token) for token in command),
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )

    def run_argv(
        self,
        component: Component,
        action: str,
        argv: list[str],
        *,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        """Run a validated adapter-owned argv action without a shell locally."""

        if not argv or any(not isinstance(token, str) or not token for token in argv):
            raise DriverError(f"{component.qualified_id}: invalid argv for action {action}")
        host = self._host(component)
        command = argv if host.transport == "local" else host.ssh_base() + [shlex.join(argv)]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout or component.timeouts.status,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                component=component.qualified_id,
                action=action,
                command=shlex.join(command),
                returncode=124,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr=f"{action} timed out after {timeout or component.timeouts.status} seconds",
            )
        return CommandResult(
            component=component.qualified_id,
            action=action,
            command=shlex.join(command),
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )

    def status(self, component: Component) -> CommandResult:
        """Return the component's driver status result."""

        return self.run(component, "status")

    def logs(self, component: Component, *, channel: str = "service") -> CommandResult:
        """Return recent output for one named log channel."""

        return self.run(component, "logs", log_channel=channel)

    def runtime_command(self, component: Component, result: CommandResult) -> Optional[CommandResult]:
        """Inspect the command line of a live PID reported by a typed driver."""

        match = re.search(r"(?:^|\s)pid=(\d+)(?:\s|$)", result.stdout)
        if match is None:
            return None
        host = self._host(component)
        script = f"ps -p {int(match.group(1))} -o command="
        command = ["/bin/sh", "-c", script] if host.transport == "local" else host.ssh_base() + [script]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        return CommandResult(
            component.qualified_id,
            "runtime",
            " ".join(shlex.quote(token) for token in command),
            completed.returncode,
            completed.stdout.strip(),
            completed.stderr.strip(),
        )

    @staticmethod
    def lifecycle_from_result(component: Component, result: CommandResult) -> str:
        """Interpret a driver status command as lifecycle, not readiness."""

        if result.returncode == 255:
            return "unknown"
        output = f"{result.stdout}\n{result.stderr}".casefold()
        if component.driver in {"model-proxy", "tts-bridge", "modelctl"}:
            if re.search(r"(^|\n)[^\n]*:\s+running(?:\s|$)", output):
                return "running"
            if re.search(r"(^|\n)[^\n]*:\s+(?:not running|stopped)(?:\s|$)", output):
                return "stopped"
        return "running" if result.ok else "stopped"

    def is_running(self, component: Component) -> bool:
        """Return lifecycle state without treating failed readiness as stopped."""

        return self.lifecycle_from_result(component, self.status(component)) == "running"

    def probe_health(
        self,
        component: Component,
        *,
        driver_result: Optional[CommandResult] = None,
    ) -> Optional[CommandResult]:
        """Run one configured readiness probe without retries."""

        health = component.health
        profile = load_profile(self.topology.paths, component)
        if profile.get("template_id") == "rtk":
            executable = profile.get("executable")
            if not isinstance(executable, str) or not executable:
                raise DriverError(f"{component.qualified_id}: RTK profile requires executable")
            resolved = _remote_root(executable)
            script = (
                f"output=$({resolved} telemetry status 2>&1); rc=$?; "
                'printf "%s\\n" "$output"; '
                'test "$rc" -eq 0 && printf "%s\\n" "$output" | '
                'grep -Eq "enabled:[[:space:]]+no"'
            )
            host = self._host(component)
            command = (
                ["/bin/sh", "-c", script]
                if host.transport == "local"
                else host.ssh_base() + [script]
            )
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            return CommandResult(
                component.qualified_id,
                "health",
                " ".join(shlex.quote(token) for token in command),
                completed.returncode,
                completed.stdout.strip(),
                completed.stderr.strip(),
            )
        if health.kind == "none":
            return None
        if health.kind == "driver":
            return driver_result or self.status(component)
        host = self._host(component)
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
        return CommandResult(
            component.qualified_id,
            "health",
            " ".join(shlex.quote(token) for token in command),
            completed.returncode,
            completed.stdout.strip(),
            completed.stderr.strip(),
        )

    def inspect(self, component: Component) -> ComponentObservation:
        """Observe lifecycle and health as separate component properties."""

        result = self.status(component)
        lifecycle = self.lifecycle_from_result(component, result)
        observability = "unreachable" if result.returncode == 255 else "observed"
        if lifecycle != "running":
            health = "unknown" if lifecycle == "unknown" else "not-applicable"
            return ComponentObservation(lifecycle, health, observability, result)
        health_result = self.probe_health(component, driver_result=result)
        if health_result is None:
            health = "not-applicable"
        else:
            health = "healthy" if health_result.ok else "degraded"
        return ComponentObservation(
            lifecycle,
            health,
            observability,
            result,
            health_result,
            self.runtime_command(component, result),
        )

    def wait_healthy(self, component: Component) -> CommandResult:
        """Wait for the configured readiness check to pass."""

        health = component.health
        if health.kind == "none":
            return CommandResult(component.qualified_id, "health", "none", 0, "", "")
        deadline = time.monotonic() + health.timeout_seconds
        last: Optional[CommandResult] = None
        while time.monotonic() < deadline:
            last = self.probe_health(component)
            if last.ok:
                return last
            time.sleep(1.0)
        detail = last.stderr or last.stdout if last is not None else "no health result"
        raise DriverError(f"{component.qualified_id}: readiness timed out: {detail}")
