#!/usr/bin/env python
"""Path resolution helpers for LLM-Ops-Kit.

This module defines the platform-neutral filesystem layout used by new
configuration and deployment tooling. It intentionally avoids OS-specific
branches so local, CI, container, and remote-host behavior stay consistent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "llm-ops"


def _home(env: dict[str, str]) -> Path:
    return Path(env.get("HOME", "~")).expanduser()


def _resolve_home(
    env: dict[str, str],
    *,
    llmops_var: str,
    xdg_var: str,
    default_relative: str,
) -> Path:
    if env.get(llmops_var):
        return Path(env[llmops_var]).expanduser()
    if env.get(xdg_var):
        return (Path(env[xdg_var]).expanduser() / APP_NAME).resolve()
    return (_home(env) / default_relative / APP_NAME).expanduser()


def resolve_authority_config_home(env: dict[str, str] | None = None) -> Path:
    """Return the mutable desired-state root, independent of deployed revisions."""

    values = dict(os.environ if env is None else env)
    if values.get("LLMOPS_AUTHORITY_CONFIG_HOME"):
        return Path(values["LLMOPS_AUTHORITY_CONFIG_HOME"]).expanduser()
    base = Path(values.get("XDG_CONFIG_HOME", _home(values) / ".config")).expanduser()
    return base / APP_NAME


@dataclass(frozen=True)
class LlmOpsPaths:
    """Resolved LLM-Ops-Kit paths."""

    config_home: Path
    data_home: Path
    state_home: Path
    cache_home: Path

    @property
    def config_file(self) -> Path:
        return self.config_home / "config.json"

    @property
    def inventory_file(self) -> Path:
        return self.config_home / "inventory.json"

    @property
    def models_dir(self) -> Path:
        return self.config_home / "models"

    @property
    def agents_dir(self) -> Path:
        return self.config_home / "agents"

    @property
    def profiles_dir(self) -> Path:
        return self.config_home / "profiles"

    @property
    def services_dir(self) -> Path:
        return self.config_home / "services"

    @property
    def stacks_dir(self) -> Path:
        return self.config_home / "stacks"

    @property
    def bundles_dir(self) -> Path:
        return self.data_home / "bundles"

    @property
    def stage_dir(self) -> Path:
        return self.data_home / "stage"

    @property
    def runtime_data_dir(self) -> Path:
        return self.data_home / "runtime-data"

    @property
    def run_dir(self) -> Path:
        return self.state_home / "run"

    @property
    def logs_dir(self) -> Path:
        return self.state_home / "logs"

    @property
    def health_dir(self) -> Path:
        return self.state_home / "health"

    @property
    def plans_dir(self) -> Path:
        return self.state_home / "plans"

    @property
    def gguf_metadata_cache_dir(self) -> Path:
        return self.cache_home / "gguf-metadata"

    @property
    def probes_cache_dir(self) -> Path:
        return self.cache_home / "probes"

    def as_dict(self) -> dict[str, str]:
        """Return a stable string mapping for CLI reports and tests."""

        return {
            "config_home": str(self.config_home),
            "config_file": str(self.config_file),
            "inventory_file": str(self.inventory_file),
            "models_dir": str(self.models_dir),
            "agents_dir": str(self.agents_dir),
            "profiles_dir": str(self.profiles_dir),
            "services_dir": str(self.services_dir),
            "stacks_dir": str(self.stacks_dir),
            "data_home": str(self.data_home),
            "bundles_dir": str(self.bundles_dir),
            "stage_dir": str(self.stage_dir),
            "runtime_data_dir": str(self.runtime_data_dir),
            "state_home": str(self.state_home),
            "run_dir": str(self.run_dir),
            "logs_dir": str(self.logs_dir),
            "health_dir": str(self.health_dir),
            "plans_dir": str(self.plans_dir),
            "cache_home": str(self.cache_home),
            "gguf_metadata_cache_dir": str(self.gguf_metadata_cache_dir),
            "probes_cache_dir": str(self.probes_cache_dir),
        }


def resolve_paths(env: dict[str, str] | None = None) -> LlmOpsPaths:
    """Resolve the platform-neutral LLM-Ops-Kit directory layout."""

    values = dict(os.environ if env is None else env)
    return LlmOpsPaths(
        config_home=_resolve_home(
            values,
            llmops_var="LLMOPS_CONFIG_HOME",
            xdg_var="XDG_CONFIG_HOME",
            default_relative=".config",
        ),
        data_home=_resolve_home(
            values,
            llmops_var="LLMOPS_DATA_HOME",
            xdg_var="XDG_DATA_HOME",
            default_relative=".local/share",
        ),
        state_home=_resolve_home(
            values,
            llmops_var="LLMOPS_STATE_HOME",
            xdg_var="XDG_STATE_HOME",
            default_relative=".local/state",
        ),
        cache_home=_resolve_home(
            values,
            llmops_var="LLMOPS_CACHE_HOME",
            xdg_var="XDG_CACHE_HOME",
            default_relative=".cache",
        ),
    )
