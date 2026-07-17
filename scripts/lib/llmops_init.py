#!/usr/bin/env python3
"""Generate conservative starter configuration for LLM-Ops-Kit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from llmops_paths import LlmOpsPaths
except ModuleNotFoundError:  # pragma: no cover
    from .llmops_paths import LlmOpsPaths


class InitError(RuntimeError):
    """Raised when starter configuration cannot be created safely."""


def _write_json(path: Path, payload: dict[str, Any], *, force: bool) -> None:
    if path.exists() and not force:
        raise InitError(f"refusing to overwrite existing configuration: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def initialize(
    paths: LlmOpsPaths,
    *,
    preset: str,
    force: bool = False,
    user: str,
    model_host: str = "model-host.local",
    agent_host: str = "agent-host.local",
) -> list[Path]:
    """Write a disabled starter topology for a single host or local LAN."""

    if preset not in {"single-host", "local-lan"}:
        raise InitError(f"unsupported preset: {preset}")
    common = {
        "user": user,
        "port": 22,
        "install_root": "~/.local/llm-ops",
        "config_profile": "default",
    }
    if preset == "single-host":
        hosts = [
            {
                "name": "local",
                "role": "hybrid",
                "host": "localhost",
                "transport": "local",
                **common,
            }
        ]
        model_name = agent_name = "local"
        model_port = 11433
        proxy_upstream = "http://127.0.0.1:11433"
    else:
        hosts = [
            {"name": "model-host", "role": "llm", "host": model_host, **common},
            {"name": "agent-host", "role": "agent", "host": agent_host, **common},
        ]
        model_name = "model-host"
        agent_name = "agent-host"
        model_port = 11434
        proxy_upstream = "http://model-host:11434"

    documents = {
        paths.config_file: {
            "schema_version": 1,
            "runtime": {"allow_command_driver": False},
        },
        paths.inventory_file: {"schema_version": 1, "hosts": hosts},
        paths.models_dir / "chat.json": {
            "schema_version": 1,
            "name": "chat",
            "type": "llm",
            "model_path": "/path/to/model.gguf",
            "runtime": {"host": "127.0.0.1", "port": model_port},
            "llama": {"ctx_size": 32768, "gpu_layers": "auto"},
            "server": {"cache_prompt": True, "extra_flags": []},
        },
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
            "actions": {
                "start": ["/path/to/agent", "start"],
                "stop": ["/path/to/agent", "stop"],
                "restart": ["/path/to/agent", "restart"],
                "status": ["/path/to/agent", "status"],
            },
        },
        paths.stacks_dir / "starter.json": {
            "schema_version": 1,
            "name": "starter",
            "components": [
                {
                    "id": "chat",
                    "host": model_name,
                    "driver": "modelctl",
                    "profile": "chat",
                    "enabled": False,
                },
                {
                    "id": "model-proxy",
                    "host": agent_name,
                    "driver": "model-proxy",
                    "profile": "model-proxy",
                    "enabled": False,
                    "depends_on": ["chat"],
                },
                {
                    "id": "agent",
                    "host": agent_name,
                    "driver": "agent",
                    "profile": "example-agent",
                    "enabled": False,
                    "depends_on": ["model-proxy"],
                },
            ],
        },
    }
    if not force:
        conflicts = [path for path in documents if path.exists()]
        if conflicts:
            raise InitError(
                "refusing to overwrite existing configuration: "
                + ", ".join(str(path) for path in conflicts)
            )
    for path, payload in documents.items():
        _write_json(path, payload, force=force)
    return list(documents)
