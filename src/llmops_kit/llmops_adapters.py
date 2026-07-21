"""Versioned adapter registry for component lifecycle backends."""

from __future__ import annotations

import importlib.metadata
import platform
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Optional, Protocol


API_VERSION = "1.0"

COMPONENT_FIELD_SCHEMA: dict[str, dict[str, Any]] = {
    "host": {"label": "Host", "group": "Placement", "order": 10, "type": "string", "required": True},
    "profile": {"label": "Profile", "group": "Configuration", "order": 20, "type": "string", "required": True},
    "ownership": {"label": "Ownership", "group": "Lifecycle", "order": 30, "type": "enum", "choices": ["managed", "external"]},
    "enabled": {"label": "Enabled", "group": "Lifecycle", "order": 40, "type": "boolean"},
    "depends_on": {"label": "Dependencies", "group": "Topology", "order": 50, "type": "string-list"},
    "health_timeout": {"label": "Health timeout", "group": "Readiness", "order": 60, "type": "integer", "minimum": 1, "maximum": 3600},
}


class AdapterError(RuntimeError):
    """Raised when adapter discovery or validation fails."""


@dataclass(frozen=True)
class AdapterUpdateCapabilities:
    """Optional product-native update operations implemented by an adapter."""

    check: bool = True
    plan: bool = False
    apply: bool = False
    backup: bool = False
    rollback: bool = False
    post_update_health: bool = False


@dataclass(frozen=True)
class AdapterRelocationCapabilities:
    """Optional validated placement operations implemented by an adapter."""

    stateless: bool = False
    preflight: bool = False
    cutover: bool = False
    rollback: bool = False


class AdapterUpdateProvider(Protocol):
    """Execution boundary for product-native component update providers."""

    def installed_version(self, component: Any) -> str:
        """Return the installed product version."""

    def available_version(self, component: Any) -> dict[str, Any]:
        """Return available version, security, compatibility, and risk metadata."""

    def plan_update(self, component: Any) -> list[dict[str, Any]]:
        """Return a non-mutating native update plan."""

    def apply_update(self, component: Any) -> dict[str, Any]:
        """Apply the native update and post-update validation."""

    def rollback_update(self, component: Any) -> dict[str, Any]:
        """Restore the adapter-owned pre-update state."""


@dataclass(frozen=True)
class AdapterManifest:
    """Declarative capabilities and requirements for one adapter."""

    adapter_id: str
    version: str
    api_version: str = API_VERSION
    kind: str = "lifecycle"
    drivers: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ("lifecycle", "status", "logs")
    platforms: tuple[str, ...] = ("darwin",)
    required_executables: tuple[str, ...] = ()
    transports: tuple[str, ...] = ("local", "ssh")
    schema: dict[str, Any] = field(default_factory=dict)
    update: Optional[AdapterUpdateCapabilities] = None
    relocation: Optional[AdapterRelocationCapabilities] = None

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation."""

        return asdict(self)


def register_builtin_adapters() -> list[AdapterManifest]:
    """Return built-in adapters through the same contract as plugins."""

    return [
        AdapterManifest("launchd", "1.0.0", drivers=("launchd",), required_executables=("launchctl",), transports=("local",), schema={"profile_kind": "service", "component_fields": COMPONENT_FIELD_SCHEMA}),
        AdapterManifest("standalone", "1.0.0", drivers=("process", "command", "agent"), schema={"profile_kind": "service-or-agent", "component_fields": COMPONENT_FIELD_SCHEMA}),
        AdapterManifest("ssh-tunnel", "1.0.0", drivers=("ssh-tunnel",), required_executables=("ssh",), schema={"profile_kind": "service", "component_fields": COMPONENT_FIELD_SCHEMA}),
        AdapterManifest("llama-cpp", "1.0.0", drivers=("modelctl",), schema={"profile_kind": "model", "component_fields": COMPONENT_FIELD_SCHEMA}),
        AdapterManifest("model-proxy", "1.0.0", drivers=("model-proxy",), schema={"profile_kind": "service", "component_fields": COMPONENT_FIELD_SCHEMA}),
        AdapterManifest("tts-bridge", "1.0.0", drivers=("tts-bridge",), schema={"profile_kind": "service", "component_fields": COMPONENT_FIELD_SCHEMA}),
    ]


def _normalize_loaded(value: Any, source: str) -> list[AdapterManifest]:
    loaded = value() if callable(value) else value
    if isinstance(loaded, AdapterManifest):
        return [loaded]
    if isinstance(loaded, Iterable) and not isinstance(loaded, (str, bytes, dict)):
        manifests = list(loaded)
        if all(isinstance(item, AdapterManifest) for item in manifests):
            return manifests
    raise AdapterError(f"adapter entry point returned an invalid manifest: {source}")


def discover_adapters(
    *,
    entry_points: Optional[Iterable[importlib.metadata.EntryPoint]] = None,
) -> dict[str, AdapterManifest]:
    """Discover built-ins and compatible third-party entry points."""

    manifests = register_builtin_adapters()
    if entry_points is None:
        selected = importlib.metadata.entry_points()
        entry_points = selected.select(group="llmops.adapters") if hasattr(selected, "select") else selected.get("llmops.adapters", [])
    for entry_point in entry_points:
        if entry_point.name == "builtin" and entry_point.value.endswith("register_builtin_adapters"):
            continue
        manifests.extend(_normalize_loaded(entry_point.load(), entry_point.name))
    registry: dict[str, AdapterManifest] = {}
    for manifest in manifests:
        if manifest.adapter_id in registry:
            raise AdapterError(f"duplicate adapter ID: {manifest.adapter_id}")
        if manifest.api_version.split(".", 1)[0] != API_VERSION.split(".", 1)[0]:
            raise AdapterError(f"incompatible adapter API for {manifest.adapter_id}: {manifest.api_version}")
        registry[manifest.adapter_id] = manifest
    return registry


def validate_adapters(registry: dict[str, AdapterManifest], drivers: Iterable[str]) -> list[str]:
    """Return deterministic adapter compatibility errors."""

    errors: list[str] = []
    current = platform.system().lower()
    claimed: dict[str, str] = {}
    for adapter_id, manifest in sorted(registry.items()):
        if current not in manifest.platforms:
            errors.append(f"{adapter_id}: unsupported platform {current}")
        for driver in manifest.drivers:
            if driver in claimed:
                errors.append(f"driver {driver} is claimed by both {claimed[driver]} and {adapter_id}")
            claimed[driver] = adapter_id
    for driver in sorted(set(drivers) - set(claimed)):
        errors.append(f"driver has no registered adapter: {driver}")
    return errors
