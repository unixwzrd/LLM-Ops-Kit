"""Transactional schema-driven template, profile, and component operations."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from jsonschema import Draft202012Validator

from .llmops_adapters import discover_adapters
from .llmops_paths import LlmOpsPaths
from .llmops_templates import (
    ServiceTemplate,
    TemplateError,
    flatten_schema,
    load_template_registry,
    parse_schema_value,
    schema_node,
    set_dotted,
    unset_dotted,
    validate_profile,
    validate_template_document,
)
from .llmops_topology import Topology, TopologyError, load_profile, profile_path, validate_topology


COMPONENT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "host": {"type": "string", "minLength": 1, "description": "Inventory host alias"},
        "execution_user": {"type": "string", "minLength": 1},
        "profile": {"type": "string", "minLength": 1},
        "template_id": {"type": "string", "minLength": 1},
        "ownership": {"type": "string", "enum": ["managed", "external"]},
        "restart_policy": {
            "type": "string",
            "enum": ["never", "on-failure"],
            "default": "never",
            "description": "Adapter supervision after an unexpected exit; explicit stops always win",
        },
        "enabled": {"type": "boolean"},
        "retired": {"type": "boolean", "readOnly": True},
        "tags": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "depends_on": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "health": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["driver", "http", "tcp", "none"]},
                "target": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 3600},
            },
        },
        "timeouts": {
            "type": "object",
            "properties": {
                action: {"type": "integer", "minimum": 1, "maximum": 86400}
                for action in ("start", "stop", "restart", "status", "logs")
            },
        },
    },
}


class ConfigOperationError(ValueError):
    """Raised when a schema-driven desired-state operation is invalid."""


@dataclass(frozen=True)
class ConfigChange:
    """One field-level old/new value in a configuration plan."""

    path: str
    old: Any
    new: Any


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigOperationError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigOperationError(f"configuration must be an object: {path}")
    return value


def _digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.json")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def authority_hash(paths: LlmOpsPaths) -> str:
    """Return the mutable authority-tree hash used for optimistic locking."""

    return _digest_tree(paths.config_home)


def migrate_schema_v2(
    paths: LlmOpsPaths,
    *,
    apply: bool,
    expected_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Plan or apply the one-time canonical v1-to-v2 configuration migration."""

    candidates = [paths.config_file, paths.inventory_file]
    candidates.extend(sorted(paths.models_dir.glob("*.json")) if paths.models_dir.is_dir() else [])
    candidates.extend(sorted(paths.agents_dir.glob("*.json")) if paths.agents_dir.is_dir() else [])
    candidates.extend(sorted(paths.services_dir.glob("*.json")) if paths.services_dir.is_dir() else [])
    candidates.extend(sorted(paths.stacks_dir.glob("*.json")) if paths.stacks_dir.is_dir() else [])
    documents = {path: _read_object(path) for path in candidates if path.is_file()}
    if not documents:
        raise ConfigOperationError(f"no canonical configuration found under: {paths.config_home}")

    profile_templates: dict[tuple[str, str], set[str]] = {}
    findings: list[str] = []
    registry = load_template_registry(paths)
    stack_paths = set(paths.stacks_dir.glob("*.json")) if paths.stacks_dir.is_dir() else set()
    for path in stack_paths:
        document = documents[path]
        for component in document.get("components", []):
            if not isinstance(component, dict):
                continue
            template_id = component.get("template_id") or infer_template_id(
                str(component.get("driver", "")), str(component.get("profile", ""))
            )
            component["template_id"] = template_id
            template = registry.get(str(template_id))
            component.setdefault(
                "restart_policy",
                template.restart_policy if template is not None else "never",
            )
            directory = {
                "modelctl": "models",
                "agent": "agents",
            }.get(str(component.get("driver", "")), "services")
            profile_templates.setdefault((directory, str(component.get("profile", ""))), set()).add(template_id)
        document["schema_version"] = 2

    profile_paths: set[Path] = set()
    for directory in (paths.models_dir, paths.agents_dir, paths.services_dir):
        if directory.is_dir():
            profile_paths.update(directory.glob("*.json"))
    for path in profile_paths:
        document = documents[path]
        choices = profile_templates.get((path.parent.name, path.stem), set())
        if len(choices) > 1:
            findings.append(f"{path}: profile is used by multiple template types: {', '.join(sorted(choices))}")
            continue
        if choices:
            template_id = next(iter(choices))
        elif path.parent == paths.models_dir:
            template_id = "llama-cpp"
        elif path.parent == paths.agents_dir:
            template_id = "generic-agent"
        elif path.stem in {"model-proxy", "tts-bridge", "rtk"}:
            template_id = path.stem
        else:
            findings.append(f"{path}: template requires operator review")
            continue
        document["schema_version"] = 2
        document["template_id"] = template_id
        document.setdefault("name", path.stem)
        template = registry.get(template_id)
        if template:
            findings.extend(f"{path}: {error}" for error in validate_profile(template, document))

    for path in (paths.config_file, paths.inventory_file):
        if path in documents:
            documents[path]["schema_version"] = 2

    changed = {
        path: document
        for path, document in documents.items()
        if json.loads(path.read_text(encoding="utf-8")) != document
    }
    payload = {
        "action": "schema-migrate-v2",
        "from_version": 1,
        "to_version": 2,
        "files": [str(path) for path in sorted(changed)],
        "findings": findings,
        "requires_review": bool(findings),
        "authority_hash": authority_hash(paths),
    }
    if not apply:
        return payload
    if findings:
        raise ConfigOperationError(
            "schema migration has unresolved review findings; correct them before apply:\n"
            + "\n".join(findings)
        )
    payload.update(
        _transactional_files(
            paths,
            changed,
            expected_hash=expected_hash,
            validate=lambda: None,
        )
    )
    payload["applied"] = True
    return payload


