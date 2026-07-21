"""Transactional role-filtered configuration reconciliation."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Iterable

try:
    from .llmops_topology import Topology, TopologyError, write_host_snapshot
except ImportError:  # Direct source execution.
    from llmops_topology import Topology, TopologyError, write_host_snapshot


class ReconcileError(RuntimeError):
    """Raised when configuration cannot be reconciled safely."""


def snapshot_hash(root: Path) -> tuple[str, bool, list[str]]:
    """Return the declared snapshot hash and whether every file still matches."""

    manifest = root / "resolved.json"
    if not manifest.is_file():
        records = [
            {
                "path": str(path.relative_to(root)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in sorted(root.rglob("*.json"))
            if path.is_file() and path.name != "ui.json"
        ]
        if not records:
            raise ReconcileError(f"configuration contains no JSON documents: {root}")
        digest = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return digest, True, []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconcileError(f"invalid snapshot manifest {manifest}: {exc}") from exc
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list):
        raise ReconcileError(f"snapshot manifest has no file inventory: {manifest}")
    normalized: list[dict[str, str]] = []
    errors: list[str] = []
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
            raise ReconcileError(f"snapshot manifest contains an invalid file record: {manifest}")
        path = root / item["path"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"
        if actual != item["sha256"]:
            errors.append(f"{item['path']}: expected {item['sha256']}, observed {actual}")
        normalized.append({"path": item["path"], "sha256": item["sha256"]})
    digest = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return digest, not errors, errors


def _remote_command(host: Any, command: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    if host.transport == "local":
        argv = ["/bin/sh", "-c", command]
    else:
        argv = host.ssh_base() + [command]
    return subprocess.run(argv, capture_output=True, text=True, check=False, timeout=timeout)


def _remote_llmops(host: Any) -> str:
    root = host.public_bin_dir
    if root.startswith("~/"):
        return '"$HOME"/' + shlex.quote(root[2:] + "/llmops")
    return shlex.quote(str(Path(root) / "llmops"))


def remote_snapshot_status(host: Any) -> dict[str, Any]:
    """Read and verify the target's active configuration through its installed CLI."""

    completed = _remote_command(host, f"{_remote_llmops(host)} config hash --json")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "reachable": completed.returncode != 255,
            "ok": False,
            "error": completed.stderr.strip() or "remote config hash returned invalid JSON",
        }
    if not isinstance(payload, dict):
        return {"reachable": True, "ok": False, "error": "remote config hash returned invalid data"}
    payload["reachable"] = True
    return payload


def reconcile_plan(topology: Topology, host_names: Iterable[str]) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    """Build desired snapshots and compare them with verified remote state."""

    temporary = Path(tempfile.mkdtemp(prefix="llmops-reconcile-"))
    snapshots: dict[str, Path] = {}
    plan: list[dict[str, Any]] = []
    for name in host_names:
        host = topology.hosts.get(name)
        if host is None:
            raise ReconcileError(f"inventory host not found: {name}")
        snapshot = temporary / name
        write_host_snapshot(topology, host_name=name, destination=snapshot)
        desired, valid, errors = snapshot_hash(snapshot)
        if not valid:
            raise ReconcileError(f"generated snapshot failed verification: {'; '.join(errors)}")
        observed = remote_snapshot_status(host)
        error_text = str(observed.get("error", "")).lower()
        uninitialized = any(
            phrase in error_text
            for phrase in ("inventory not found", "configuration not found", "config.json not found")
        )
        if not observed.get("reachable", True):
            action = "unreachable"
        elif not observed.get("valid", True) and observed.get("config_hash"):
            action = "conflict"
        elif not observed.get("ok") and uninitialized:
            action = "apply"
        elif not observed.get("ok"):
            action = "error"
        elif observed.get("config_hash") == desired:
            action = "none"
        else:
            action = "apply"
        plan.append(
            {
                "host": name,
                "desired_hash": desired,
                "observed_hash": observed.get("config_hash", ""),
                "action": action,
                "reachable": observed.get("reachable", True),
                "error": observed.get("error", ""),
            }
        )
        snapshots[name] = snapshot
    return plan, snapshots


def apply_snapshot(host: Any, snapshot: Path, desired_hash: str) -> dict[str, Any]:
    """Copy, verify, and atomically select one configuration revision."""

    with tempfile.TemporaryDirectory(prefix="llmops-config-archive-") as temporary:
        archive = Path(temporary) / f"{desired_hash}.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            for path in sorted(snapshot.rglob("*")):
                if path.is_file():
                    bundle.add(path, arcname=path.relative_to(snapshot), recursive=False)
        remote_relative = f".cache/llm-ops/config/{archive.name}"
        if host.transport == "local":
            remote_archive = Path.home() / remote_relative
            remote_archive.parent.mkdir(parents=True, exist_ok=True)
            remote_archive.write_bytes(archive.read_bytes())
        else:
            mkdir = _remote_command(host, "mkdir -p \"$HOME/.cache/llm-ops/config\"")
            if mkdir.returncode != 0:
                raise ReconcileError(f"could not create remote config stage for {host.name}: {mkdir.stderr.strip()}")
            copied = subprocess.run(
                ["scp", "-P", str(host.port), "-o", "BatchMode=yes", str(archive), f"{host.destination}:{remote_relative}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if copied.returncode != 0:
                raise ReconcileError(f"could not transfer config snapshot to {host.name}: {copied.stderr.strip()}")
        root = host.install_root
        root_expr = '"$HOME"/' + shlex.quote(root[2:]) if root.startswith("~/") else shlex.quote(root)
        script = "; ".join(
            [
                "set -eu",
                f"root={root_expr}",
                f"archive=\"$HOME/{remote_relative}\"",
                f"revision=\"$root/config-revisions/{desired_hash}\"",
                'if test ! -e "$revision"; then mkdir -p "$revision"; tar -xzf "$archive" -C "$revision"; fi',
                f"observed=$(LLMOPS_CONFIG_HOME=\"$revision\" {_remote_llmops(host)} config hash | awk -F= '$1 == \"config_hash\" {{print $2}}')",
                f"test \"$observed\" = {shlex.quote(desired_hash)}",
                'if test -L "$root/current-config"; then old=$(readlink "$root/current-config"); ln -s "$old" "$root/.previous-config.$$"; if ! mv -fh "$root/.previous-config.$$" "$root/previous-config" 2>/dev/null; then rm -f "$root/previous-config"; mv -f "$root/.previous-config.$$" "$root/previous-config"; fi; fi',
                'ln -s "$revision" "$root/.current-config.$$"',
                'if ! mv -fh "$root/.current-config.$$" "$root/current-config" 2>/dev/null; then rm -f "$root/current-config"; mv -f "$root/.current-config.$$" "$root/current-config"; fi',
                f"printf '%s\\n' {shlex.quote(desired_hash)} > \"$root/config-revisions/.last-sync\"",
            ]
        )
        completed = _remote_command(host, script)
        if completed.returncode != 0:
            raise ReconcileError(f"configuration apply failed for {host.name}: {completed.stderr.strip() or completed.stdout.strip()}")
    return {"host": host.name, "ok": True, "config_hash": desired_hash}
