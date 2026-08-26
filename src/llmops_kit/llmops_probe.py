#!/usr/bin/env python
"""Read-only host and runtime probes for guided operation."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

try:
    from llmops_profiles import model_values, service_values
    from llmops_topology import Topology, load_profile
except ModuleNotFoundError:  # pragma: no cover
    from .llmops_profiles import model_values, service_values
    from .llmops_topology import Topology, load_profile


def _command(topology: Topology, host_name: str, script: str) -> list[str]:
    host = topology.hosts[host_name]
    return ["/bin/sh", "-c", script] if host.transport == "local" else host.ssh_base() + [script]


def _run(topology: Topology, host_name: str, script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(_command(topology, host_name, script), capture_output=True, text=True, check=False, timeout=15)


def _item(host: str, check: str, status: str, detail: str, correction: str = "") -> dict[str, str]:
    return {"host": host, "check": check, "status": status, "detail": detail, "correction": correction}


def _path_check(topology: Topology, host_name: str, label: str, path: str, *, enabled: bool) -> dict[str, str]:
    if path.startswith(("env:", "seckit:")):
        return _item(host_name, label, "ok", f"provider reference: {path}")
    if path.startswith("~/"):
        expanded = '"$HOME"/' + shlex.quote(path[2:])
    elif path.startswith("$HOME/"):
        expanded = '"$HOME"/' + shlex.quote(path[6:])
    elif path.startswith("${HOME}/"):
        expanded = '"$HOME"/' + shlex.quote(path[8:])
    else:
        expanded = shlex.quote(path)
    completed = _run(topology, host_name, f"test -e {expanded}")
    if completed.returncode == 0:
        return _item(host_name, label, "ok", path)
    status = "error" if enabled else "warning"
    return _item(host_name, label, status, f"not found: {path}", f"correct the referenced path for host {host_name}")


def _executable_check(topology: Topology, host_name: str, label: str, executable: str, *, enabled: bool) -> dict[str, str]:
    if "/" in executable or executable.startswith(("~", "$", "env:", "seckit:")):
        return _path_check(topology, host_name, label, executable, enabled=enabled)
    completed = _run(topology, host_name, f"command -v {shlex.quote(executable)}")
    if completed.returncode == 0:
        return _item(host_name, label, "ok", completed.stdout.strip())
    status = "error" if enabled else "warning"
    return _item(host_name, label, status, f"not found in PATH: {executable}", f"install the executable or configure an explicit path for host {host_name}")


def _port_check(topology: Topology, host_name: str, label: str, host: str, port: str, *, enabled: bool) -> dict[str, str]:
    completed = _run(topology, host_name, f"nc -z -w 1 {shlex.quote(host)} {int(port)}")
    occupied = completed.returncode == 0
    if occupied and not enabled:
        return _item(host_name, label, "warning", f"{host}:{port} is already accepting connections", "select another port or identify the existing listener before enabling the component")
    return _item(host_name, label, "ok", f"{host}:{port} is {'occupied' if occupied else 'available'}")


def probe_topology(topology: Topology) -> dict[str, Any]:
    """Probe configured hosts without changing services or configuration."""

    checks: list[dict[str, str]] = []
    for host_name in sorted(topology.hosts):
        install_root = topology.hosts[host_name].install_root
        if install_root.startswith("~/"):
            app_python = '"$HOME"/' + shlex.quote(install_root[2:] + "/current/app/bin/python")
        else:
            app_python = shlex.quote(str(Path(install_root) / "current" / "app" / "bin" / "python"))
        baseline = _run(
            topology,
            host_name,
            "printf 'arch='; uname -m; "
            f"printf 'app_python='; test -x {app_python} && {app_python} --version 2>&1 || true; "
            "printf '\\nbash='; command -v bash || true; "
            "printf 'launchctl='; command -v launchctl || true; "
            "printf 'memory='; sysctl -n hw.memsize 2>/dev/null || true",
        )
        if baseline.returncode != 0:
            checks.append(_item(host_name, "connectivity", "error", baseline.stderr.strip() or "host probe failed", "verify inventory transport, SSH user, key, and host reachability"))
            continue
        values = dict(line.split("=", 1) for line in baseline.stdout.splitlines() if "=" in line)
        checks.append(_item(host_name, "connectivity", "ok", "reachable"))
        arch = values.get("arch", "unknown")
        supported_arch = arch in {"arm64", "x86_64"}
        checks.append(_item(host_name, "architecture", "ok" if supported_arch else "error", arch, "use a supported macOS arm64 or x86_64 host" if not supported_arch else ""))
        app_python_version = values.get("app_python", "")
        has_enabled = any(component.host == host_name and component.enabled for component in topology.all_components())
        python_status = "ok" if app_python_version.startswith("Python 3.") else "error" if has_enabled else "warning"
        checks.append(_item(host_name, "application-python", python_status, app_python_version or "not found", "repair or reinstall the LLM-Ops-Kit application runtime" if not app_python_version else ""))
        bash = values.get("bash", "")
        checks.append(_item(host_name, "gnu-bash", "ok" if bash else "error", bash or "not found", "install GNU Bash and make it available in PATH" if not bash else ""))
        needs_launchd = any(component.host == host_name and component.driver in {"launchd", "ssh-tunnel"} for component in topology.all_components())
        launchctl = values.get("launchctl", "")
        if needs_launchd:
            checks.append(_item(host_name, "launchctl", "ok" if launchctl else "error", launchctl or "not found", "launchd-managed components require launchctl on macOS" if not launchctl else ""))
        checks.append(_item(host_name, "memory-bytes", "ok", values.get("memory", "unknown")))

    for component in topology.all_components():
        if component.host not in topology.hosts:
            continue
        profile = load_profile(topology.paths, component)
        if component.driver == "modelctl":
            values = model_values(profile)
            model_path = values.get("MODEL")
            if model_path:
                checks.append(_path_check(topology, component.host, f"{component.qualified_id}:model", model_path, enabled=component.enabled))
            python_path = values.get("TTS_PYTHON_BIN")
            if python_path:
                checks.append(_executable_check(topology, component.host, f"{component.qualified_id}:python", python_path, enabled=component.enabled))
            if values.get("HOST") and values.get("PORT", "").isdigit():
                checks.append(_port_check(topology, component.host, f"{component.qualified_id}:port", values["HOST"], values["PORT"], enabled=component.enabled))
        elif component.driver in {"model-proxy", "tts-bridge"}:
            values = service_values(component.driver, profile)
            python_key = "MODEL_PROXY_PYTHON_BIN" if component.driver == "model-proxy" else "TTS_BRIDGE_PYTHON_BIN"
            if values.get(python_key):
                checks.append(_executable_check(topology, component.host, f"{component.qualified_id}:python", values[python_key], enabled=component.enabled))
            port = values.get("MODEL_PROXY_LISTEN_PORT" if component.driver == "model-proxy" else "TTS_BRIDGE_PORT")
            listen_host = values.get("MODEL_PROXY_LISTEN_HOST" if component.driver == "model-proxy" else "TTS_BRIDGE_HOST", "127.0.0.1")
            if port and port.isdigit():
                checks.append(_port_check(topology, component.host, f"{component.qualified_id}:port", listen_host, port, enabled=component.enabled))
        elif component.driver in {"agent", "process", "command"}:
            actions = profile.get("actions", {})
            start = actions.get("start") if isinstance(actions, dict) else None
            if isinstance(start, list) and start and str(start[0]).startswith(("/", "~/")):
                checks.append(_path_check(topology, component.host, f"{component.qualified_id}:executable", str(start[0]), enabled=component.enabled))

    return {"ok": not any(item["status"] == "error" for item in checks), "checks": checks}
