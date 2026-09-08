#!/usr/bin/env python
"""Typed component commands and host transport for LLM-Ops-Kit."""

from __future__ import annotations

import json
import os
import pwd
import re
import signal
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Optional

try:
    from llmops_inventory import HostRecord
    from llmops_profiles import model_values
    from llmops_templates import load_template_registry
    from llmops_topology import Component, Topology, TopologyError, load_profile
except ModuleNotFoundError:  # pragma: no cover
    from .llmops_inventory import HostRecord
    from .llmops_profiles import model_values
    from .llmops_templates import load_template_registry
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


@dataclass(frozen=True)
class LogChannelRecord:
    """Resolved, host-qualified component log channel."""

    component: str
    channel: str
    host: str
    execution_user: str
    path: str = ""
    provider: str = "file"
    available: Optional[bool] = None
    readable: Optional[bool] = None
    size: Optional[int] = None
    modified_at: Optional[int] = None
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation."""

        return {
            "component": self.component,
            "channel": self.channel,
            "host": self.host,
            "execution_user": self.execution_user,
            "path": self.path,
            "provider": self.provider,
            "available": self.available,
            "readable": self.readable,
            "size": self.size,
            "modified_at": self.modified_at,
            "error": self.error,
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
    gui_domain = f'gui/$(id -u)/{shlex.quote(label)}'
    user_domain = f'user/$(id -u)/{shlex.quote(label)}'
    plist = profile.get("plist")
    if plist is not None and (not isinstance(plist, str) or not plist):
        raise DriverError(f"{component.qualified_id}: launchd plist must be a path string")
    if action == "status":
        return (
            f"launchctl print {gui_domain} 2>/dev/null || "
            f"launchctl print {user_domain}"
        )
    if action in {"start", "restart"}:
        bootstrap = (
            f"launchctl bootstrap gui/$(id -u) {_remote_root(plist)} || exit $?"
            if plist
            else (
                f"printf '%s\\n' {shlex.quote(f'{component.qualified_id}: managed launchd job is unloaded and no plist is configured')} >&2; "
                "exit 1"
            )
        )
        return (
            f"if launchctl print {gui_domain} >/dev/null 2>&1; then "
            f"launchctl kickstart -k {gui_domain}; "
            f"elif launchctl print {user_domain} >/dev/null 2>&1; then "
            f"launchctl kickstart -k {user_domain}; "
            f"else {bootstrap}; launchctl kickstart -k {gui_domain}; fi"
        )
    if action == "stop":
        return (
            f"if launchctl print {gui_domain} >/dev/null 2>&1; then "
            f"launchctl bootout {gui_domain}; "
            f"elif launchctl print {user_domain} >/dev/null 2>&1; then "
            f"launchctl bootout {user_domain}; fi"
        )
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
            "service": profile.get(
                "log_path",
                profile.get("log", str(topology.paths.logs_dir / "model-proxy.ndjson")),
            ),
            "raw-request": logging.get("raw_request_log", str(topology.paths.logs_dir / "model-proxy.raw.log")),
            "rendered-prompt": logging.get("rendered_prompt_log", str(topology.paths.logs_dir / "model-proxy.rendered.log")),
            "raw-response": logging.get("raw_response_log", str(topology.paths.logs_dir / "model-proxy.raw.log")),
        }
    elif component.driver == "tts-bridge":
        paths = {
            "service": profile.get(
                "log_path",
                profile.get("log", str(topology.paths.logs_dir / "tts-bridge.log")),
            ),
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


def _modelctl_log_path(topology: Topology, component: Component, profile: dict[str, Any]) -> str:
    """Resolve the service log produced by modelctl for the profile type."""

    configured = profile.get("log_path")
    if isinstance(configured, str) and configured:
        return configured
    values = model_values(profile)
    model_type = values.get("MODEL_TYPE", str(profile.get("type", ""))).casefold()
    prefix = "tts-server" if model_type == "tts" else "llama-server"
    profile_name = component.profile.replace(".", "_")
    return str(topology.paths.logs_dir / f"{prefix}-{profile_name}.log")


def _shell_path(path: str) -> str:
    """Quote a path while allowing the execution user's home to resolve remotely."""

    if path == "~":
        return '"$HOME"'
    if path.startswith("~/"):
        return f'"$HOME"/{shlex.quote(path[2:])}'
    return shlex.quote(path)


