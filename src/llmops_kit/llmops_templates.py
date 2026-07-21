"""Versioned service-template registry and schema-aware value handling."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from .llmops_adapters import discover_adapters
from .llmops_paths import LlmOpsPaths


TEMPLATE_VERSION = 1
TEMPLATE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
ALLOWED_UI_WIDGETS = {
    "argv",
    "checkbox",
    "duration",
    "endpoint",
    "number",
    "path",
    "secret-reference",
    "select",
    "text",
}
ALLOWED_OPTION_SOURCES = {"components", "endpoints", "hosts", "profiles", "stacks"}
ALLOWED_LIFECYCLES = {
    "external",
    "external-launchd",
    "launchd-user",
    "ssh-tunnel",
    "standalone",
    "systemd-user",
    "tool",
}


class TemplateError(ValueError):
    """Raised when a service template or schema-aware value is invalid."""


@dataclass(frozen=True)
class ServiceTemplate:
    """One validated built-in or operator-imported service template."""

    template_id: str
    version: str
    adapter: str
    profile_kind: str
    component_kind: str
    platforms: tuple[str, ...]
    lifecycle: str
    restart_policy: str
    profile_schema: dict[str, Any]
    defaults: dict[str, Any]
    bindings: dict[str, Any]
    endpoints: dict[str, Any]
    logs: dict[str, Any]
    actions: dict[str, Any]
    source: str
    experimental: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation."""

        return {
            "template_version": TEMPLATE_VERSION,
            "id": self.template_id,
            "version": self.version,
            "adapter": self.adapter,
            "profile_kind": self.profile_kind,
            "component_kind": self.component_kind,
            "platforms": list(self.platforms),
            "lifecycle": self.lifecycle,
            "restart_policy": self.restart_policy,
            "profile_schema": copy.deepcopy(self.profile_schema),
            "defaults": copy.deepcopy(self.defaults),
            "bindings": copy.deepcopy(self.bindings),
            "endpoints": copy.deepcopy(self.endpoints),
            "logs": copy.deepcopy(self.logs),
            "actions": copy.deepcopy(self.actions),
            "experimental": self.experimental,
            "source": self.source,
        }


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TemplateError(f"cannot read template {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TemplateError(f"template must be a JSON object: {path}")
    return payload


def _validate_ui_metadata(node: Any, *, path: str = "profile_schema") -> None:
    if isinstance(node, dict):
        metadata = node.get("x-llmops-ui")
        if metadata is not None:
            if not isinstance(metadata, dict):
                raise TemplateError(f"{path}.x-llmops-ui must be an object")
            widget = metadata.get("widget")
            if widget is not None and widget not in ALLOWED_UI_WIDGETS:
                raise TemplateError(f"{path}: unsupported UI widget: {widget}")
            source = metadata.get("options_source")
            if source is not None and source not in ALLOWED_OPTION_SOURCES:
                raise TemplateError(f"{path}: unsupported option source: {source}")
        for key, value in node.items():
            _validate_ui_metadata(value, path=f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _validate_ui_metadata(value, path=f"{path}[{index}]")


def validate_template_document(
    document: Mapping[str, Any],
    *,
    source: str,
    adapters: Optional[Mapping[str, Any]] = None,
) -> ServiceTemplate:
    """Validate and normalize one service-template document."""

    required = {
        "template_version",
        "id",
        "version",
        "adapter",
        "profile_kind",
        "component_kind",
        "platforms",
        "lifecycle",
        "profile_schema",
        "defaults",
    }
    missing = sorted(required - set(document))
    if missing:
        raise TemplateError(f"{source}: missing template fields: {', '.join(missing)}")
    if document["template_version"] != TEMPLATE_VERSION:
        raise TemplateError(f"{source}: unsupported template_version: {document['template_version']}")
    template_id = document["id"]
    if not isinstance(template_id, str) or not TEMPLATE_ID_PATTERN.fullmatch(template_id):
        raise TemplateError(f"{source}: invalid template ID: {template_id!r}")
    adapter = document["adapter"]
    registry = dict(adapters or discover_adapters())
    if adapter not in registry:
        raise TemplateError(f"{source}: adapter is not registered: {adapter}")
    lifecycle = document["lifecycle"]
    if lifecycle not in ALLOWED_LIFECYCLES:
        raise TemplateError(f"{source}: unsupported lifecycle: {lifecycle}")
    restart_policy = document.get("restart_policy", "never")
    if restart_policy not in {"never", "on-failure"}:
        raise TemplateError(f"{source}: unsupported restart_policy: {restart_policy}")
    platforms = document["platforms"]
    if not isinstance(platforms, list) or not platforms or any(not isinstance(item, str) for item in platforms):
        raise TemplateError(f"{source}: platforms must be a nonempty string array")
    schema = document["profile_schema"]
    defaults = document["defaults"]
    if not isinstance(schema, dict) or not isinstance(defaults, dict):
        raise TemplateError(f"{source}: profile_schema and defaults must be objects")
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(defaults)
    except (SchemaError, ValidationError) as exc:
        raise TemplateError(f"{source}: invalid profile schema/defaults: {exc.message}") from exc
    _validate_ui_metadata(schema)
    for key in ("bindings", "endpoints", "logs", "actions"):
        value = document.get(key, {})
        if not isinstance(value, dict):
            raise TemplateError(f"{source}: {key} must be an object")
    for action, definition in document.get("actions", {}).items():
        if not isinstance(definition, dict):
            raise TemplateError(f"{source}: action {action} must be an object")
        argv = definition.get("argv", [])
        if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
            raise TemplateError(f"{source}: action {action}.argv must be a string array")
    return ServiceTemplate(
        template_id=template_id,
        version=str(document["version"]),
        adapter=str(adapter),
        profile_kind=str(document["profile_kind"]),
        component_kind=str(document["component_kind"]),
        platforms=tuple(platforms),
        lifecycle=str(lifecycle),
        restart_policy=str(restart_policy),
        profile_schema=copy.deepcopy(schema),
        defaults=copy.deepcopy(defaults),
        bindings=copy.deepcopy(document.get("bindings", {})),
        endpoints=copy.deepcopy(document.get("endpoints", {})),
        logs=copy.deepcopy(document.get("logs", {})),
        actions=copy.deepcopy(document.get("actions", {})),
        source=source,
        experimental=bool(document.get("experimental", False)),
    )


def builtin_template_documents() -> Iterable[tuple[str, dict[str, Any]]]:
    """Yield bundled template documents without requiring a source checkout."""

    root = resources.files("llmops_kit").joinpath("resources/service_templates")
    for item in sorted(root.iterdir(), key=lambda entry: entry.name):
        if item.name.endswith(".json"):
            payload = json.loads(item.read_text(encoding="utf-8"))
            yield f"builtin:{item.name}", payload


def load_template_registry(paths: LlmOpsPaths) -> dict[str, ServiceTemplate]:
    """Load built-ins followed by reviewed authority-local templates."""

    registry: dict[str, ServiceTemplate] = {}
    for source, document in builtin_template_documents():
        template = validate_template_document(document, source=source)
        registry[template.template_id] = template
    if paths.templates_dir.is_dir():
        for path in sorted(paths.templates_dir.glob("*.json")):
            template = validate_template_document(_load_object(path), source=str(path))
            if template.template_id in registry:
                raise TemplateError(f"duplicate template ID: {template.template_id}")
            registry[template.template_id] = template
    return registry


def validate_profile(template: ServiceTemplate, profile: Mapping[str, Any]) -> list[str]:
    """Return every deterministic profile-schema violation."""

    errors: list[str] = []
    validator = Draft202012Validator(template.profile_schema)
    for finding in sorted(validator.iter_errors(dict(profile)), key=lambda item: list(item.absolute_path)):
        path = ".".join(str(item) for item in finding.absolute_path) or "profile"
        errors.append(f"{path}: {finding.message}")
    return errors


def schema_node(schema: Mapping[str, Any], dotted_path: str) -> dict[str, Any]:
    """Resolve one dotted property path in an object schema."""

    node: Mapping[str, Any] = schema
    for part in dotted_path.split(".") if dotted_path else []:
        properties = node.get("properties", {})
        if not isinstance(properties, dict) or part not in properties:
            raise TemplateError(f"unknown schema field: {dotted_path}")
        child = properties[part]
        if not isinstance(child, dict):
            raise TemplateError(f"invalid schema field: {dotted_path}")
        node = child
    return dict(node)


def parse_schema_value(node: Mapping[str, Any], raw: str) -> Any:
    """Parse one CLI value according to its declared JSON Schema type."""

    declared = node.get("type")
    try:
        if declared == "boolean":
            if raw.lower() not in {"true", "false"}:
                raise ValueError("expected true or false")
            value: Any = raw.lower() == "true"
        elif declared == "integer":
            value = int(raw)
        elif declared == "number":
            value = float(raw)
        elif declared in {"array", "object"}:
            value = json.loads(raw)
        elif declared == "null":
            if raw.lower() != "null":
                raise ValueError("expected null")
            value = None
        else:
            value = raw
        Draft202012Validator(node).validate(value)
        return value
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        message = exc.message if isinstance(exc, ValidationError) else str(exc)
        raise TemplateError(f"invalid value {raw!r}: {message}") from exc


def set_dotted(document: dict[str, Any], path: str, value: Any) -> None:
    """Set a dotted object path, creating only intermediate objects."""

    parts = path.split(".")
    if not parts or any(not part for part in parts):
        raise TemplateError(f"invalid dotted path: {path!r}")
    target = document
    for part in parts[:-1]:
        existing = target.setdefault(part, {})
        if not isinstance(existing, dict):
            raise TemplateError(f"cannot descend through non-object field: {part}")
        target = existing
    target[parts[-1]] = value


def unset_dotted(document: dict[str, Any], path: str) -> bool:
    """Remove one dotted object path and return whether it existed."""

    parts = path.split(".")
    target: Any = document
    for part in parts[:-1]:
        if not isinstance(target, dict) or part not in target:
            return False
        target = target[part]
    if not isinstance(target, dict) or parts[-1] not in target:
        return False
    del target[parts[-1]]
    return True


def flatten_schema(
    schema: Mapping[str, Any],
    *,
    prefix: str = "",
    required: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Flatten object properties into stable field-inspection records."""

    rows: list[dict[str, Any]] = []
    required_here = set(schema.get("required", []))
    dependent = schema.get("dependentRequired", {})
    constraints = schema.get("allOf", [])
    for name, raw in schema.get("properties", {}).items():
        if not isinstance(raw, dict):
            continue
        path = f"{prefix}.{name}" if prefix else name
        if raw.get("type") == "object" and isinstance(raw.get("properties"), dict):
            rows.extend(flatten_schema(raw, prefix=path, required=required_here))
            continue
        ui = raw.get("x-llmops-ui", {}) if isinstance(raw.get("x-llmops-ui"), dict) else {}
        rows.append(
            {
                "path": path,
                "type": raw.get("type", "any"),
                "required": name in required_here,
                "default": raw.get("default"),
                "allowed": raw.get("enum"),
                "description": raw.get("description", ""),
                "group": ui.get("group", "General"),
                "order": ui.get("order", 100),
                "widget": ui.get("widget"),
                "advanced": bool(ui.get("advanced", False)),
                "read_only": bool(raw.get("readOnly", False) or "const" in raw),
                "dependencies": list(dependent.get(name, [])) if isinstance(dependent, dict) else [],
                "exclusions": [
                    json.dumps(rule, sort_keys=True)
                    for rule in constraints
                    if name in json.dumps(rule, sort_keys=True)
                ],
            }
        )
    return sorted(rows, key=lambda item: (item["group"], item["order"], item["path"]))
