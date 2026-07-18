#!/usr/bin/env python3
"""Canonical component and stack topology for LLM-Ops-Kit."""

from __future__ import annotations

import json
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

try:
    from llmops_config import LlmOpsConfig
    from llmops_inventory import HostRecord
    from llmops_paths import LlmOpsPaths
    from llmops_profiles import ProfileError, model_values, service_values
except ModuleNotFoundError:  # pragma: no cover
    from .llmops_config import LlmOpsConfig
    from .llmops_inventory import HostRecord
    from .llmops_paths import LlmOpsPaths
    from .llmops_profiles import ProfileError, model_values, service_values


SUPPORTED_DRIVERS = {
    "agent",
    "command",
    "launchd",
    "model-proxy",
    "modelctl",
    "process",
    "ssh-tunnel",
    "tts-bridge",
}
PROFILE_DIR_BY_DRIVER = {
    "agent": "agents",
    "command": "services",
    "launchd": "services",
    "model-proxy": "services",
    "modelctl": "models",
    "process": "services",
    "ssh-tunnel": "services",
    "tts-bridge": "services",
}


class TopologyError(ValueError):
    """Raised when a component topology is invalid."""


@dataclass(frozen=True)
class HealthCheck:
    """Readiness check attached to a component."""

    kind: str = "driver"
    target: str = ""
    timeout_seconds: int = 60


@dataclass(frozen=True)
class Component:
    """One independently managed component inside a stack."""

    stack: str
    component_id: str
    host: str
    driver: str
    profile: str
    enabled: bool
    depends_on: tuple[str, ...]
    ownership: str
    tags: tuple[str, ...]
    health: HealthCheck

    @property
    def qualified_id(self) -> str:
        """Return the globally unambiguous component identifier."""

        return f"{self.stack}:{self.component_id}"


@dataclass(frozen=True)
class Stack:
    """A named dependency graph of components."""

    name: str
    path: Path
    components: dict[str, Component]