def _dotted_value(document: dict[str, Any], path: str) -> Any:
    value: Any = document
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _template_log_path(
    topology: Topology,
    component: Component,
    profile: dict[str, Any],
    channel: str,
    definition: dict[str, Any],
) -> tuple[str, str]:
    """Resolve one audited template log definition to a path or provider."""

    provider = str(definition.get("provider", "file"))
    if provider != "file":
        unit = _dotted_value(profile, "unit")
        return (str(unit) if isinstance(unit, str) else ""), provider
    if component.driver == "modelctl":
        return _modelctl_log_path(topology, component, profile), provider
    configured = definition.get("path")
    if isinstance(configured, str) and configured:
        configured = configured.format(profile=component.profile)
        if configured.startswith("state:"):
            configured = str(topology.paths.state_home / configured.removeprefix("state:"))
        return configured, provider
    path_field = definition.get("path_field")
    if isinstance(path_field, str) and path_field:
        value = _dotted_value(profile, path_field)
        return (str(value), provider) if isinstance(value, str) and value else ("", provider)
    try:
        return _log_path(topology, component, profile, channel), provider
    except DriverError:
        return "", provider


def resolve_log_channels(topology: Topology, component: Component) -> tuple[LogChannelRecord, ...]:
    """Resolve declared log channels without contacting the component host."""

    profile = load_profile(topology.paths, component)
    template_id = component.template_id or str(profile.get("template_id", ""))
    template = load_template_registry(topology.paths).get(template_id)
    if template is None:
        raise DriverError(f"{component.qualified_id}: service template not found: {template_id or '<unset>'}")
    execution_user = component.execution_user or topology.hosts[component.host].user
    records: list[LogChannelRecord] = []
    for channel, raw_definition in sorted(template.logs.items()):
        definition = raw_definition if isinstance(raw_definition, dict) else {}
        path, provider = _template_log_path(
            topology, component, profile, channel, definition
        )
        error = ""
        if provider == "file" and not path:
            error = "log path is not configured"
        records.append(
            LogChannelRecord(
                component=component.qualified_id,
                channel=channel,
                host=component.host,
                execution_user=execution_user,
                path=path,
                provider=provider,
                error=error,
            )
        )
    return tuple(records)


def _resolve_log_channel(
    topology: Topology, component: Component, channel: str
) -> LogChannelRecord:
    records = resolve_log_channels(topology, component)
    for record in records:
        if record.channel == channel:
            if record.error:
                raise DriverError(
                    f"{component.qualified_id}: log channel {channel!r} is unavailable: {record.error}"
                )
            return record
    choices = ", ".join(item.channel for item in records) or "none"
    raise DriverError(
        f"{component.qualified_id}: log channel {channel!r} is unavailable; choose: {choices}"
    )


def _log_command(record: LogChannelRecord, *, lines: int, follow: bool = False) -> str:
    if lines < 1 or lines > 10_000:
        raise DriverError("log line count must be between 1 and 10000")
    if record.provider == "journalctl-user-unit":
        if not record.path:
            raise DriverError(f"{record.component}: systemd log unit is not configured")
        command = (
            f"journalctl --user -u {shlex.quote(record.path)} -n {lines} --no-pager"
        )
        return f"{command} -f" if follow else command
    if record.provider != "file":
        raise DriverError(
            f"{record.component}: unsupported log provider: {record.provider}"
        )
    follow_flag = " -F" if follow else ""
    return f"tail{follow_flag} -n {lines} {_shell_path(record.path)}"