def _template_driver(template: ServiceTemplate) -> str:
    if template.template_id == "generic-agent":
        return "agent"
    if template.lifecycle in {"launchd-user", "external-launchd"}:
        return "launchd"
    if template.lifecycle == "ssh-tunnel":
        return "ssh-tunnel"
    if template.lifecycle == "systemd-user":
        return "systemd"
    manifest = discover_adapters()[template.adapter]
    if len(manifest.drivers) == 1:
        return manifest.drivers[0]
    if template.lifecycle in {"external", "tool", "standalone"}:
        return "process"
    raise ConfigOperationError(f"template does not resolve one driver: {template.template_id}")


def _profile_directory(paths: LlmOpsPaths, template: ServiceTemplate) -> Path:
    if template.profile_kind == "model":
        return paths.models_dir
    if template.profile_kind == "agent":
        return paths.agents_dir
    return paths.services_dir


def _transactional_files(
    paths: LlmOpsPaths,
    documents: Mapping[Path, Mapping[str, Any]],
    *,
    expected_hash: Optional[str],
    validate: Callable[[], None],
) -> dict[str, Any]:
    """Write several authority files atomically with validation and rollback."""

    before_hash = authority_hash(paths)
    if expected_hash and expected_hash != before_hash:
        raise ConfigOperationError(
            f"authority configuration changed: expected {expected_hash}, observed {before_hash}"
        )
    timestamp = time.strftime("%Y%m%dT%H%M%S")
    backups: dict[Path, Path] = {}
    temporaries: dict[Path, Path] = {}
    try:
        for path, document in documents.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
            temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temporaries[path] = temporary
            if path.exists():
                backup = path.with_name(f"{path.name}.backup-{timestamp}")
                shutil.copy2(path, backup)
                backups[path] = backup
        for path, temporary in temporaries.items():
            os.replace(temporary, path)
        validate()
    except Exception:
        for path in documents:
            backup = backups.get(path)
            if backup and backup.exists():
                os.replace(backup, path)
            elif path.exists() and path not in backups:
                path.unlink()
        for temporary in temporaries.values():
            temporary.unlink(missing_ok=True)
        raise
    return {
        "before_hash": before_hash,
        "after_hash": authority_hash(paths),
        "backups": {str(path): str(backup) for path, backup in backups.items()},
    }