@dataclass(frozen=True)
class Topology:
    """All loaded stacks plus validated host and profile references."""

    stacks: dict[str, Stack]
    hosts: dict[str, HostRecord]
    paths: LlmOpsPaths
    config: LlmOpsConfig

    def all_components(self, *, enabled_only: bool = False) -> list[Component]:
        """Return components in stable stack and component order."""

        components = [
            component
            for stack_name in sorted(self.stacks)
            for component in self.stacks[stack_name].components.values()
        ]
        if enabled_only:
            components = [component for component in components if component.enabled]
        return components

    def resolve_component(self, reference: str) -> Component:
        """Resolve `stack:component` or an unambiguous short component ID."""

        normalized = reference.replace("/", ":", 1)
        if ":" in normalized:
            stack_name, component_id = normalized.split(":", 1)
            stack = self.stacks.get(stack_name)
            if stack is None or component_id not in stack.components:
                raise TopologyError(f"component not found: {reference}")
            return stack.components[component_id]
        matches = [item for item in self.all_components() if item.component_id == normalized]
        if not matches:
            raise TopologyError(f"component not found: {reference}")
        if len(matches) > 1:
            choices = ", ".join(item.qualified_id for item in matches)
            raise TopologyError(f"ambiguous component '{reference}'; use one of: {choices}")
        return matches[0]


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TopologyError(f"{path}: invalid {label} JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise TopologyError(f"{path}: {label} must be a JSON object")
    if raw.get("schema_version", 1) != 1:
        raise TopologyError(f"{path}: unsupported schema_version: {raw.get('schema_version')}")
    return raw


def profile_path(paths: LlmOpsPaths, component: Component) -> Path:
    """Return the canonical profile path for a component."""

    directory = getattr(paths, f"{PROFILE_DIR_BY_DRIVER[component.driver]}_dir")
    return directory / f"{component.profile}.json"


def load_profile(paths: LlmOpsPaths, component: Component) -> dict[str, Any]:
    """Load the JSON profile referenced by a component."""

    path = profile_path(paths, component)
    if not path.is_file():
        raise TopologyError(f"{component.qualified_id}: profile not found: {path}")
    return _load_json_object(path, label="profile")


def _parse_health(raw: Any, *, component_ref: str) -> HealthCheck:
    if raw is None:
        return HealthCheck()
    if not isinstance(raw, dict):
        raise TopologyError(f"{component_ref}: health must be an object")
    kind = str(raw.get("type", "driver"))
    if kind not in {"driver", "http", "tcp", "none"}:
        raise TopologyError(f"{component_ref}: unsupported health type: {kind}")
    target = str(raw.get("target", raw.get("url", "")))
    timeout = raw.get("timeout_seconds", 60)
    if not isinstance(timeout, int) or timeout < 1 or timeout > 3600:
        raise TopologyError(f"{component_ref}: health timeout_seconds must be 1..3600")
    if kind in {"http", "tcp"} and not target:
        raise TopologyError(f"{component_ref}: health target is required for {kind}")
    return HealthCheck(kind=kind, target=target, timeout_seconds=timeout)


def _parse_component(stack_name: str, raw: Any) -> Component:
    if not isinstance(raw, dict):
        raise TopologyError(f"stack {stack_name}: every component must be an object")
    component_id = raw.get("id")
    if not isinstance(component_id, str) or not component_id.strip() or ":" in component_id:
        raise TopologyError(f"stack {stack_name}: invalid component id: {component_id!r}")
    reference = f"{stack_name}:{component_id}"
    driver = raw.get("driver")
    if driver not in SUPPORTED_DRIVERS:
        raise TopologyError(f"{reference}: unsupported driver: {driver}")
    host = raw.get("host")
    profile = raw.get("profile")
    if not isinstance(host, str) or not host:
        raise TopologyError(f"{reference}: host is required")
    if not isinstance(profile, str) or not profile:
        raise TopologyError(f"{reference}: profile is required")
    depends = raw.get("depends_on", [])
    if not isinstance(depends, list) or any(not isinstance(item, str) for item in depends):
        raise TopologyError(f"{reference}: depends_on must be an array of component IDs")
    ownership = str(raw.get("ownership", "managed"))
    if ownership not in {"managed", "external"}:
        raise TopologyError(f"{reference}: ownership must be managed or external")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise TopologyError(f"{reference}: enabled must be boolean")
    tags = raw.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
        raise TopologyError(f"{reference}: tags must be nonempty strings")
    normalized_dependencies = tuple(
        item if ":" in item else f"{stack_name}:{item}" for item in depends
    )
    return Component(
        stack=stack_name,
        component_id=component_id,
        host=host,
        driver=driver,
        profile=profile,
        enabled=enabled,
        depends_on=normalized_dependencies,
        ownership=ownership,
        tags=tuple(dict.fromkeys(tag.strip() for tag in tags)),
        health=_parse_health(raw.get("health"), component_ref=reference),
    )


def load_stacks(paths: LlmOpsPaths) -> dict[str, Stack]:
    """Load all canonical stack documents."""

    if not paths.stacks_dir.is_dir():
        return {}
    stacks: dict[str, Stack] = {}
    for path in sorted(paths.stacks_dir.glob("*.json")):
        raw = _load_json_object(path, label="stack")
        name = raw.get("name", path.stem)
        if not isinstance(name, str) or not name:
            raise TopologyError(f"{path}: stack name must be a nonempty string")
        if name in stacks:
            raise TopologyError(f"duplicate stack name: {name}")
        items = raw.get("components")
        if not isinstance(items, list) or not items:
            raise TopologyError(f"{path}: stack contains no components")
        components: dict[str, Component] = {}
        for item in items:
            component = _parse_component(name, item)
            if component.component_id in components:
                raise TopologyError(f"{path}: duplicate component id: {component.component_id}")
            components[component.component_id] = component
        stacks[name] = Stack(name=name, path=path, components=components)
    return stacks


def topological_order(stack: Stack, *, subset: Optional[Iterable[str]] = None) -> list[Component]:
    """Return dependency-first component order and reject cycles."""

    selected = (
        {component.qualified_id for component in stack.components.values()}
        if subset is None
        else set(subset)
    )
    by_qualified = {component.qualified_id: component for component in stack.components.values()}
    order: list[Component] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(reference: str) -> None:
        if reference in visited or reference not in selected:
            return
        if reference in visiting:
            raise TopologyError(f"dependency cycle detected at {reference}")
        component = by_qualified.get(reference)
        if component is None:
            raise TopologyError(f"{stack.name}: dependency not found: {reference}")
        visiting.add(reference)
        for dependency in component.depends_on:
            if dependency not in by_qualified:
                raise TopologyError(f"{component.qualified_id}: dependency not found: {dependency}")
            visit(dependency)
        visiting.remove(reference)
        visited.add(reference)
        order.append(component)

    for reference in sorted(selected):
        visit(reference)
    return order


def dependency_closure(stack: Stack, component: Component) -> set[str]:
    """Return the target plus all transitive upstream dependencies."""

    by_qualified = {item.qualified_id: item for item in stack.components.values()}
    selected: set[str] = set()

    def add(reference: str) -> None:
        if reference in selected:
            return
        selected.add(reference)
        item = by_qualified[reference]
        for dependency in item.depends_on:
            add(dependency)

    add(component.qualified_id)
    return selected


def dependent_closure(stack: Stack, component: Component) -> set[str]:
    """Return the target plus all transitive downstream dependents."""

    selected = {component.qualified_id}
    changed = True
    while changed:
        changed = False
        for item in stack.components.values():
            if item.qualified_id in selected:
                continue
            if any(dependency in selected for dependency in item.depends_on):
                selected.add(item.qualified_id)
                changed = True
    return selected


def _profile_bindings(profile: dict[str, Any], values: Optional[dict[str, str]] = None) -> set[tuple[str, int]]:
    bindings: set[tuple[str, int]] = set()
    candidates = [profile]
    for section in ("runtime", "server", "listen"):
        candidate = profile.get(section)
        if isinstance(candidate, dict):
            candidates.append(candidate)
    for candidate in candidates:
        host = candidate.get("host", candidate.get("listen_host"))
        port = candidate.get("port", candidate.get("listen_port"))
        if isinstance(host, str) and isinstance(port, (int, str)) and str(port).isdigit():
            bindings.add((host, int(port)))
    if values:
        host = values.get("HOST") or values.get("MODEL_PROXY_LISTEN_HOST") or values.get("TTS_BRIDGE_HOST")
        port = values.get("PORT") or values.get("MODEL_PROXY_LISTEN_PORT") or values.get("TTS_BRIDGE_PORT")
        if host and port and str(port).isdigit():
            bindings.add((host, int(port)))
    url = profile.get("listen_url")
    if isinstance(url, str):
        parsed = urlparse(url)
        if parsed.hostname and parsed.port:
            bindings.add((parsed.hostname, parsed.port))
    return bindings


def _required(values: dict[str, str], names: tuple[str, ...], *, component: Component) -> list[str]:
    return [
        f"{component.qualified_id}: profile missing required runtime value: {name}"
        for name in names
        if not values.get(name)
    ]


def _validate_profile(component: Component, profile: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    """Validate driver-specific profile contracts without contacting managed hosts."""

    errors: list[str] = []
    values: dict[str, str] = {}
    try:
        if component.driver == "modelctl":
            values = model_values(profile)
            errors.extend(
                _required(
                    values,
                    ("MODEL_PROFILE", "MODEL_TYPE", "MODEL", "HOST", "PORT"),
                    component=component,
                )
            )
            model_type = values.get("MODEL_TYPE")
            if model_type not in {"llm", "embedding", "tts"}:
                errors.append(f"{component.qualified_id}: unsupported model type: {model_type or '<missing>'}")
            if model_type == "embedding":
                errors.extend(_required(values, ("POOLING",), component=component))
            if model_type == "tts":
                errors.extend(
                    _required(values, ("TTS_PYTHON_BIN", "TTS_SERVER_MODULE"), component=component)
                )
        elif component.driver in {"model-proxy", "tts-bridge"}:
            values = service_values(component.driver, profile)
            required = (
                ("LLMOPS_UPSTREAM_HOST", "LLMOPS_UPSTREAM_PORT", "MODEL_PROXY_LISTEN_HOST", "MODEL_PROXY_LISTEN_PORT")
                if component.driver == "model-proxy"
                else ("TTS_BRIDGE_UPSTREAM_BASE", "TTS_BRIDGE_PORT")
            )
            errors.extend(_required(values, required, component=component))
        elif component.driver in {"launchd", "ssh-tunnel"}:
            if not isinstance(profile.get("label"), str) or not profile.get("label"):
                errors.append(f"{component.qualified_id}: launchd profile requires label")
            if "plist" in profile and (not isinstance(profile["plist"], str) or not profile["plist"]):
                errors.append(f"{component.qualified_id}: launchd plist must be a path string")
        elif component.driver in {"agent", "process", "command"}:
            actions = profile.get("actions")
            if not isinstance(actions, dict):
                errors.append(f"{component.qualified_id}: profile actions must be an object")
            else:
                for action in ("start", "stop", "restart", "status"):
                    argv = actions.get(action)
                    if not isinstance(argv, list) or not argv or any(not isinstance(token, str) or not token for token in argv):
                        errors.append(
                            f"{component.qualified_id}: action {action} must be a nonempty argv array"
                        )
    except ProfileError as exc:
        errors.append(f"{component.qualified_id}: {exc}")
    return errors, values


def validate_topology(topology: Topology) -> list[str]:
    """Validate all host, profile, driver, dependency, and port contracts."""

    errors: list[str] = []
    if not topology.stacks:
        return [f"no stack definitions found under {topology.paths.stacks_dir}"]
    allow_command = bool(
        topology.config.data.get("runtime", {}).get("allow_command_driver", False)
    )
    bound: dict[tuple[str, str, int], str] = {}
    for stack in topology.stacks.values():
        try:
            topological_order(stack)
        except TopologyError as exc:
            errors.append(str(exc))
        for component in stack.components.values():
            if component.host not in topology.hosts:
                errors.append(f"{component.qualified_id}: inventory host not found: {component.host}")
                continue
            if component.driver == "command" and not allow_command:
                errors.append(
                    f"{component.qualified_id}: command driver requires runtime.allow_command_driver=true"
                )
            try:
                profile = load_profile(topology.paths, component)
            except TopologyError as exc:
                errors.append(str(exc))
                continue
            profile_errors, values = _validate_profile(component, profile)
            errors.extend(profile_errors)
            for bind_host, port in _profile_bindings(profile, values):
                key = (component.host, bind_host, port)
                if key in bound and bound[key] != component.qualified_id:
                    errors.append(
                        f"port conflict on {component.host} {bind_host}:{port}: "
                        f"{bound[key]} and {component.qualified_id}"
                    )
                else:
                    bound[key] = component.qualified_id
    return errors


def _contains_secret_value(value: Any, *, key_path: str = "") -> Optional[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{key_path}.{key}" if key_path else str(key)
            finding = _contains_secret_value(child, key_path=child_path)
            if finding:
                return finding
        return None
    if isinstance(value, list):
        for index, child in enumerate(value):
            finding = _contains_secret_value(child, key_path=f"{key_path}[{index}]")
            if finding:
                return finding
        return None
    key = key_path.rsplit(".", 1)[-1].lower()
    secret_key = any(token in key for token in ("password", "token", "api_key", "secret_value"))
    if secret_key and value not in (None, "", "<redacted>"):
        if isinstance(value, str) and value.startswith(("env:", "seckit:")):
            return None
        return key_path
    return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_topology_catalog(topology: Topology, destination: Path) -> Path:
    """Write the shared, secret-free observer catalog used for cross-host status."""

    catalog = {
        "schema_version": 1,
        "trusted_control_hosts": sorted(
            host.name for host in topology.hosts.values() if host.trusted_control
        ),
        "hosts": [
            {
                "name": host.name,
                "role": host.role,
                "host": host.control_host or host.host,
                "user": host.user,
                "port": host.port,
                "public_bin_dir": host.public_bin_dir,
                "tags": list(host.tags),
            }
            for host in sorted(topology.hosts.values(), key=lambda item: item.name)
        ],
        "components": [
            {
                "id": component.qualified_id,
                "stack": component.stack,
                "component_id": component.component_id,
                "host": component.host,
                "driver": component.driver,
                "profile": component.profile,
                "enabled": component.enabled,
                "ownership": component.ownership,
                "tags": list(component.tags),
                "depends_on": list(component.depends_on),
            }
            for component in topology.all_components()
        ],
    }
    destination.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def write_host_snapshot(topology: Topology, *, host_name: str, destination: Path) -> Path:
    """Write a deterministic, secret-free profile snapshot for one host."""

    if host_name not in topology.hosts:
        raise TopologyError(f"inventory host not found: {host_name}")
    errors = validate_topology(topology)
    if errors:
        raise TopologyError("invalid topology:\n" + "\n".join(errors))
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    hosted = [item for item in topology.all_components(enabled_only=True) if item.host == host_name]
    if not hosted:
        raise TopologyError(f"host {host_name} has no enabled components")

    copied: list[dict[str, str]] = []
    seen: set[Path] = set()
    for component in hosted:
        source = profile_path(topology.paths, component)
        if source in seen:
            continue
        profile = load_profile(topology.paths, component)
        finding = _contains_secret_value(profile)
        if finding:
            raise TopologyError(
                f"{component.qualified_id}: profile contains secret value at {finding}; use env: or seckit: reference"
            )
        relative = Path(PROFILE_DIR_BY_DRIVER[component.driver]) / source.name
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append({"path": str(relative), "sha256": _sha256(target)})
        seen.add(source)

    config_data = topology.config.data
    finding = _contains_secret_value(config_data)
    if finding:
        raise TopologyError(
            f"global configuration contains secret value at {finding}; use env: or seckit: reference"
        )
    config_path = destination / "config.json"
    config_path.write_text(json.dumps(config_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    copied.append({"path": "config.json", "sha256": _sha256(config_path)})

    host = topology.hosts[host_name]
    inventory_data = {
        "schema_version": 1,
        "hosts": [
            {
                "name": host.name,
                "role": host.role,
                "host": host.host,
                "user": host.user,
                "port": host.port,
                "install_root": host.install_root,
                "public_bin_dir": host.public_bin_dir,
                "config_profile": host.config_profile,
                "ssh_key": host.ssh_key,
                "proxy_jump": host.proxy_jump,
                "tags": list(host.tags),
                "transport": "local",
                "control_host": host.control_host or host.host,
                "trusted_control": host.trusted_control,
            }
        ],
    }
    inventory_path = destination / "inventory.json"
    inventory_path.write_text(
        json.dumps(inventory_data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    copied.append({"path": "inventory.json", "sha256": _sha256(inventory_path)})

    catalog_path = write_topology_catalog(topology, destination / "catalog.json")
    copied.append({"path": "catalog.json", "sha256": _sha256(catalog_path)})

    hosted_ids = {item.qualified_id for item in hosted}
    external_dependencies: dict[str, list[str]] = {}
    for stack_name in sorted(topology.stacks):
        stack_components = [item for item in hosted if item.stack == stack_name]
        if not stack_components:
            continue
        serialized: list[dict[str, Any]] = []
        for item in stack_components:
            local_dependencies = [dependency for dependency in item.depends_on if dependency in hosted_ids]
            remote_dependencies = [dependency for dependency in item.depends_on if dependency not in hosted_ids]
            if remote_dependencies:
                external_dependencies[item.qualified_id] = remote_dependencies
            serialized.append(
                {
                    "id": item.component_id,
                    "host": host_name,
                    "driver": item.driver,
                    "profile": item.profile,
                    "enabled": item.enabled,
                    "depends_on": local_dependencies,
                    "ownership": item.ownership,
                    "tags": list(item.tags),
                    "health": {
                        "type": item.health.kind,
                        "target": item.health.target,
                        "timeout_seconds": item.health.timeout_seconds,
                    },
                }
            )
        stack_path = destination / "stacks" / f"{stack_name}.json"
        stack_path.parent.mkdir(parents=True, exist_ok=True)
        stack_path.write_text(
            json.dumps(
                {"schema_version": 1, "name": stack_name, "components": serialized},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        copied.append(
            {"path": str(stack_path.relative_to(destination)), "sha256": _sha256(stack_path)}
        )
    snapshot = {
        "schema_version": 1,
        "host": host_name,
        "components": [
            {
                "id": item.qualified_id,
                "driver": item.driver,
                "profile": item.profile,
                "ownership": item.ownership,
                "tags": list(item.tags),
            }
            for item in hosted
        ],
        "external_dependencies": external_dependencies,
        "files": sorted(copied, key=lambda item: item["path"]),
    }
    snapshot_path = destination / "resolved.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return snapshot_path
