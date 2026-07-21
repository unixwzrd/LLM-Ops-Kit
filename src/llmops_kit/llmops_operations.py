"""Persistent detached operation records for long-running control actions."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from .llmops_paths import LlmOpsPaths


ACTIVE_STATES = {"queued", "running"}


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load_record(path: Path) -> dict[str, Any]:
    """Load one operation record."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"invalid operation record: {path}")
    return raw


def list_records(paths: LlmOpsPaths, *, limit: int = 50) -> list[dict[str, Any]]:
    """Return operation records newest first."""

    if not paths.operations_dir.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(paths.operations_dir.glob("*.json"), reverse=True):
        try:
            records.append(load_record(path))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if len(records) >= limit:
            break
    return records


def record_path(paths: LlmOpsPaths, operation_id: str) -> Path:
    """Resolve a validated operation record path."""

    if re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}", operation_id) is None:
        raise ValueError(f"invalid operation ID: {operation_id}")
    return paths.operations_dir / f"{operation_id}.json"


def dispatch(
    paths: LlmOpsPaths,
    *,
    argv: list[str],
    action: str,
    target: str,
    command: str,
    plan: list[dict[str, Any]],
    host: str = "",
) -> dict[str, Any]:
    """Persist and launch one detached short-lived worker."""

    operation_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:12]}"
    path = record_path(paths, operation_id)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "operation_id": operation_id,
        "state": "queued",
        "action": action,
        "target": target,
        "host": host,
        "command": command,
        "argv": argv,
        "plan": plan,
        "created_at": _timestamp(),
        "started_at": "",
        "finished_at": "",
        "returncode": None,
        "output_summary": "",
        "error": "",
        "result": {},
        "stdout": "",
        "stderr": "",
    }
    _write(path, payload)
    subprocess.Popen(
        [sys.executable, "-m", "llmops_kit.llmops_operation_worker", str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    return payload


def update_record(path: Path, **changes: Any) -> dict[str, Any]:
    """Transactionally update one operation record."""

    payload = load_record(path)
    payload.update(changes)
    _write(path, payload)
    return payload