def import_template(
    paths: LlmOpsPaths,
    source: Path,
    *,
    apply: bool,
    expected_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Plan or import one reviewed local template."""

    document = _read_object(source)
    template = validate_template_document(document, source=str(source))
    registry = load_template_registry(paths)
    if template.template_id in registry:
        raise ConfigOperationError(f"template already exists: {template.template_id}")
    destination = paths.templates_dir / f"{template.template_id}.json"
    payload = {
        "action": "template-import",
        "template": template.template_id,
        "source": str(source),
        "destination": str(destination),
        "authority_hash": authority_hash(paths),
    }
    if not apply:
        return payload
    payload.update(
        _transactional_files(
            paths,
            {destination: document},
            expected_hash=expected_hash,
            validate=lambda: load_template_registry(paths),
        )
    )
    payload["applied"] = True
    return payload


def field_records(
    template: ServiceTemplate,
    *,
    prefix: str = "profile",
    current: Optional[Mapping[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Return schema fields enriched with current values and source."""

    rows = flatten_schema(template.profile_schema)
    values = dict(current or {})
    for row in rows:
        target: Any = values
        for part in row["path"].split("."):
            if not isinstance(target, dict) or part not in target:
                target = None
                break
            target = target[part]
        row["path"] = f"{prefix}.{row['path']}"
        row["current"] = target
        row["source"] = "profile" if target is not None else "default"
    return rows


def component_field_records(
    topology: Topology,
    reference: str,
) -> list[dict[str, Any]]:
    """Return component, connection, and profile fields for one component."""

    component = topology.resolve_component(reference)
    _, _, raw_component = _component_source(topology, component.qualified_id)
    raw_profile = load_profile(topology.paths, component)
    template_id = (
        raw_component.get("template_id")
        or raw_profile.get("template_id")
        or infer_template_id(component.driver, component.profile)
    )
    template = load_template_registry(topology.paths).get(str(template_id))
    if template is None:
        raise ConfigOperationError(f"template not found for component: {template_id}")
    rows = _schema_field_records(COMPONENT_SCHEMA, prefix="component", current=raw_component)
    rows.extend(field_records(template, current=raw_profile))
    for name, value in sorted(component.connections.items()):
        for field_name in ("component", "endpoint"):
            rows.append(
                {
                    "path": f"connections.{name}.{field_name}",
                    "type": "string",
                    "required": True,
                    "default": None,
                    "allowed": None,
                    "description": f"Typed endpoint connection {name} {field_name}",
                    "group": "Connections",
                    "order": 100,
                    "widget": "endpoint",
                    "advanced": False,
                    "current": value.get(field_name),
                    "source": "component",
                }
            )
    return sorted(rows, key=lambda row: (row["group"], row["order"], row["path"]))


def _schema_field_records(
    schema: Mapping[str, Any],
    *,
    prefix: str,
    current: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows = flatten_schema(schema)
    for row in rows:
        value = _get_dotted(current, row["path"])
        row["path"] = f"{prefix}.{row['path']}"
        row["current"] = value
        row["source"] = "component" if value is not None else "default"
    return rows


def find_profile(paths: LlmOpsPaths, name: str) -> tuple[Path, dict[str, Any]]:
    """Find one unambiguous profile across model, agent, and service roots."""

    matches = [
        directory / f"{name}.json"
        for directory in (paths.models_dir, paths.agents_dir, paths.services_dir)
        if (directory / f"{name}.json").is_file()
    ]
    if not matches:
        raise ConfigOperationError(f"profile not found: {name}")
    if len(matches) > 1:
        raise ConfigOperationError(
            f"ambiguous profile {name!r}: " + ", ".join(str(path) for path in matches)
        )
    return matches[0], _read_object(matches[0])


def profile_template(paths: LlmOpsPaths, name: str) -> tuple[ServiceTemplate, Path, dict[str, Any]]:
    """Resolve one profile and its declared or inferred template."""

    path, document = find_profile(paths, name)
    template_id = document.get("template_id")
    if not template_id:
        directory_kind = path.parent.name
        if directory_kind == "models":
            template_id = "llama-cpp"
        elif directory_kind == "agents":
            template_id = "generic-agent"
        else:
            template_id = infer_template_id("process", name)
    template = load_template_registry(paths).get(str(template_id))
    if template is None:
        raise ConfigOperationError(f"template not found for profile {name}: {template_id}")
    return template, path, document


def template_action_argv(
    topology: Topology,
    reference: str,
    action: str,
) -> tuple[ServiceTemplate, list[str], bool]:
    """Resolve a registered adapter-owned action to a validated argument array."""

    component = topology.resolve_component(reference)
    profile = load_profile(topology.paths, component)
    template_id = component.template_id or profile.get("template_id") or infer_template_id(
        component.driver, component.profile
    )
    template = load_template_registry(topology.paths).get(str(template_id))
    if template is None:
        raise ConfigOperationError(f"template not found for component: {template_id}")
    definition = template.actions.get(action)
    if not isinstance(definition, dict):
        choices = ", ".join(sorted(template.actions)) or "none"
        raise ConfigOperationError(f"action not available for {component.qualified_id}: {action}; choose: {choices}")
    argv: list[str] = []
    for token in definition.get("argv", []):
        if token.startswith("{profile.") and token.endswith("}"):
            path = token[len("{profile.") : -1]
            value = _get_dotted(profile, path)
            if not isinstance(value, (str, int, float)) or value == "":
                raise ConfigOperationError(f"action {action} cannot resolve profile.{path}")
            argv.append(str(Path(value).expanduser()) if path.endswith(("path", "executable")) else str(value))
        elif "{" in token or "}" in token:
            raise ConfigOperationError(f"unsupported action placeholder: {token}")
        else:
            argv.append(token)
    return template, argv, bool(definition.get("mutating", False))


def _parse_assignment(specification: str) -> tuple[str, str]:
    path, separator, raw = specification.partition("=")
    if not separator or not path:
        raise ConfigOperationError(f"assignment must be path=value: {specification!r}")
    return path, raw


def mutate_documents(
    *,
    component: dict[str, Any],
    profile: dict[str, Any],
    template: ServiceTemplate,
    assignments: Iterable[str],
    unsets: Iterable[str],
) -> tuple[dict[str, Any], dict[str, Any], list[ConfigChange]]:
    """Apply schema-aware dotted mutations to component/profile candidates."""

    candidate_component = copy.deepcopy(component)
    candidate_profile = copy.deepcopy(profile)
    changes: list[ConfigChange] = []
    for specification in assignments:
        path, raw = _parse_assignment(specification)
        root, separator, relative = path.partition(".")
        if not separator or root not in {"component", "profile", "connections"}:
            raise ConfigOperationError(f"unsupported assignment root: {path}")
        if root == "profile":
            node = schema_node(template.profile_schema, relative)
            if node.get("readOnly"):
                raise ConfigOperationError(f"field is read-only: {path}")
            target = candidate_profile
        elif root == "component":
            node = schema_node(COMPONENT_SCHEMA, relative)
            if node.get("readOnly"):
                raise ConfigOperationError(f"field is read-only: {path}")
            target = candidate_component
        else:
            parts = relative.split(".")
            if len(parts) != 2 or parts[-1] not in {"component", "endpoint"}:
                raise ConfigOperationError(
                    "connection paths must be connections.<name>.component or connections.<name>.endpoint"
                )
            node = {"type": "string", "minLength": 1}
            target = candidate_component.setdefault("connections", {})
            relative = ".".join(parts)
        old = copy.deepcopy(_get_dotted(target, relative))
        value = parse_schema_value(node, raw)
        set_dotted(target, relative, value)
        changes.append(ConfigChange(path, old, value))
    for path in unsets:
        root, separator, relative = path.partition(".")
        if not separator or root not in {"component", "profile", "connections"}:
            raise ConfigOperationError(f"unsupported unset root: {path}")
        target = candidate_profile if root == "profile" else candidate_component
        actual = relative if root != "connections" else f"connections.{relative}"
        old = copy.deepcopy(_get_dotted(target, actual))
        if old is None:
            raise ConfigOperationError(f"field is not set: {path}")
        node = (
            schema_node(template.profile_schema, relative)
            if root == "profile"
            else schema_node(COMPONENT_SCHEMA, relative)
            if root == "component"
            else {}
        )
        if "default" in node:
            replacement = copy.deepcopy(node["default"])
            set_dotted(target, actual, replacement)
        else:
            unset_dotted(target, actual)
            replacement = None
        changes.append(ConfigChange(path, old, replacement))
    errors = validate_profile(template, candidate_profile)
    if errors:
        raise ConfigOperationError("invalid profile:\n" + "\n".join(errors))
    component_errors = sorted(
        Draft202012Validator(COMPONENT_SCHEMA).iter_errors(candidate_component),
        key=lambda item: list(item.absolute_path),
    )
    if component_errors:
        findings = []
        for finding in component_errors:
            path = ".".join(str(item) for item in finding.absolute_path) or "component"
            findings.append(f"{path}: {finding.message}")
        raise ConfigOperationError("invalid component:\n" + "\n".join(findings))
    for connection in candidate_component.get("connections", {}).values():
        target = str(connection.get("component", ""))
        if target and target not in candidate_component.setdefault("depends_on", []):
            candidate_component["depends_on"].append(target)
    return candidate_component, candidate_profile, changes


def _get_dotted(document: Mapping[str, Any], path: str) -> Any:
    target: Any = document
    for part in path.split(".") if path else []:
        if not isinstance(target, Mapping) or part not in target:
            return None
        target = target[part]
    return target


def _component_source(topology: Topology, qualified_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    component = topology.resolve_component(qualified_id)
    path = topology.stacks[component.stack].path
    stack = _read_object(path)
    raw = next(item for item in stack["components"] if item.get("id") == component.component_id)
    return path, stack, raw


def configure_component_schema(
    topology: Topology,
    reference: str,
    *,
    assignments: Iterable[str],
    unsets: Iterable[str],
    apply: bool,
    expected_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Plan or apply one atomic component/profile configuration mutation."""

    component = topology.resolve_component(reference)
    stack_path, stack, raw_component = _component_source(topology, component.qualified_id)
    raw_profile = load_profile(topology.paths, component)
    registry = load_template_registry(topology.paths)
    template_id = raw_component.get("template_id") or raw_profile.get("template_id") or infer_template_id(component.driver, component.profile)
    if template_id not in registry:
        raise ConfigOperationError(f"template not found for component: {template_id}")
    template = registry[template_id]
    candidate_component, candidate_profile, changes = mutate_documents(
        component=raw_component,
        profile=raw_profile,
        template=template,
        assignments=assignments,
        unsets=unsets,
    )
    candidate_component["template_id"] = template_id
    candidate_profile["template_id"] = template_id
    candidate_stack = copy.deepcopy(stack)
    for index, item in enumerate(candidate_stack["components"]):
        if item.get("id") == component.component_id:
            candidate_stack["components"][index] = candidate_component
            break
    profile_source = profile_path(topology.paths, component)
    affected = sorted(
        item.qualified_id
        for item in topology.all_components()
        if item.driver == component.driver and item.profile == component.profile
    )
    payload = {
        "action": "component-configure",
        "component": component.qualified_id,
        "template": template_id,
        "changes": [change.__dict__ for change in changes],
        "affected_components": affected,
        "files": [str(stack_path), str(profile_source)],
        "authority_hash": authority_hash(topology.paths),
        "restart_affected": False,
    }
    if not apply:
        return payload

    payload.update(
        _transactional_files(
            topology.paths,
            {stack_path: candidate_stack, profile_source: candidate_profile},
            expected_hash=expected_hash,
            validate=lambda: _validate_rebuilt(topology),
        )
    )
    payload["applied"] = True
    return payload


def _rebuild(topology: Topology) -> Topology:
    from .llmops_cli import build_topology

    return build_topology(
        config_home=str(topology.paths.config_home),
        inventory=str(topology.paths.inventory_file),
    )


def infer_template_id(driver: str, profile: str = "") -> str:
    """Map existing version-one components to built-in templates."""

    mapping = {
        "agent": "generic-agent",
        "command": "standalone",
        "launchd": "launchd-external",
        "model-proxy": "model-proxy",
        "modelctl": "llama-cpp",
        "process": "rtk" if profile == "rtk" else "standalone",
        "ssh-tunnel": "ssh-tunnel",
        "systemd": "systemd-user",
        "tts-bridge": "tts-bridge",
    }
    if driver not in mapping:
        raise ConfigOperationError(f"cannot infer template for driver: {driver}")
    return mapping[driver]


def create_profile(
    paths: LlmOpsPaths,
    *,
    name: str,
    template_id: str,
    values: Optional[Mapping[str, Any]],
    apply: bool,
    expected_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Plan or create one reusable named profile."""

    if not name or "/" in name or name in {".", ".."}:
        raise ConfigOperationError(f"invalid profile name: {name!r}")
    template = load_template_registry(paths).get(template_id)
    if template is None:
        raise ConfigOperationError(f"template not found: {template_id}")
    document = copy.deepcopy(template.defaults)
    document.update(copy.deepcopy(dict(values or {})))
    document["name"] = name
    document["schema_version"] = 2
    document["template_id"] = template_id
    errors = validate_profile(template, document)
    if errors:
        raise ConfigOperationError("invalid profile:\n" + "\n".join(errors))
    destination = _profile_directory(paths, template) / f"{name}.json"
    if destination.exists():
        raise ConfigOperationError(f"profile already exists: {name}")
    payload = {"action": "profile-create", "profile": name, "template": template_id, "path": str(destination), "authority_hash": authority_hash(paths)}
    if apply:
        payload.update(_transactional_files(paths, {destination: document}, expected_hash=expected_hash, validate=lambda: None))
        payload["applied"] = True
    return payload


def edit_profile(
    topology: Topology,
    name: str,
    *,
    assignments: Iterable[str],
    unsets: Iterable[str],
    apply: bool,
    expected_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Plan or atomically edit one reusable profile."""

    template, path, document = profile_template(topology.paths, name)
    candidate = copy.deepcopy(document)
    changes: list[ConfigChange] = []
    for specification in assignments:
        raw_path, raw = _parse_assignment(specification)
        relative = raw_path.removeprefix("profile.")
        if raw_path != relative and not relative:
            raise ConfigOperationError(f"invalid profile field: {raw_path}")
        node = schema_node(template.profile_schema, relative)
        if node.get("readOnly"):
            raise ConfigOperationError(f"field is read-only: profile.{relative}")
        old = copy.deepcopy(_get_dotted(candidate, relative))
        value = parse_schema_value(node, raw)
        set_dotted(candidate, relative, value)
        changes.append(ConfigChange(f"profile.{relative}", old, value))
    for raw_path in unsets:
        relative = raw_path.removeprefix("profile.")
        node = schema_node(template.profile_schema, relative)
        if node.get("readOnly"):
            raise ConfigOperationError(f"field is read-only: profile.{relative}")
        old = copy.deepcopy(_get_dotted(candidate, relative))
        if old is None:
            raise ConfigOperationError(f"field is not set: profile.{relative}")
        if "default" in node:
            replacement = copy.deepcopy(node["default"])
            set_dotted(candidate, relative, replacement)
        else:
            if not unset_dotted(candidate, relative):
                raise ConfigOperationError(f"field is not set: profile.{relative}")
            replacement = None
        changes.append(ConfigChange(f"profile.{relative}", old, replacement))
    errors = validate_profile(template, candidate)
    if errors:
        raise ConfigOperationError("invalid profile:\n" + "\n".join(errors))
    affected = sorted(
        component.qualified_id
        for component in topology.all_components()
        if component.profile == name
    )
    payload = {
        "action": "profile-edit",
        "profile": name,
        "template": template.template_id,
        "changes": [change.__dict__ for change in changes],
        "affected_components": affected,
        "shared_profile": len(affected) > 1,
        "path": str(path),
        "authority_hash": authority_hash(topology.paths),
    }
    if apply:
        payload.update(
            _transactional_files(
                topology.paths,
                {path: candidate},
                expected_hash=expected_hash,
                validate=lambda: _validate_rebuilt(topology),
            )
        )
        payload["applied"] = True
    return payload


def clone_profile(
    paths: LlmOpsPaths,
    source_name: str,
    new_name: str,
    *,
    apply: bool,
    expected_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Plan or clone a reusable profile without changing its source."""

    template, source, document = profile_template(paths, source_name)
    destination = _profile_directory(paths, template) / f"{new_name}.json"
    if destination.exists():
        raise ConfigOperationError(f"profile already exists: {new_name}")
    candidate = copy.deepcopy(document)
    candidate["name"] = new_name
    errors = validate_profile(template, candidate)
    if errors:
        raise ConfigOperationError("invalid cloned profile:\n" + "\n".join(errors))
    payload = {
        "action": "profile-clone",
        "source": source_name,
        "profile": new_name,
        "template": template.template_id,
        "source_path": str(source),
        "path": str(destination),
        "authority_hash": authority_hash(paths),
    }
    if apply:
        payload.update(
            _transactional_files(
                paths,
                {destination: candidate},
                expected_hash=expected_hash,
                validate=lambda: None,
            )
        )
        payload["applied"] = True
    return payload


def add_component(
    topology: Topology,
    *,
    component_id: str,
    stack_name: str,
    template_id: str,
    profile_name: str,
    host: str,
    execution_user: str = "",
    connections: Optional[Mapping[str, Mapping[str, str]]] = None,
    dependencies: Iterable[str] = (),
    apply: bool,
    expected_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Plan or add a component bound to an existing compatible profile."""

    if stack_name not in topology.stacks:
        raise ConfigOperationError(f"stack not found: {stack_name}")
    if host not in topology.hosts:
        raise ConfigOperationError(f"host not found: {host}")
    registry = load_template_registry(topology.paths)
    template = registry.get(template_id)
    if template is None:
        raise ConfigOperationError(f"template not found: {template_id}")
    profile_file = _profile_directory(topology.paths, template) / f"{profile_name}.json"
    if not profile_file.is_file():
        raise ConfigOperationError(f"profile not found: {profile_name}")
    errors = validate_profile(template, _read_object(profile_file))
    if errors:
        raise ConfigOperationError("incompatible profile:\n" + "\n".join(errors))
    stack_path = topology.stacks[stack_name].path
    stack = _read_object(stack_path)
    if any(item.get("id") == component_id for item in stack["components"]):
        raise ConfigOperationError(f"component already exists: {stack_name}:{component_id}")
    component = {
        "id": component_id,
        "host": host,
        "driver": _template_driver(template),
        "template_id": template_id,
        "profile": profile_name,
        "enabled": False,
        "retired": False,
        "ownership": "external" if template.lifecycle in {"external", "external-launchd", "tool"} else "managed",
        "restart_policy": template.restart_policy,
        "depends_on": list(dict.fromkeys(dependencies)),
        "connections": copy.deepcopy(dict(connections or {})),
    }
    if execution_user:
        component["execution_user"] = execution_user
    for connection in component["connections"].values():
        target = str(connection.get("component", ""))
        if target and target not in component["depends_on"]:
            component["depends_on"].append(target)
    stack["components"].append(component)
    payload = {"action": "component-add", "component": f"{stack_name}:{component_id}", "template": template_id, "profile": profile_name, "host": host, "path": str(stack_path), "authority_hash": authority_hash(topology.paths)}
    if apply:
        payload.update(
            _transactional_files(
                topology.paths,
                {stack_path: stack},
                expected_hash=expected_hash,
                validate=lambda: _validate_rebuilt(topology),
            )
        )
        payload["applied"] = True
    return payload


def provision_component(
    topology: Topology,
    *,
    component_id: str,
    stack_name: str,
    template_id: str,
    profile_name: str,
    host: str,
    execution_user: str = "",
    connections: Optional[Mapping[str, Mapping[str, str]]] = None,
    dependencies: Iterable[str] = (),
    profile_values: Optional[Mapping[str, Any]] = None,
    create_new_profile: bool = False,
    apply: bool,
    expected_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Plan or atomically create/reuse a profile and add one disabled component."""

    if stack_name not in topology.stacks:
        raise ConfigOperationError(f"stack not found: {stack_name}")
    if host not in topology.hosts:
        raise ConfigOperationError(f"host not found: {host}")
    template = load_template_registry(topology.paths).get(template_id)
    if template is None:
        raise ConfigOperationError(f"template not found: {template_id}")
    profile_path_value = _profile_directory(topology.paths, template) / f"{profile_name}.json"
    documents: dict[Path, Mapping[str, Any]] = {}
    if create_new_profile:
        if profile_path_value.exists():
            raise ConfigOperationError(f"profile already exists: {profile_name}")
        profile_document = copy.deepcopy(template.defaults)
        profile_document.update(copy.deepcopy(dict(profile_values or {})))
        profile_document.update(
            {"schema_version": 2, "template_id": template_id, "name": profile_name}
        )
        errors = validate_profile(template, profile_document)
        if errors:
            raise ConfigOperationError("invalid profile:\n" + "\n".join(errors))
        documents[profile_path_value] = profile_document
    elif not profile_path_value.is_file():
        raise ConfigOperationError(f"profile not found: {profile_name}")

    stack_path = topology.stacks[stack_name].path
    stack = _read_object(stack_path)
    if any(item.get("id") == component_id for item in stack["components"]):
        raise ConfigOperationError(f"component already exists: {stack_name}:{component_id}")
    component = {
        "id": component_id,
        "host": host,
        "driver": _template_driver(template),
        "template_id": template_id,
        "profile": profile_name,
        "enabled": False,
        "retired": False,
        "ownership": "external" if template.lifecycle in {"external", "external-launchd", "tool"} else "managed",
        "restart_policy": template.restart_policy,
        "depends_on": list(dict.fromkeys(dependencies)),
        "connections": copy.deepcopy(dict(connections or {})),
    }
    if execution_user:
        component["execution_user"] = execution_user
    for connection in component["connections"].values():
        target = str(connection.get("component", ""))
        if target and target not in component["depends_on"]:
            component["depends_on"].append(target)
    stack["components"].append(component)
    documents[stack_path] = stack
    payload = {
        "action": "component-provision",
        "component": f"{stack_name}:{component_id}",
        "template": template_id,
        "profile": profile_name,
        "profile_mode": "created" if create_new_profile else "reused",
        "host": host,
        "execution_user": execution_user or topology.hosts[host].user,
        "files": [str(path) for path in documents],
        "authority_hash": authority_hash(topology.paths),
    }
    if apply:
        payload.update(
            _transactional_files(
                topology.paths,
                documents,
                expected_hash=expected_hash,
                validate=lambda: _validate_rebuilt(topology),
            )
        )
        payload["applied"] = True
    return payload


def clone_component(
    topology: Topology,
    reference: str,
    new_id: str,
    *,
    share_profile: bool,
    apply: bool,
    expected_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Plan or clone a component, optionally cloning its reusable profile."""

    source_component = topology.resolve_component(reference)
    stack_path, stack, raw = _component_source(topology, source_component.qualified_id)
    if any(item.get("id") == new_id for item in stack["components"]):
        raise ConfigOperationError(f"component already exists: {source_component.stack}:{new_id}")
    candidate_component = copy.deepcopy(raw)
    candidate_component["id"] = new_id
    candidate_component["enabled"] = False
    candidate_component["retired"] = False
    documents: dict[Path, Mapping[str, Any]] = {}
    profile_name = source_component.profile
    if not share_profile:
        template, source_path, profile_document = profile_template(topology.paths, profile_name)
        profile_name = new_id
        destination = _profile_directory(topology.paths, template) / f"{profile_name}.json"
        if destination.exists():
            raise ConfigOperationError(f"profile already exists: {profile_name}")
        cloned_profile = copy.deepcopy(profile_document)
        cloned_profile["name"] = profile_name
        candidate_component["profile"] = profile_name
        documents[destination] = cloned_profile
    stack["components"].append(candidate_component)
    documents[stack_path] = stack
    payload = {
        "action": "component-clone",
        "source": source_component.qualified_id,
        "component": f"{source_component.stack}:{new_id}",
        "profile": profile_name,
        "profile_mode": "shared" if share_profile else "cloned",
        "files": [str(path) for path in documents],
        "authority_hash": authority_hash(topology.paths),
    }
    if apply:
        payload.update(
            _transactional_files(
                topology.paths,
                documents,
                expected_hash=expected_hash,
                validate=lambda: _validate_rebuilt(topology),
            )
        )
        payload["applied"] = True
    return payload


def _validate_rebuilt(topology: Topology) -> None:
    refreshed = _rebuild(topology)
    errors = validate_topology(refreshed)
    errors.extend(validate_connections(refreshed))
    if errors:
        raise ConfigOperationError("invalid topology:\n" + "\n".join(errors))


def validate_connections(topology: Topology) -> list[str]:
    """Validate typed endpoint references and implied lifecycle dependencies."""

    registry = load_template_registry(topology.paths)
    errors: list[str] = []
    for component in topology.all_components():
        if not component.connections:
            continue
        template_id = component.template_id or infer_template_id(component.driver, component.profile)
        consumer = registry.get(template_id)
        if consumer is None:
            errors.append(f"{component.qualified_id}: template not found: {template_id}")
            continue
        required = consumer.endpoints.get("requires", {})
        for name, connection in component.connections.items():
            requirement = required.get(name)
            if not isinstance(requirement, dict):
                errors.append(f"{component.qualified_id}: undeclared required endpoint: {name}")
                continue
            target_ref = connection.get("component", "")
            if ":" not in target_ref:
                target_ref = f"{component.stack}:{target_ref}"
            try:
                provider_component = topology.resolve_component(target_ref)
            except TopologyError as exc:
                errors.append(f"{component.qualified_id}: connection {name}: {exc}")
                continue
            provider_id = provider_component.template_id or infer_template_id(
                provider_component.driver, provider_component.profile
            )
            provider = registry.get(provider_id)
            endpoint_name = connection.get("endpoint", "")
            provided = provider.endpoints.get("provides", {}) if provider else {}
            if endpoint_name not in provided:
                errors.append(
                    f"{component.qualified_id}: connection {name}: "
                    f"{provider_component.qualified_id} does not provide {endpoint_name}"
                )
            protocol = requirement.get("protocol")
            if protocol and protocol != endpoint_name:
                errors.append(
                    f"{component.qualified_id}: connection {name}: expected protocol {protocol}, got {endpoint_name}"
                )
            if requirement.get("lifecycle_dependency", True) and provider_component.qualified_id not in component.depends_on:
                errors.append(
                    f"{component.qualified_id}: connection {name} requires dependency {provider_component.qualified_id}"
                )
    return errors


def retire_component(
    topology: Topology,
    reference: str,
    *,
    restore: bool,
    apply: bool,
    expected_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Plan or change a component's reversible retired state."""

    component = topology.resolve_component(reference)
    if not restore:
        dependents = [
            item.qualified_id for item in topology.all_components() if component.qualified_id in item.depends_on and not item.retired
        ]
        if dependents:
            raise ConfigOperationError("component has active dependents: " + ", ".join(sorted(dependents)))
    stack_path, stack, raw = _component_source(topology, component.qualified_id)
    raw["retired"] = not restore
    raw["enabled"] = False
    payload = {
        "action": "component-restore" if restore else "component-retire",
        "component": component.qualified_id,
        "path": str(stack_path),
        "authority_hash": authority_hash(topology.paths),
        "requires_stop": not restore and component.enabled,
        "preserves_profile": True,
    }
    if apply:
        payload.update(_transactional_files(topology.paths, {stack_path: stack}, expected_hash=expected_hash, validate=lambda: _validate_rebuilt(topology)))
        payload["applied"] = True
    return payload
