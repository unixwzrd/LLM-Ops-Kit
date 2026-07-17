#!/usr/bin/env python3
"""Transactional guided initialization for LLM-Ops-Kit."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    from llmops_paths import LlmOpsPaths
except ModuleNotFoundError:  # pragma: no cover
    from .llmops_paths import LlmOpsPaths


class InitError(RuntimeError):
    """Raised when starter configuration cannot be created safely."""


PROFILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SECRET_FIELD = re.compile(r"(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE)
MODEL_TYPES = {"llm", "embedding", "tts"}


@dataclass(frozen=True)
class ModelCandidate:
    name: str
    model_type: str
    source: Path
    profile: dict[str, Any]
    converted_secrets: tuple[str, ...]


@dataclass(frozen=True)
class InitResult:
    created: tuple[Path, ...]
    imported_models: tuple[str, ...]
    converted_secrets: tuple[str, ...]


def _secret_reference(key: str, value: Any) -> tuple[Any, bool]:
    if not SECRET_FIELD.search(key) or value in (None, ""):
        return value, False
    if isinstance(value, str) and value.startswith(("env:", "seckit:")):
        return value, False
    return f"env:{key.upper()}", True


def _sanitize_secrets(value: Any, prefix: str = "") -> tuple[Any, list[str]]:
    converted: list[str] = []
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            field = f"{prefix}.{key}" if prefix else key
            replacement, changed = _secret_reference(key, item)
            if changed:
                result[key] = replacement
                converted.append(field)
            else:
                result[key], nested = _sanitize_secrets(item, field)
                converted.extend(nested)
        return result, converted
    if isinstance(value, list):
        result = []
        for index, item in enumerate(value):
            normalized, nested = _sanitize_secrets(item, f"{prefix}[{index}]")
            result.append(normalized)
            converted.extend(nested)
        return result, converted
    return value, converted


def sanitize_secret_references(value: Any) -> tuple[Any, tuple[str, ...]]:
    """Replace literal secret fields with provider references."""

    normalized, converted = _sanitize_secrets(value)
    return normalized, tuple(converted)


def _normalize_model(path: Path) -> ModelCandidate:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InitError(f"cannot read model profile {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise InitError(f"model profile must be an object: {path}")
    if raw.get("schema_version", 1) != 1:
        raise InitError(f"unsupported model profile schema in {path}: {raw.get('schema_version')}")
    name = str(raw.get("name") or path.stem)
    if not PROFILE_NAME.fullmatch(name):
        raise InitError(f"invalid model profile name in {path}: {name!r}")
    explicit = raw.get("environment", raw.get("env"))
    model_type = str(raw.get("type") or raw.get("model_type") or "")
    if not model_type and isinstance(explicit, dict):
        model_type = str(explicit.get("MODEL_TYPE", "llm"))
    model_type = model_type.lower()
    if model_type not in MODEL_TYPES:
        raise InitError(f"unsupported model type in {path}: {model_type!r}")

    normalized = dict(raw)
    normalized.pop("env", None)
    normalized.pop("sources", None)
    normalized["schema_version"] = 1
    normalized["name"] = name
    normalized["type"] = model_type
    if explicit is not None:
        if not isinstance(explicit, dict):
            raise InitError(f"model environment must be an object: {path}")
        normalized["environment"] = dict(explicit)
        normalized["environment"].setdefault("MODEL_PROFILE", name)
        normalized["environment"].setdefault("MODEL_TYPE", model_type)
    normalized, converted = _sanitize_secrets(normalized)

    environment = normalized.get("environment", {})
    model_path = environment.get("MODEL") if isinstance(environment, dict) else normalized.get("model_path")
    if model_path not in (None, "") and not str(model_path).startswith(("/", "~", "env:", "seckit:")):
        raise InitError(f"model path must be absolute or a provider reference in {path}: {model_path}")
    if isinstance(environment, dict):
        for key, value in environment.items():
            if key.endswith("PYTHON_BIN") and value and not str(value).startswith(("/", "~", "env:", "seckit:")):
                raise InitError(f"{key} must be an absolute path or provider reference in {path}")
    normalized["import"] = {"source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return ModelCandidate(name, model_type, path, normalized, tuple(converted))


def discover_model_profiles(config_root: Path) -> dict[str, ModelCandidate]:
    """Return validated model profiles available for optional import."""

    models = config_root.expanduser() / "models"
    candidates: dict[str, ModelCandidate] = {}
    if not models.is_dir():
        return candidates
    for path in sorted(models.glob("*.json")):
        candidate = _normalize_model(path)
        if candidate.name in candidates:
            raise InitError(f"duplicate model profile name: {candidate.name}")
        candidates[candidate.name] = candidate
    return candidates


def _write_documents(config_home: Path, documents: dict[Path, dict[str, Any]], *, force: bool) -> None:
    config_home.parent.mkdir(parents=True, exist_ok=True)
    conflicts = [path for path in documents if path.exists()]
    if conflicts and not force:
        raise InitError("refusing to overwrite existing configuration: " + ", ".join(map(str, conflicts)))
    staging = Path(tempfile.mkdtemp(prefix=".llm-ops-init-", dir=config_home.parent))
    backup: Optional[Path] = None
    try:
        if config_home.exists():
            shutil.copytree(config_home, staging, dirs_exist_ok=True)
        for destination, payload in documents.items():
            relative = destination.relative_to(config_home)
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if config_home.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{config_home.name}.backup-", dir=config_home.parent))
            backup.rmdir()
            config_home.replace(backup)
        staging.replace(config_home)
        if backup is not None:
            shutil.rmtree(backup)
    except Exception:
        if config_home.exists() and backup is not None:
            shutil.rmtree(config_home)
        if backup is not None and backup.exists():
            backup.replace(config_home)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def initialize(
    paths: LlmOpsPaths,
    *,
    preset: str,
    force: bool = False,
    user: str,
    model_host: str = "model-host.local",
    agent_host: str = "agent-host.local",
    model_candidates: Optional[dict[str, ModelCandidate]] = None,
    import_models: Iterable[str] = (),
    default_chat: Optional[str] = None,
    default_embedding: Optional[str] = None,
    default_tts: Optional[str] = None,
) -> InitResult:
    """Write a disabled starter topology and selected normalized model profiles."""

    if preset not in {"single-host", "local-lan"}:
        raise InitError(f"unsupported preset: {preset}")
    candidates = model_candidates or {}
    selected_names = tuple(dict.fromkeys(import_models))
    missing = [name for name in selected_names if name not in candidates]
    if missing:
        raise InitError("selected model profile not found: " + ", ".join(missing))
    defaults = {"llm": default_chat, "embedding": default_embedding, "tts": default_tts}
    for model_type, name in defaults.items():
        if name is None:
            continue
        if name not in selected_names:
            raise InitError(f"default {model_type} profile was not selected for import: {name}")
        if candidates[name].model_type != model_type:
            raise InitError(f"default {model_type} profile has type {candidates[name].model_type}: {name}")

    common = {
        "user": user,
        "port": 22,
        "install_root": "~/.local/llm-ops",
        "public_bin_dir": "~/.local/bin",
        "config_profile": "default",
    }
    if preset == "single-host":
        hosts = [{"name": "local", "role": "hybrid", "host": "localhost", "transport": "local", **common}]
        model_name = agent_name = "local"
        model_port = 11433
        proxy_upstream = "http://127.0.0.1:11433"
    else:
        hosts = [
            {"name": "model-host", "role": "llm", "host": model_host, **common},
            {"name": "agent-host", "role": "agent", "host": agent_host, **common},
        ]
        model_name, agent_name = "model-host", "agent-host"
        model_port = 11434
        proxy_upstream = "http://model-host:11434"

    chat_profile = default_chat or ("starter-chat" if "chat" in selected_names else "chat")
    documents: dict[Path, dict[str, Any]] = {
        paths.config_file: {"schema_version": 1, "runtime": {"allow_command_driver": False}},
        paths.inventory_file: {"schema_version": 1, "hosts": hosts},
        paths.services_dir / "model-proxy.json": {
            "schema_version": 1,
            "name": "model-proxy",
            "runtime": {
                "listen_host": "127.0.0.1",
                "listen_port": 11434,
                "upstream_host": proxy_upstream.rsplit(":", 1)[0].removeprefix("http://"),
                "upstream_port": int(proxy_upstream.rsplit(":", 1)[1]),
            },
        },
        paths.agents_dir / "example-agent.json": {
            "schema_version": 1,
            "actions": {action: ["/path/to/agent", action] for action in ("start", "stop", "restart", "status")},
        },
    }
    if default_chat is None:
        documents[paths.models_dir / f"{chat_profile}.json"] = {
            "schema_version": 1,
            "name": chat_profile,
            "type": "llm",
            "model_path": "/path/to/model.gguf",
            "runtime": {"host": "127.0.0.1", "port": model_port},
            "llama": {"ctx_size": 32768, "gpu_layers": "auto"},
            "server": {"cache_prompt": True, "extra_flags": []},
        }
    for name in selected_names:
        documents[paths.models_dir / f"{name}.json"] = candidates[name].profile

    components: list[dict[str, Any]] = [
        {"id": "chat", "host": model_name, "driver": "modelctl", "profile": chat_profile, "enabled": False},
    ]
    if default_embedding:
        components.append({"id": "embedding", "host": model_name, "driver": "modelctl", "profile": default_embedding, "enabled": False})
    if default_tts:
        components.append({"id": "tts", "host": model_name, "driver": "modelctl", "profile": default_tts, "enabled": False})
    components.extend(
        [
            {"id": "model-proxy", "host": agent_name, "driver": "model-proxy", "profile": "model-proxy", "enabled": False, "depends_on": ["chat"]},
            {"id": "agent", "host": agent_name, "driver": "agent", "profile": "example-agent", "enabled": False, "depends_on": ["model-proxy"]},
        ]
    )
    documents[paths.stacks_dir / "starter.json"] = {"schema_version": 1, "name": "starter", "components": components}
    _write_documents(paths.config_home, documents, force=force)
    converted = tuple(
        f"{name}:{field}"
        for name in selected_names
        for field in candidates[name].converted_secrets
    )
    return InitResult(tuple(documents), selected_names, converted)
