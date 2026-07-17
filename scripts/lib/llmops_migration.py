#!/usr/bin/env python3
"""One-way classified migration from proof-of-concept configuration."""

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
    from llmops_init import sanitize_secret_references
    from llmops_paths import LlmOpsPaths
except ModuleNotFoundError:  # pragma: no cover
    from .llmops_config import default_config
    from .llmops_init import sanitize_secret_references
    from .llmops_paths import LlmOpsPaths


class MigrationError(RuntimeError):
    """Raised when a one-way migration cannot complete safely."""


VARIABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_VALUE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*):-([^}]*)\}$")
SERVICES = {"model-proxy", "model_proxy", "tts-bridge", "tts_bridge"}


@dataclass(frozen=True)
class MigrationResult:
    source_hash: str
    written: tuple[Path, ...]
    unchanged: bool
    mappings: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]
    skipped: tuple[str, ...]


def _assignment_value(raw: str, known: dict[str, str]) -> str:
    try:
        tokens = shlex.split(raw.strip(), comments=True, posix=True)
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
    candidates = [legacy_home / "config.env"]
    candidates.extend(sorted((legacy_home / "config").glob("*.env")))
    candidates.extend(sorted((legacy_home / "config").glob("*.sh")))
    candidates.extend(sorted((legacy_home / "config" / "agents").glob("*.env")))
    for name in ("inventory.json", "inventory.yml", "inventory.yaml"):
        candidates.append(legacy_home / name)
    return [path for path in candidates if path.is_file()]


def source_hash(files: list[Path], legacy_home: Path) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(legacy_home)).encode("utf-8"))
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


def _classify(path: Path, values: dict[str, str]) -> Optional[str]:
    if path.parent.name == "agents":
        return "agent"
    stem = path.stem.lower()
    if stem in SERVICES or any(key.startswith(("MODEL_PROXY_", "TTS_BRIDGE_", "LLMOPS_UPSTREAM_")) for key in values):
        return "service"
    if "MODEL" in values or "MODEL_TYPE" in values or "TTS_SERVER_MODULE" in values:
        return "model"
    return None


def _documents(legacy_home: Path, paths: LlmOpsPaths, digest: str) -> tuple[dict[Path, dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    files = source_files(legacy_home)
    global_values = parse_assignments(legacy_home / "config.env")
    config = default_config()
    config["migration"] = {"version": 1, "source_hash": digest}
    documents: dict[Path, dict[str, Any]] = {paths.config_file: config}
    mappings: list[dict[str, Any]] = []
    warnings: list[str] = []
    skipped: list[str] = []

    for path in files:
        if path == legacy_home / "config.env" or path.name.startswith("inventory."):
            continue
        values = {**global_values, **parse_assignments(path)}
        kind = _classify(path, values)
        if kind is None:
            skipped.append(str(path))
            warnings.append(f"unclassified legacy input: {path}")
            continue
        payload: dict[str, Any]
        if kind == "model":
            model_type = values.get("MODEL_TYPE", "tts" if "TTS_SERVER_MODULE" in values else "llm").lower()
            payload = {"schema_version": 1, "name": path.stem, "type": model_type, "environment": values}
            destination = paths.models_dir / f"{path.stem}.json"
        elif kind == "service":
            service_name = "tts-bridge" if "tts" in path.stem.lower() or any(key.startswith("TTS_BRIDGE_") for key in values) else "model-proxy"
            payload = {"schema_version": 1, "name": service_name, "environment": values}
            destination = paths.services_dir / f"{service_name}.json"
        else:
            payload = {"schema_version": 1, "name": path.stem, "enabled": False, "environment": values, "actions": {}}
            destination = paths.agents_dir / f"{path.stem}.json"
            warnings.append(f"agent lifecycle actions require review: {path}")
        if destination in documents:
            skipped.append(str(path))
            warnings.append(f"multiple legacy inputs map to {destination}: {path}")
            continue
        payload, converted = sanitize_secret_references(payload)
        documents[destination] = payload
        mappings.append({"source": str(path), "destination": str(destination), "kind": kind, "converted_secret_fields": list(converted)})

    inventory = next((path for path in files if path.name in {"inventory.json", "inventory.yml", "inventory.yaml"}), None)
    if inventory is not None:
        documents[paths.inventory_file] = _json_inventory(inventory) if inventory.suffix == ".json" else _simple_yaml_inventory(inventory)
        mappings.append({"source": str(inventory), "destination": str(paths.inventory_file), "kind": "inventory", "converted_secret_fields": []})
    return documents, mappings, warnings, skipped


def migrate(legacy_home: Path, paths: LlmOpsPaths, *, dry_run: bool = False, force: bool = False, allow_partial: bool = False) -> MigrationResult:
    """Migrate once without executing or retaining legacy runtime inputs."""

    legacy_home = legacy_home.expanduser().resolve()
    files = source_files(legacy_home)
    if not files:
        raise MigrationError(f"no proof-of-concept configuration found under: {legacy_home}")
    digest = source_hash(files, legacy_home)
    marker = paths.config_home / ".migration-v1.json"
    if marker.is_file():
        existing = json.loads(marker.read_text(encoding="utf-8"))
        if existing.get("source_hash") == digest:
            return MigrationResult(digest, tuple(), True, tuple(), tuple(), tuple())
        if not force:
            raise MigrationError("migration source changed; rerun with --force after reviewing the diff")
    documents, mappings, warnings, skipped = _documents(legacy_home, paths, digest)
    if skipped and not allow_partial and not dry_run:
        raise MigrationError("migration found unclassified inputs; review the dry-run and rerun with --allow-partial: " + ", ".join(skipped))
    documents[marker] = {"schema_version": 1, "source_hash": digest}
    conflicts = [path for path in documents if path.exists()]
    if conflicts and not force:
        raise MigrationError("destination exists; use --force after backup: " + ", ".join(map(str, conflicts)))
    if dry_run:
        return MigrationResult(digest, tuple(sorted(documents)), False, tuple(mappings), tuple(warnings), tuple(skipped))
    temporary: list[tuple[Path, Path]] = []
    try:
        for path, payload in sorted(documents.items()):
            path.parent.mkdir(parents=True, exist_ok=True)
            candidate = path.with_name(f".{path.name}.migration-tmp")
            candidate.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temporary.append((candidate, path))
        for candidate, path in temporary:
            candidate.replace(path)
    finally:
        for candidate, _ in temporary:
            candidate.unlink(missing_ok=True)
    return MigrationResult(digest, tuple(path for _, path in temporary), False, tuple(mappings), tuple(warnings), tuple(skipped))
