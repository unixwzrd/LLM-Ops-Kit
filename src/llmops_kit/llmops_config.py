#!/usr/bin/env python
"""JSON configuration loading for LLM-Ops-Kit."""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from llmops_paths import LlmOpsPaths, resolve_paths
except ModuleNotFoundError:  # pragma: no cover - direct source execution
    from .llmops_paths import LlmOpsPaths, resolve_paths


SUPPORTED_SCHEMA_VERSION = 1
OBJECT_SECTIONS = {
    "runtime",
    "models",
    "agents",
    "profiles",
    "services",
    "deployment",
    "secrets",
    "display",
}


class ConfigError(ValueError):
    """Raised when JSON configuration is missing required structure."""


@dataclass(frozen=True)
class LlmOpsConfig:
    """Loaded config.json data and metadata."""

    path: Path
    data: dict[str, Any]
    exists: bool

    @property
    def schema_version(self) -> int:
        raw = self.data.get("schema_version", SUPPORTED_SCHEMA_VERSION)
        return int(raw)


def default_config() -> dict[str, Any]:
    """Return the minimum valid v1 config document."""

    return {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "runtime": {},
        "models": {},
        "agents": {},
        "profiles": {},
        "services": {},
        "deployment": {},
        "display": {},
        "secrets": {
            "provider": "env",
        },
    }


def validate_config(data: dict[str, Any]) -> None:
    """Validate the minimum shape of config.json."""

    raw_version = data.get("schema_version", SUPPORTED_SCHEMA_VERSION)
    if not isinstance(raw_version, int):
        raise ConfigError("schema_version must be an integer")
    if raw_version != SUPPORTED_SCHEMA_VERSION:
        raise ConfigError(f"unsupported schema_version: {raw_version}")
    for section in OBJECT_SECTIONS:
        if section in data and not isinstance(data[section], dict):
            raise ConfigError(f"{section} must be a JSON object")
    secrets = data.get("secrets", {})
    provider = secrets.get("provider", "env") if isinstance(secrets, dict) else "env"
    if provider not in {"env", "none", "seckit"}:
        raise ConfigError(f"unsupported secrets.provider: {provider}")
    display = data.get("display", {})
    for field in ("organization", "site"):
        value = display.get(field, "") if isinstance(display, dict) else ""
        if not isinstance(value, str):
            raise ConfigError(f"display.{field} must be a string")


def load_config(path: Path | None = None, *, paths: LlmOpsPaths | None = None) -> LlmOpsConfig:
    """Load config.json, returning defaults when the file does not exist."""

    resolved_paths = paths or resolve_paths()
    config_path = path or resolved_paths.config_file
    if not config_path.exists():
        data = default_config()
        validate_config(data)
        return LlmOpsConfig(path=config_path, data=data, exists=False)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{config_path}: invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path}: top-level config must be a JSON object")
    data = {**default_config(), **raw}
    validate_config(data)
    return LlmOpsConfig(path=config_path, data=data, exists=True)


def update_display(path: Path, *, organization: str, site: str) -> Path:
    """Transactionally update shared display metadata and preserve a backup."""

    loaded = load_config(path)
    data = dict(loaded.data)
    data["display"] = {"organization": organization.strip(), "site": site.strip()}
    validate_config(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(f"{path.name}.backup-{time.strftime('%Y%m%dT%H%M%S')}")
    if path.exists():
        shutil.copy2(path, backup)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return backup
