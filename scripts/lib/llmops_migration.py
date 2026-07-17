#!/usr/bin/env python3
"""One-way migration from the proof-of-concept shell configuration."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    from llmops_config import default_config
    from llmops_paths import LlmOpsPaths
except ModuleNotFoundError:  # pragma: no cover
    from .llmops_config import default_config
    from .llmops_paths import LlmOpsPaths


class MigrationError(RuntimeError):
    """Raised when a one-way migration cannot complete safely."""


VARIABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_VALUE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*):-([^}]*)\}$")


@dataclass(frozen=True)
class MigrationResult:
    """Summary of a migration or idempotent no-op."""

    source_hash: str
    written: tuple[Path, ...]
    unchanged: bool


def _assignment_value(raw: str, known: dict[str, str]) -> str:
    value = raw.strip()
    try:
        tokens = shlex.split(value, comments=True, posix=True)
    except ValueError:
        return ""
    if len(tokens) != 1:
        return ""
    value = tokens[0]
    match = DEFAULT_VALUE.fullmatch(value)
    if match:
        return known.get(match.group(1), match.group(2))
    for key, replacement in known.items():
        value = value.replace(f"${{{key}}}", replacement).replace(f"${key}", replacement)
    return value


def parse_assignments(path: Path) -> dict[str, str]:
    """Parse scalar shell assignments without executing the source file."""

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        if not VARIABLE.fullmatch(key) or raw_value.lstrip().startswith("("):
            continue
        value = _assignment_value(raw_value, values)
        if value:
            values[key] = value
    return values


def source_files(legacy_home: Path) -> list[Path]:
    """Return deterministic legacy inputs from the explicitly selected home."""

    candidates = [legacy_home / "config.env"]
    candidates.extend(sorted((legacy_home / "config").glob("*.env")))
    candidates.extend(sorted((legacy_home / "config").glob("*.sh")))
    candidates.extend(sorted((legacy_home / "config" / "agents").glob("*.env")))
    for name in ("inventory.json", "inventory.yml", "inventory.yaml"):
        candidates.append(legacy_home / name)
    return [path for path in candidates if path.is_file()]


def source_hash(files: list[Path]) -> str:
    """Hash source names and bytes so repeated migration is deterministic."""

    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _json_inventory(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise MigrationError(f"legacy inventory must be an object: {path}")
    raw["schema_version"] = 1
    return raw


def _yaml_scalar(raw: str) -> Any:
    value = raw.strip().strip("\"'")
    if value.startswith("[") and value.endswith("]"):
        return [item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip()]
    try:
        return int(value)
    except ValueError:
        return value


def _simple_yaml_inventory(path: Path) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    hosts: list[dict[str, Any]] = []
    section = ""
    current: Optional[dict[str, Any]] = None
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line == "defaults:":
            section = "defaults"
            continue
        if line == "hosts:":
            section = "hosts"
            continue
        stripped = line.strip()
        if section == "defaults" and line.startswith("  ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            defaults[key] = _yaml_scalar(value)
            continue
        if section == "hosts" and line.startswith("  - "):
            current = {}
            hosts.append(current)
            remainder = stripped[2:].strip()
            if remainder:
                key, value = remainder.split(":", 1)
                current[key] = _yaml_scalar(value)
            continue
        if section == "hosts" and line.startswith("    ") and current is not None:
            key, value = stripped.split(":", 1)
            current[key] = _yaml_scalar(value)
            continue
        raise MigrationError(f"{path}:{number}: unsupported legacy inventory syntax")
    return {"schema_version": 1, "defaults": defaults, "hosts": hosts}


def _documents(legacy_home: Path, paths: LlmOpsPaths, digest: str) -> dict[Path, dict[str, Any]]:
    files = source_files(legacy_home)
    global_values = parse_assignments(legacy_home / "config.env")
    config = default_config()
    config["migration"] = {
        "version": 1,
        "source_home": str(legacy_home),
        "source_hash": digest,
        "sources": [str(path) for path in files],
    }
    documents: dict[Path, dict[str, Any]] = {paths.config_file: config}
    for path in sorted((legacy_home / "config").glob("*")):
        if not path.is_file() or path.suffix not in {".env", ".sh"}:
            continue
        values = {**global_values, **parse_assignments(path)}
        documents[paths.models_dir / f"{path.stem}.json"] = {
            "schema_version": 1,
            "name": path.stem,
            "environment": values,
            "migrated_from": str(path),
        }
    for path in sorted((legacy_home / "config" / "agents").glob("*.env")):
        documents[paths.agents_dir / f"{path.stem}.json"] = {
            "schema_version": 1,
            "name": path.stem,
            "environment": {**global_values, **parse_assignments(path)},
            "actions": {},
            "migrated_from": str(path),
        }
    inventory = next(
        (path for path in files if path.name in {"inventory.json", "inventory.yml", "inventory.yaml"}),
        None,
    )
    if inventory is not None:
        documents[paths.inventory_file] = (
            _json_inventory(inventory) if inventory.suffix == ".json" else _simple_yaml_inventory(inventory)
        )
    return documents


def migrate(
    legacy_home: Path,
    paths: LlmOpsPaths,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> MigrationResult:
    """Migrate once, refusing implicit overwrite and never reading legacy data at runtime."""

    legacy_home = legacy_home.expanduser().resolve()
    files = source_files(legacy_home)
    if not files:
        raise MigrationError(f"no proof-of-concept configuration found under: {legacy_home}")
    digest = source_hash(files)
    marker = paths.config_home / ".migration-v1.json"
    if marker.is_file():
        existing = json.loads(marker.read_text(encoding="utf-8"))
        if existing.get("source_hash") == digest:
            return MigrationResult(digest, tuple(), True)
        if not force:
            raise MigrationError("migration source changed; rerun with --force after reviewing the diff")
    documents = _documents(legacy_home, paths, digest)
    conflicts = [path for path in documents if path.exists()]
    if conflicts and not force:
        raise MigrationError("destination exists; use --force after backup: " + ", ".join(map(str, conflicts)))
    if dry_run:
        return MigrationResult(digest, tuple(sorted(documents)), False)
    written: list[Path] = []
    for path, payload in sorted(documents.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)
        written.append(path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {"schema_version": 1, "source_home": str(legacy_home), "source_hash": digest},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(marker)
    return MigrationResult(digest, tuple(written), False)
