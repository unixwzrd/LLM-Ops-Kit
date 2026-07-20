#!/usr/bin/env python
"""Canonical JSON profile loading and runtime value resolution."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from llmops_paths import LlmOpsPaths, resolve_paths
except ModuleNotFoundError:  # pragma: no cover
    from .llmops_paths import LlmOpsPaths, resolve_paths


class ProfileError(ValueError):
    """Raised when a canonical profile is missing or malformed."""


PROFILE_DIRS = {
    "agent": "agents",
    "model": "models",
    "service": "services",
}


def profile_path(paths: LlmOpsPaths, kind: str, name: str) -> Path:
    """Return the only supported profile path for a profile kind and name."""

    if kind not in PROFILE_DIRS:
        raise ProfileError(f"unsupported profile kind: {kind}")
    if not name or "/" in name or name in {".", ".."}:
        raise ProfileError(f"invalid profile name: {name!r}")
    return paths.config_home / PROFILE_DIRS[kind] / f"{name}.json"


def load_profile(
    kind: str,
    name: str,
    *,
    paths: Optional[LlmOpsPaths] = None,
    path: Optional[Path] = None,
) -> tuple[Path, dict[str, Any]]:
    """Load one canonical JSON profile without repository or shell fallbacks."""

    resolved_paths = paths or resolve_paths()
    source = path.expanduser() if path is not None else profile_path(resolved_paths, kind, name)
    if not source.is_file():
        raise ProfileError(f"{kind} profile not found: {source}")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(f"{source}: invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ProfileError(f"{source}: profile must be a JSON object")
    if raw.get("schema_version", 1) != 1:
        raise ProfileError(f"{source}: unsupported schema_version: {raw.get('schema_version')}")
    return source, raw


def _bool(value: Any) -> str:
    return "1" if bool(value) else "0"


def _clean(values: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items() if value not in (None, "")}


def resolve_references(values: dict[str, str], env: dict[str, str]) -> dict[str, str]:
    """Resolve explicit environment references for runtime execution."""

    resolved: dict[str, str] = {}
    for key, value in values.items():
        if value.startswith("env:"):
            variable = value.removeprefix("env:")
            if not variable or variable not in env:
                raise ProfileError(f"unresolved environment reference for {key}: {value}")
            resolved[key] = env[variable]
        elif value.startswith("seckit:"):
            raise ProfileError(f"unresolved Secrets-Kit reference for {key}; configure the provider before runtime use")
        else:
            resolved[key] = value
    return resolved


def model_values(profile: dict[str, Any]) -> dict[str, str]:
    """Resolve a model profile into the stable modelctl runtime vocabulary."""

    runtime = profile.get("runtime") or profile.get("server") or {}
    llama = profile.get("llama") or {}
    sampling = profile.get("sampling") or {}
    template = profile.get("template") or {}
    server = profile.get("server") or {}
    if not all(isinstance(item, dict) for item in (runtime, llama, sampling, template, server)):
        raise ProfileError("model profile sections must be JSON objects")
    explicit = profile.get("environment")
    if explicit is not None:
        if not isinstance(explicit, dict):
            raise ProfileError("model environment must be a JSON object")
        return _clean(explicit)
    return _clean(
        {
            "MODEL_PROFILE": profile.get("name"),
            "MODEL_TYPE": profile.get("type", profile.get("model_type", "llm")),
            "MODEL": profile.get("model_path"),
            "PORT": runtime.get("port"),
            "HOST": runtime.get("host"),
            "THREADS": runtime.get("threads", "auto"),
            "THREADS_BATCH": runtime.get("threads_batch", runtime.get("threads", "auto")),
            "CTX_SIZE": llama.get("ctx_size"),
            "GPU_LAYERS": llama.get("gpu_layers"),
            "BATCH_SIZE": llama.get("batch_size"),
            "UBATCH_SIZE": llama.get("ubatch_size"),
            "USE_MLOCK": _bool(llama.get("use_mlock", False)),
            "USE_NO_MMAP": _bool(llama.get("use_no_mmap", False)),
            "DIRECT_IO": _bool(llama.get("direct_io", False)),
            "USE_CUSTOM_TEMPLATE": _bool(template.get("enabled", False)),
            "CHAT_TEMPLATE": template.get("path"),
            "CACHE_PROMPT": _bool(server.get("cache_prompt", False)),
            "CACHE_REUSE": server.get("cache_reuse"),
            "SLOT_SAVE_PATH": server.get("slot_save_path"),
            "SPEC_TYPE": server.get("spec_type"),
            "SPEC_NGRAM_SIZE_N": server.get("spec_ngram_size_n"),
            "SPEC_NGRAM_SIZE_M": server.get("spec_ngram_size_m"),
            "PERF": _bool(server.get("perf", False)),
            "FLASH_ATTENTION": _bool(server.get("flash_attention", False)),
            "NO_CPU_MOE": _bool(server.get("no_cpu_moe", False)),
            "NO_HOST": _bool(server.get("no_host", False)),
            "EXTRA_FLAGS": " ".join(str(flag) for flag in server.get("extra_flags", [])),
            "TEMP": sampling.get("temp"),
            "TOP_P": sampling.get("top_p"),
            "TOP_K": sampling.get("top_k"),
            "MIN_P": sampling.get("min_p"),
            "PRESENCE_PENALTY": sampling.get("presence_penalty"),
            "REPEAT_PENALTY": sampling.get("repeat_penalty"),
        }
    )


def service_values(name: str, profile: dict[str, Any]) -> dict[str, str]:
    """Resolve a supported service profile into its runtime vocabulary."""

    explicit = profile.get("environment")
    if explicit is not None:
        if not isinstance(explicit, dict):
            raise ProfileError("service environment must be a JSON object")
        return _clean(explicit)
    runtime = profile.get("runtime") or {}
    paths = profile.get("paths") or {}
    logging = profile.get("logging") or {}
    defaults = profile.get("defaults") or {}
    template = profile.get("template") or {}
    if name == "model-proxy":
        return _clean(
            {
                "LLMOPS_UPSTREAM_HOST": runtime.get("upstream_host"),
                "LLMOPS_UPSTREAM_PORT": runtime.get("upstream_port"),
                "MODEL_PROXY_LISTEN_HOST": runtime.get("listen_host"),
                "MODEL_PROXY_LISTEN_PORT": runtime.get("listen_port"),
                "MODEL_PROXY_PYTHON_BIN": runtime.get("python_bin"),
                "MODEL_PROXY_CHAT_TEMPLATE": template.get("path"),
                "MODEL_PROXY_LOG_ROTATE_SECONDS": logging.get("rotate_seconds"),
                "MODEL_PROXY_LOG_ROTATE_KEEP": logging.get("rotate_keep"),
            }
        )
    if name == "tts-bridge":
        return _clean(
            {
                "TTS_BRIDGE_HOST": runtime.get("host"),
                "TTS_BRIDGE_PORT": runtime.get("port"),
                "TTS_BRIDGE_UPSTREAM_BASE": runtime.get("upstream_base"),
                "TTS_BRIDGE_MODEL": paths.get("model"),
                "TTS_BRIDGE_CONFIG_DIR": paths.get("config_dir"),
                "TTS_BRIDGE_PRONOUNCE_CONFIG": paths.get("pronounce_config"),
                "TTS_BRIDGE_VOICE_MAP_CONFIG": paths.get("voice_map_config"),
                "TTS_BRIDGE_SAMPLES_DIR": paths.get("samples_dir"),
                "TTS_BRIDGE_LOG_ROTATE_SECONDS": logging.get("rotate_seconds"),
                "TTS_BRIDGE_LOG_ROTATE_KEEP": logging.get("rotate_keep"),
                "TTS_BRIDGE_REF_AUDIO": defaults.get("ref_audio"),
                "TTS_BRIDGE_REF_TEXT": defaults.get("ref_text"),
                "TTS_BRIDGE_PYTHON_BIN": runtime.get("python_bin"),
            }
        )
    raise ProfileError(f"unsupported service profile: {name}")


def resolved_values(kind: str, name: str, profile: dict[str, Any], *, runtime_env: Optional[dict[str, str]] = None) -> dict[str, str]:
    """Resolve one profile into stable runtime values."""

    if kind == "model":
        values = model_values(profile)
        return resolve_references(values, runtime_env) if runtime_env is not None else values
    if kind == "service":
        values = service_values(name, profile)
        return resolve_references(values, runtime_env) if runtime_env is not None else values
    if kind == "agent":
        environment = profile.get("environment", {})
        if not isinstance(environment, dict):
            raise ProfileError("agent environment must be a JSON object")
        values = _clean(environment)
        return resolve_references(values, runtime_env) if runtime_env is not None else values
    raise ProfileError(f"unsupported profile kind: {kind}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve an LLM-Ops-Kit JSON profile")
    parser.add_argument("kind", choices=sorted(PROFILE_DIRS))
    parser.add_argument("name")
    parser.add_argument("--profile-path")
    parser.add_argument("--config-home")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--resolve-references", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    env = dict(os.environ)
    if args.config_home:
        env["LLMOPS_CONFIG_HOME"] = args.config_home
    try:
        source, profile = load_profile(
            args.kind,
            args.name,
            paths=resolve_paths(env),
            path=Path(args.profile_path) if args.profile_path else None,
        )
        values = resolved_values(
            args.kind,
            args.name,
            profile,
            runtime_env=dict(os.environ) if args.resolve_references else None,
        )
    except ProfileError as exc:
        print(f"llmops: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"profile": str(source), "values": values}, indent=2, sort_keys=True))
    else:
        for key in sorted(values):
            print(f"{key}={shlex.quote(values[key])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