def build_component_command(
    topology: Topology,
    component: Component,
    action: str,
    *,
    log_channel: str = "service",
    log_lines: int = 200,
) -> str:
    """Build a safe remote shell command for one typed component action."""

    if action not in {"start", "stop", "restart", "status", "logs"}:
        raise DriverError(f"unsupported component action: {action}")
    host = topology.hosts[component.host]
    profile = load_profile(topology.paths, component)
    if action == "logs":
        return _log_command(
            _resolve_log_channel(topology, component, log_channel),
            lines=log_lines,
        )
    if component.driver == "modelctl":
        binary = _managed_binary(host, "modelctl")
        return f"{binary} {shlex.quote(component.profile)} {shlex.quote(action)}"
    if component.driver in {"model-proxy", "tts-bridge"}:
        binary = _managed_binary(host, component.driver)
        return f"{binary} {shlex.quote(action)}"
    if component.driver == "agent":
        actions = _require_actions(profile, component)
        argv = actions.get(action)
        if argv is None:
            raise DriverError(
                f"{component.qualified_id}: agent profile does not define action: {action}"
            )
        return shlex.join(argv)
    if component.driver in {"launchd", "ssh-tunnel"}:
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
        target_user = component.execution_user or host.user
        effective_user = pwd.getpwuid(os.geteuid()).pw_name
        updates: dict[str, str] = {}
        if component.execution_user:
            updates["user"] = component.execution_user
        if host.transport == "local" and target_user != effective_user:
            updates["transport"] = "ssh"
        return replace(host, **updates) if updates else host

    def run(
        self,
        component: Component,
        action: str,
        *,
        log_channel: str = "service",
        log_lines: int = 200,
    ) -> CommandResult:
        """Run one component action and capture output."""

        script = build_component_command(
            self.topology,
            component,
            action,
            log_channel=log_channel,
            log_lines=log_lines,
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

    def logs(
        self,
        component: Component,
        *,
        channel: str = "service",
        lines: int = 200,
    ) -> CommandResult:
        """Return recent output for one named log channel."""

        return self.run(component, "logs", log_channel=channel, log_lines=lines)

    def list_logs(self, component: Component) -> tuple[LogChannelRecord, ...]:
        """Inspect every declared log channel on its configured host."""

        records: list[LogChannelRecord] = []
        host = self._host(component)
        for record in resolve_log_channels(self.topology, component):
            if record.error:
                records.append(record)
                continue
            if record.provider != "file":
                records.append(record)
                continue
            path = _shell_path(record.path)
            script = (
                f"if test -e {path}; then "
                "printf 'available=1\\n'; "
                f"if test -r {path}; then printf 'readable=1\\n'; else printf 'readable=0\\n'; fi; "
                f"size=$(wc -c < {path} | tr -d ' '); "
                f"modified=$(stat -c '%Y' {path} 2>/dev/null) || modified=$(stat -f '%m' {path} 2>/dev/null); "
                "printf 'size=%s\\nmodified_at=%s\\n' \"$size\" \"$modified\"; "
                "else printf 'available=0\\nreadable=0\\nsize=0\\nmodified_at=0\\n'; fi"
            )
            command = (
                ["/bin/sh", "-c", script]
                if host.transport == "local"
                else host.ssh_base() + [script]
            )
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=component.timeouts.logs,
                )
            except subprocess.TimeoutExpired:
                records.append(replace(record, error="log inspection timed out"))
                continue
            values = dict(
                line.split("=", 1)
                for line in completed.stdout.splitlines()
                if "=" in line
            )
            if completed.returncode != 0:
                records.append(
                    replace(record, error=completed.stderr.strip() or "log inspection failed")
                )
                continue
            records.append(
                replace(
                    record,
                    available=values.get("available") == "1",
                    readable=values.get("readable") == "1",
                    size=int(values["size"]) if values.get("size", "").isdigit() else None,
                    modified_at=(
                        int(values["modified_at"])
                        if values.get("modified_at", "").isdigit()
                        and values["modified_at"] != "0"
                        else None
                    ),
                )
            )
        return tuple(records)

    def follow_logs(
        self,
        component: Component,
        *,
        channel: str = "service",
        lines: int = 200,
    ) -> int:
        """Stream one declared log and cleanly reap the transport on interruption."""

        record = _resolve_log_channel(self.topology, component, channel)
        script = _log_command(record, lines=lines, follow=True)
        host = self._host(component)
        command = (
            ["/bin/sh", "-c", script]
            if host.transport == "local"
            else host.ssh_base() + [script]
        )
        process = subprocess.Popen(
            command,
            text=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
            start_new_session=True,
        )
        try:
            return process.wait()
        except KeyboardInterrupt:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            return 130

    def runtime_command(self, component: Component, result: CommandResult) -> Optional[CommandResult]:
        """Inspect elapsed time and command line for a live reported PID."""

        match = re.search(
            r"(?:^|\s)(?:pid\s*=|Main PID:)\s*(\d+)(?:\s|$)",
            result.stdout,
        )
        if match is None:
            return None
        host = self._host(component)
        script = f"ps -p {int(match.group(1))} -o etime= -o command="
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
        if component.driver in {"process", "command"}:
            pid_status = re.search(
                r"(?:^|\n)[^\n]*:\s+running\s+pid\s*=\s*(\d*)(?:\s|$)",
                output,
            )
            if pid_status is not None:
                return "running" if pid_status.group(1) else "stopped"
        if component.driver in {"model-proxy", "tts-bridge", "modelctl"}:
            if re.search(r"(^|\n)[^\n]*:\s+running(?:\s|$)", output):
                return "running"
            if re.search(r"(^|\n)[^\n]*:\s+(?:not running|stopped)(?:\s|$)", output):
                return "stopped"
        return "running" if result.ok else "stopped"

    def is_running(self, component: Component) -> bool:
        """Return lifecycle state without treating failed readiness as stopped."""

        return self.lifecycle_from_result(component, self.status(component)) == "running"

    def wait_stopped(self, component: Component) -> CommandResult:
        """Verify that a completed stop action left the component stopped."""

        result = self.status(component)
        lifecycle = self.lifecycle_from_result(component, result)
        if lifecycle == "stopped":
            return result
        if lifecycle == "unknown":
            raise DriverError(
                f"{component.qualified_id}: stop could not be verified: component is unreachable"
            )
        raise DriverError(
            f"{component.qualified_id}: stop command completed but component is still running"
        )

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
        if component.driver in {"model-proxy", "tts-bridge", "modelctl"} and not result.ok:
            health = "degraded"
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
