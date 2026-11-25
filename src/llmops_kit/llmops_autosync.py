"""Run an explicitly enrolled authority's synchronization helper."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any


_START_LOCK = threading.Lock()


def _install_root() -> Path | None:
    release = Path(sys.executable).absolute().parents[2].resolve()
    return release.parent.parent if release.parent.name == "releases" else None


def _read_private(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_nlink != 1:
            raise ValueError("owner-private synchronization file required")
        result = stream.read(64 * 1024 + 1)
        if len(result) > 64 * 1024:
            raise ValueError("synchronization file too large")
        return result


def _run(phase: str, component: str | None = None) -> None:
    if os.geteuid() == 0 or os.environ.get("LLMOPS_AUTOSYNC_ACTIVE") == "1":
        return
    root = _install_root()
    if root is None:
        return
    approval = root / "auto-sync.json"
    if not approval.exists() and not approval.is_symlink():
        return
    try:
        enrolled = json.loads(_read_private(approval))
        if not isinstance(enrolled, dict) or set(enrolled) != {"schema_version", "program_sha256"} or enrolled["schema_version"] != 1:
            raise ValueError("invalid synchronization enrollment")
        program = _read_private(root / "auto-sync.py")
        if hashlib.sha256(program).hexdigest() != enrolled["program_sha256"]:
            raise ValueError("synchronization helper changed")
        # Execute the exact bytes verified here. Never pass caller commands or configuration paths.
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-", phase, *([component] if component else [])],
            input=program, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=root,
            timeout=150 if phase == "sync" else 25,
            env={**os.environ, "LLMOPS_AUTOSYNC_ACTIVE": "1", "LLMOPS_AUTO_UPDATE_ACTIVE": "1"},
            check=False,
        )
        if result.returncode:
            print("llmops: automatic synchronization could not finish safely; continuing without forcing changes.", file=sys.stderr)
        elif result.stdout:
            print(result.stdout.decode("utf-8", errors="replace").rstrip(), file=sys.stderr)
    except (OSError, ValueError, subprocess.SubprocessError):
        print("llmops: automatic synchronization is unavailable; check the authority's enrollment.", file=sys.stderr)


def sync_for_command(args: Any) -> None:
    """Leave previews, explicit overrides, and release-management commands outside the hook."""
    if any(getattr(args, flag, None) for flag in ("config_home", "inventory", "local", "status_host", "plan")):
        return
    command = getattr(args, "command", "")
    subcommand = getattr(args, f"{command}_command", "")
    if command == "status" or (command in {"stack", "component"} and subcommand in {"status", "start", "stop", "restart"}):
        args.autosync_lifecycle = True
        _run("sync")


def sync_before_start(component_id: str) -> None:
    """Give the authority a chance to prepare a selected stopped proxy job."""
    if component_id.endswith((":model-proxy", ":external-model-proxy")):
        # Parallel starts must not launch another member of a proxy pair while
        # the first member's reviewed binding transaction is in progress.
        with _START_LOCK:
            _run("before-start", component_id)
