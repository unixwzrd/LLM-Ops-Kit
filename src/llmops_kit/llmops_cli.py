#!/usr/bin/env python
"""Operator CLI for LLM-Ops-Kit component and stack orchestration."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

try:
    from . import __version__
except ImportError:
    __version__ = "source"

try:
    from .llmops_adapters import AdapterError, discover_adapters, validate_adapters
    from .llmops_config import ConfigError, load_config, update_display
    from .llmops_config_ops import (
        COMPONENT_SCHEMA,
        ConfigOperationError,
        add_component,
        authority_hash,
        clone_component,
        clone_profile,
        component_field_records,
        configure_component_schema,
        create_profile,
        edit_profile,
        field_records,
        find_profile,
        import_template,
        migrate_schema_v2,
        profile_template,
        provision_component,
        retire_component,
        template_action_argv,
        validate_connections,
    )
    from .llmops_config_sync import ReconcileError, apply_snapshot, reconcile_plan, snapshot_hash
    from .llmops_drivers import ComponentRunner, DriverError, build_component_command
    from .llmops_executor import ExecutionError, Executor, component_plan, stack_plan
    from .llmops_inventory import InventoryError, load_inventory
    from .llmops_lifecycle_state import LifecycleStateError, LifecycleStateStore
    from .llmops_init import InitError, ModelCandidate, discover_model_profiles, initialize
    from .llmops_migration import MigrationError, migrate
    from .llmops_operations import list_records, load_record, record_path
    from .llmops_paths import LlmOpsPaths, resolve_authority_config_home, resolve_paths
    from .llmops_probe import probe_topology
    from .llmops_profiles import model_values, service_values
    from .llmops_topology import Topology, TopologyError, load_profile, load_stacks, profile_path, validate_topology
    from .llmops_topology_view import project_topology, render_dot, render_mermaid, render_table
    from .llmops_templates import TemplateError, flatten_schema, load_template_registry, parse_schema_value, schema_node, set_dotted
except ImportError:  # Direct source execution.
    from llmops_adapters import AdapterError, discover_adapters, validate_adapters
    from llmops_config import ConfigError, load_config, update_display
    from llmops_config_ops import (
        COMPONENT_SCHEMA,
        ConfigOperationError,
        add_component,
        authority_hash,
        clone_component,
        clone_profile,
        component_field_records,
        configure_component_schema,
        create_profile,
        edit_profile,
        field_records,
        find_profile,
        import_template,
        migrate_schema_v2,
        profile_template,
        provision_component,
        retire_component,
        template_action_argv,
        validate_connections,
    )
    from llmops_config_sync import ReconcileError, apply_snapshot, reconcile_plan, snapshot_hash
    from llmops_drivers import ComponentRunner, DriverError, build_component_command
    from llmops_executor import ExecutionError, Executor, component_plan, stack_plan
    from llmops_inventory import InventoryError, load_inventory
    from llmops_lifecycle_state import LifecycleStateError, LifecycleStateStore
    from llmops_init import InitError, ModelCandidate, discover_model_profiles, initialize
    from llmops_migration import MigrationError, migrate
    from llmops_operations import list_records, load_record, record_path
    from llmops_paths import LlmOpsPaths, resolve_authority_config_home, resolve_paths
    from llmops_probe import probe_topology
    from llmops_profiles import model_values, service_values
    from llmops_topology import Topology, TopologyError, load_profile, load_stacks, profile_path, validate_topology
    from llmops_topology_view import project_topology, render_dot, render_mermaid, render_table
    from llmops_templates import TemplateError, flatten_schema, load_template_registry, parse_schema_value, schema_node, set_dotted


PUBLIC_COMMANDS = {
    "status": "Show aggregate local and remote component status",
    "host": "List trusted hosts or run a restricted operation on a peer",
    "component": "Inspect or operate one independently managed component",
    "stack": "Inspect or operate a dependency group of components",
    "topology": "Show bounded host and dependency relationships",
    "adapter": "List and validate installed lifecycle adapters",
    "template": "Inspect and import versioned service templates",
    "profile": "Create and edit reusable schema-driven profiles",
    "plan": "Preview dependency-ordered operations",
    "doctor": "Validate configuration and probe hosts and dependencies",
    "config": "Show or reconcile canonical configuration",
    "init": "Create guided single-host or local-LAN configuration",
    "migrate-config": "Convert supported proof-of-concept configuration once",
    "migrate-schema": "Convert canonical version 1 configuration to version 2 once",
    "rollback": "Return to the previous immutable runtime",
    "update": "Check, plan, or apply verified local and remote releases",
    "tui": "Open the optional Textual operations console",
    "operation": "Inspect persisted background lifecycle operations",
}


def print_public_help() -> None:
    """Print the stable top-level command summary."""

    print("Usage: llmops <command> [args...]\n\nCommands:")
    width = max(map(len, PUBLIC_COMMANDS))
    for command, description in PUBLIC_COMMANDS.items():
        print(f"  {command.ljust(width)}  {description}")
    print("\nUse `llmops --version` to print the installed toolkit version.")
    print("Run `llmops <command> --help` for command-specific options.")


def build_topology(*, config_home: Optional[str], inventory: Optional[str]) -> Topology:
    """Load canonical configuration, inventory, and stack topology."""

    env = dict(os.environ)
    if config_home:
        env["LLMOPS_CONFIG_HOME"] = config_home
    paths = resolve_paths(env)
    config = load_config(paths=paths)
    inventory_path = Path(inventory).expanduser() if inventory else paths.inventory_file
    hosts = load_inventory(inventory_path)
    return Topology(
        stacks=load_stacks(paths),
        hosts=hosts,
        paths=paths,
        config=config,
    )


def desired_topology(config_home: Optional[str] = None) -> Topology:
    """Load mutable authority configuration, falling back to the active topology."""

    root = Path(config_home).expanduser() if config_home else resolve_authority_config_home()
    if not (root / "config.json").is_file() or not (root / "inventory.json").is_file():
        return CURRENT_TOPOLOGY
    return build_topology(config_home=str(root), inventory=str(root / "inventory.json"))


def authority_paths(config_home: Optional[str] = None) -> LlmOpsPaths:
    """Resolve mutable desired-state paths without selecting a deployed revision."""

    if config_home:
        return resolve_paths({**os.environ, "LLMOPS_CONFIG_HOME": config_home})
    root = resolve_authority_config_home()
    if (root / "config.json").is_file() or (root / "inventory.json").is_file():
        return resolve_paths({**os.environ, "LLMOPS_CONFIG_HOME": str(root)})
    try:
        return CURRENT_TOPOLOGY.paths
    except NameError:
        return resolve_paths()


def emit(payload: Any, *, json_output: bool) -> None:
    """Print JSON or concise human-readable output."""

    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                print("\t".join(f"{key}={value}" for key, value in item.items()))
            else:
                print(item)
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            print(f"{key}={value}")
        return
    print(payload)


def operation_payload(operations: list[Any]) -> list[dict[str, str]]:
    """Render operations with their equivalent remote command."""

    rendered: list[dict[str, str]] = []
    for operation in operations:
        item = operation.as_dict()
        item["command"] = build_component_command(
            CURRENT_TOPOLOGY, operation.component, operation.action
        )
        rendered.append(item)
    return rendered


def cmd_doctor(args: argparse.Namespace) -> int:
    errors = validate_topology(CURRENT_TOPOLOGY)
    errors.extend(validate_connections(CURRENT_TOPOLOGY))
    errors.extend(
        validate_adapters(
            discover_adapters(),
            (component.driver for component in CURRENT_TOPOLOGY.all_components()),
        )
    )
    payload: dict[str, Any] = {
        "ok": not errors,
        "config_home": str(CURRENT_TOPOLOGY.paths.config_home),
        "inventory": str(CURRENT_TOPOLOGY.paths.inventory_file),
        "stacks": len(CURRENT_TOPOLOGY.stacks),
        "components": len(CURRENT_TOPOLOGY.all_components()),
        "errors": errors,
    }
    if args.probe and not errors:
        probes = probe_topology(CURRENT_TOPOLOGY)
        payload["probes"] = probes["checks"]
        payload["ok"] = bool(payload["ok"] and probes["ok"])
    emit(payload, json_output=args.json)
    return 0 if payload["ok"] else 2


def cmd_config_show(args: argparse.Namespace) -> int:
    payload = {
        "paths": CURRENT_TOPOLOGY.paths.as_dict(),
        "config_exists": CURRENT_TOPOLOGY.config.exists,
        "config": CURRENT_TOPOLOGY.config.data,
        "hosts": sorted(CURRENT_TOPOLOGY.hosts),
        "stacks": sorted(CURRENT_TOPOLOGY.stacks),
    }
    emit(payload, json_output=args.json)
    return 0


def _effective_component(component: Any, *, topology: Optional[Topology] = None) -> dict[str, Any]:
    """Return the canonical and resolved non-secret configuration for a component."""

    active_topology = topology or CURRENT_TOPOLOGY
    profile = load_profile(active_topology.paths, component)
    if component.driver == "modelctl":
        resolved = model_values(profile)
    elif component.driver in {"model-proxy", "tts-bridge"}:
        resolved = service_values(component.driver, profile)
    else:
        environment = profile.get("environment", {})
        resolved = environment if isinstance(environment, dict) else {}
    host = active_topology.hosts[component.host]
    return {
        "component": component.qualified_id,
        "host": component.host,
        "execution_user": component.execution_user or host.user,
        "transport": host.transport,
        "address": host.host,
        "driver": component.driver,
        "profile": component.profile,
        "profile_path": str(profile_path(active_topology.paths, component)),
        "enabled": component.enabled,
        "ownership": component.ownership,
        "restart_policy": component.restart_policy,
        "dependencies": list(component.depends_on),
        "health": {
            "type": component.health.kind,
            "target": component.health.target,
            "timeout_seconds": component.health.timeout_seconds,
        },
        "timeouts": {
            "start": component.timeouts.start,
            "stop": component.timeouts.stop,
            "restart": component.timeouts.restart,
            "status": component.timeouts.status,
            "logs": component.timeouts.logs,
        },
        "resolved": resolved,
        "profile_document": profile,
    }


def cmd_config_effective(args: argparse.Namespace) -> int:
    """Show the effective canonical configuration used by component drivers."""

    if args.scope == "component" and not args.component:
        raise TopologyError("config effective component requires a component ID")
    if args.component:
        payload: Any = _effective_component(CURRENT_TOPOLOGY.resolve_component(args.component))
    else:
        payload = [_effective_component(item) for item in CURRENT_TOPOLOGY.all_components()]
    emit(payload, json_output=args.json)
    return 0


def cmd_operation_list(args: argparse.Namespace) -> int:
    """List recent persisted operations."""

    emit(list_records(CURRENT_TOPOLOGY.paths, limit=args.limit), json_output=args.json)
    return 0


def cmd_operation_show(args: argparse.Namespace) -> int:
    """Show one persisted operation."""

    try:
        payload = load_record(record_path(CURRENT_TOPOLOGY.paths, args.operation_id))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TopologyError(f"operation not found or invalid: {args.operation_id}: {exc}") from exc
    emit(payload, json_output=args.json)
    return 0


def cmd_config_hash(args: argparse.Namespace) -> int:
    """Verify and report the active role-filtered configuration snapshot."""

    digest, valid, errors = snapshot_hash(CURRENT_TOPOLOGY.paths.config_home)
    payload = {
        "ok": valid,
        "valid": valid,
        "config_home": str(CURRENT_TOPOLOGY.paths.config_home),
        "config_hash": digest,
        "errors": errors,
    }
    emit(payload, json_output=args.json)
    return 0 if valid else 2


def cmd_config_display(args: argparse.Namespace) -> int:
    """Plan or transactionally update shared operator display metadata."""

    desired = desired_topology()
    current = desired.config.data.get("display", {})
    organization = args.organization if args.organization is not None else current.get("organization", "")
    site = args.site if args.site is not None else current.get("site", "")
    command = ["llmops", "config", "display", "--organization", organization, "--site", site]
    payload = {
        "organization": organization,
        "site": site,
        "command": command + (["--apply", "--yes"] if args.apply else ["--plan"]),
        "applied": False,
    }
    if not args.apply:
        emit(payload, json_output=args.json)
        return 0
    if not args.yes:
        if args.json or not sys.stdin.isatty():
            raise TopologyError("config display --apply requires --yes in non-interactive mode")
        print(json.dumps(payload, indent=2, sort_keys=True))
        if input("Apply display configuration? [y/N]: ").strip().lower() not in {"y", "yes"}:
            return 0
    backup = update_display(
        desired.paths.config_file,
        organization=organization,
        site=site,
    )
    payload.update({"applied": True, "backup": str(backup) if backup.exists() else ""})
    emit(payload, json_output=args.json)
    return 0


def cmd_topology_show(args: argparse.Namespace) -> int:
    """Render a bounded view of hosts, components, and dependencies."""

    projection = project_topology(
        CURRENT_TOPOLOGY,
        component=args.component,
        host=args.topology_host,
        stack=args.stack,
        adapter=args.adapter,
    )
    if args.format == "json" or args.json:
        emit(projection, json_output=True)
    elif args.format == "mermaid":
        print(render_mermaid(projection))
    elif args.format == "dot":
        print(render_dot(projection))
    else:
        print(render_table(projection))
    return 0


def cmd_config_reconcile(args: argparse.Namespace) -> int:
    """Plan or apply authority-generated role-filtered snapshots."""

    authority = desired_topology()
    names = list(dict.fromkeys(args.host or []))
    if args.all_hosts:
        names = sorted(authority.hosts)
    if not names:
        raise ReconcileError("select at least one --host or use --all-hosts")
    plan, snapshots = reconcile_plan(authority, names)
    try:
        if any(item["action"] in {"conflict", "unreachable", "error"} for item in plan):
            emit({"ok": False, "plan": plan}, json_output=args.json)
            return 2
        if not args.apply:
            emit({"ok": True, "plan": plan}, json_output=args.json)
            return 0
        if not args.yes:
            if args.json or not sys.stdin.isatty():
                raise ReconcileError("--apply requires --yes in non-interactive mode")
            answer = input("Apply the displayed configuration reconciliation plan? [y/N]: ").strip().lower()
            if answer not in {"y", "yes"}:
                emit({"ok": True, "cancelled": True, "plan": plan}, json_output=args.json)
                return 0
        results = [
            apply_snapshot(authority.hosts[item["host"]], snapshots[item["host"]], item["desired_hash"])
            for item in plan
            if item["action"] == "apply"
        ]
        emit({"ok": True, "plan": plan, "results": results}, json_output=args.json)
        return 0
    finally:
        roots = {path.parent for path in snapshots.values()}
        for root in roots:
            shutil.rmtree(root, ignore_errors=True)


def cmd_adapter(args: argparse.Namespace) -> int:
    """List, inspect, or validate installed adapters."""

    registry = discover_adapters()
    if args.adapter_action == "list":
        payload = [registry[name].as_dict() for name in sorted(registry)]
        emit(payload, json_output=args.json)
        return 0
    if args.adapter_action == "show":
        manifest = registry.get(args.adapter)
        if manifest is None:
            raise AdapterError(f"adapter not found: {args.adapter}")
        emit(manifest.as_dict(), json_output=args.json)
        return 0
    errors = validate_adapters(registry, ())
    emit({"ok": not errors, "adapters": len(registry), "errors": errors}, json_output=args.json)
    return 0 if not errors else 2


def _load_values_file(raw_path: Optional[str]) -> dict[str, Any]:
    if not raw_path:
        return {}
    path = Path(raw_path).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigOperationError(f"cannot read values file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigOperationError(f"values file must contain a JSON object: {path}")
    return payload


def _confirm_plan(args: argparse.Namespace, payload: dict[str, Any], prompt: str) -> bool:
    if not getattr(args, "apply", False):
        return False
    if getattr(args, "yes", False):
        return True
    if args.json or not sys.stdin.isatty():
        raise ConfigOperationError("--apply requires --yes in non-interactive mode")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return input(f"{prompt} [y/N]: ").strip().lower() in {"y", "yes"}


def _emit_fields(rows: list[dict[str, Any]], *, json_output: bool) -> None:
    if json_output:
        emit(rows, json_output=True)
        return
    table = Table(show_header=True, header_style="bold")
    for column in ("Path", "Type", "Current", "Default", "Allowed", "Required", "Source", "Description"):
        table.add_column(column)
    for row in rows:
        table.add_row(
            str(row.get("path", "")),
            json.dumps(row.get("type", ""), sort_keys=True),
            json.dumps(row.get("current"), sort_keys=True) if row.get("current") is not None else "",
            json.dumps(row.get("default"), sort_keys=True) if row.get("default") is not None else "",
            ", ".join(map(str, row.get("allowed") or [])),
            "yes" if row.get("required") else "no",
            str(row.get("source", "")),
            str(row.get("description", "")),
        )
    Console().print(table)


def cmd_template(args: argparse.Namespace) -> int:
    paths = authority_paths(args.config_home)
    registry = load_template_registry(paths)
    if args.template_action == "list":
        emit(
            [
                {
                    "id": item.template_id,
                    "version": item.version,
                    "adapter": item.adapter,
                    "kind": item.component_kind,
                    "lifecycle": item.lifecycle,
                    "platforms": list(item.platforms),
                    "experimental": item.experimental,
                    "source": item.source,
                }
                for item in registry.values()
            ],
            json_output=args.json,
        )
        return 0
    if args.template_action == "doctor":
        emit({"ok": True, "templates": len(registry)}, json_output=args.json)
        return 0
    if args.template_action == "import":
        source = Path(args.file).expanduser()
        plan = import_template(paths, source, apply=False)
        if not _confirm_plan(args, plan, "Import this reviewed local template?"):
            emit(plan, json_output=args.json)
            return 0
        emit(
            import_template(
                paths,
                source,
                apply=True,
                expected_hash=args.expected_hash,
            ),
            json_output=args.json,
        )
        return 0
    item = registry.get(args.template)
    if item is None:
        raise TemplateError(f"template not found: {args.template}")
    if args.template_action == "fields":
        _emit_fields(field_records(item), json_output=args.json)
    else:
        emit(item.as_dict(), json_output=args.json)
    return 0


def _profile_listing(topology: Topology) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for kind, directory in (
        ("model", topology.paths.models_dir),
        ("agent", topology.paths.agents_dir),
        ("service", topology.paths.services_dir),
    ):
        for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows.append(
                {
                    "name": path.stem,
                    "kind": kind,
                    "template": payload.get("template_id", "legacy-v1"),
                    "schema_version": payload.get("schema_version", 1),
                    "path": str(path),
                }
            )
    return rows


def cmd_profile(args: argparse.Namespace) -> int:
    action = args.profile_action
    topology = desired_topology()
    if action == "list":
        emit(_profile_listing(topology), json_output=args.json)
        return 0
    if action in {"show", "fields"}:
        template, path, document = profile_template(topology.paths, args.profile)
        if action == "fields":
            _emit_fields(field_records(template, current=document), json_output=args.json)
        else:
            emit(
                {"profile": args.profile, "template": template.template_id, "path": str(path), "document": document},
                json_output=args.json,
            )
        return 0
    if action == "create":
        values = _load_values_file(args.values)
        plan = create_profile(
            topology.paths,
            name=args.profile,
            template_id=args.template,
            values=values,
            apply=False,
        )
        if not _confirm_plan(args, plan, "Create this reusable profile?"):
            emit(plan, json_output=args.json)
            return 0
        payload = create_profile(
            topology.paths,
            name=args.profile,
            template_id=args.template,
            values=values,
            apply=True,
            expected_hash=args.expected_hash,
        )
    elif action == "edit":
        plan = edit_profile(
            topology,
            args.profile,
            assignments=args.set_values,
            unsets=args.unset_values,
            apply=False,
        )
        if plan["shared_profile"] and not args.confirm_shared:
            raise ConfigOperationError(
                "profile is shared; review affected_components and repeat with --confirm-shared"
            )
        if not _confirm_plan(args, plan, "Apply this profile update?"):
            emit(plan, json_output=args.json)
            return 0
        payload = edit_profile(
            topology,
            args.profile,
            assignments=args.set_values,
            unsets=args.unset_values,
            apply=True,
            expected_hash=args.expected_hash,
        )
    else:
        plan = clone_profile(topology.paths, args.profile, args.new_name, apply=False)
        if not _confirm_plan(args, plan, "Clone this reusable profile?"):
            emit(plan, json_output=args.json)
            return 0
        payload = clone_profile(
            topology.paths,
            args.profile,
            args.new_name,
            apply=True,
            expected_hash=args.expected_hash,
        )
    emit(payload, json_output=args.json)
    return 0


def cmd_component_fields(args: argparse.Namespace) -> int:
    _emit_fields(component_field_records(desired_topology(), args.component), json_output=args.json)
    return 0


def cmd_component_details(args: argparse.Namespace) -> int:
    topology = desired_topology()
    component = topology.resolve_component(args.component)
    payload = _effective_component(component, topology=topology)
    payload.update(
        {
            "template_id": component.template_id,
            "retired": component.retired,
            "connections": component.connections,
            "fields": component_field_records(topology, component.qualified_id),
        }
    )
    emit(payload, json_output=args.json)
    return 0


def cmd_component_add(args: argparse.Namespace) -> int:
    topology = desired_topology()
    profile_values: dict[str, Any] = {}
    connections: dict[str, dict[str, str]] = {}
    for specification in args.connect:
        name, separator, target = specification.partition("=")
        component_ref, endpoint_separator, endpoint = target.rpartition("@")
        if not separator or not name or not endpoint_separator or not component_ref or not endpoint:
            raise ConfigOperationError(
                "connection must be name=stack:component@endpoint"
            )
        connections[name] = {"component": component_ref, "endpoint": endpoint}
    if args.create_profile:
        template = load_template_registry(topology.paths).get(args.template)
        if template is None:
            raise ConfigOperationError(f"template not found: {args.template}")
        for specification in args.profile_set:
            path, separator, raw = specification.partition("=")
            if not separator or not path:
                raise ConfigOperationError(f"profile assignment must be path=value: {specification}")
            relative = path.removeprefix("profile.")
            node = schema_node(template.profile_schema, relative)
            set_dotted(profile_values, relative, parse_schema_value(node, raw))
    operation = provision_component if args.create_profile else add_component
    operation_kwargs = {
        "component_id": args.component_id,
        "stack_name": args.stack,
        "template_id": args.template,
        "profile_name": args.profile,
        "host": args.host,
        "execution_user": args.execution_user or "",
        "connections": connections,
        "dependencies": args.depends_on,
    }
    if args.create_profile:
        operation_kwargs.update(
            {"profile_values": profile_values, "create_new_profile": True}
        )
    plan = operation(topology, apply=False, **operation_kwargs)
    if not _confirm_plan(args, plan, "Add this disabled component?"):
        emit(plan, json_output=args.json)
        return 0
    emit(
        operation(
            topology,
            apply=True,
            expected_hash=args.expected_hash,
            **operation_kwargs,
        ),
        json_output=args.json,
    )
    return 0


def cmd_component_clone(args: argparse.Namespace) -> int:
    topology = desired_topology()
    plan = clone_component(
        topology,
        args.component,
        args.new_id,
        share_profile=args.share_profile,
        apply=False,
    )
    if not _confirm_plan(args, plan, "Clone this component?"):
        emit(plan, json_output=args.json)
        return 0
    emit(
        clone_component(
            topology,
            args.component,
            args.new_id,
            share_profile=args.share_profile,
            apply=True,
            expected_hash=args.expected_hash,
        ),
        json_output=args.json,
    )
    return 0


def cmd_component_retire(args: argparse.Namespace) -> int:
    topology = desired_topology()
    restore = args.component_command == "restore"
    plan = retire_component(topology, args.component, restore=restore, apply=False)
    if not _confirm_plan(args, plan, "Apply this lifecycle-state change?"):
        emit(plan, json_output=args.json)
        return 0
    component = topology.resolve_component(args.component)
    if not restore and ComponentRunner(topology).is_running(component):
        Executor(topology).execute_component(component, "stop", force=False)
    emit(
        retire_component(
            topology,
            args.component,
            restore=restore,
            apply=True,
            expected_hash=args.expected_hash,
        ),
        json_output=args.json,
    )
    return 0


def cmd_component_action(args: argparse.Namespace) -> int:
    topology = desired_topology()
    component = topology.resolve_component(args.component)
    template, argv, mutating = template_action_argv(topology, component.qualified_id, args.tool_action)
    plan = {
        "action": "component-template-action",
        "component": component.qualified_id,
        "template": template.template_id,
        "template_action": args.tool_action,
        "argv": argv,
        "mutating": mutating,
        "host": component.host,
        "execution_user": component.execution_user or topology.hosts[component.host].user,
    }
    if args.plan:
        emit(plan, json_output=args.json)
        return 0
    if mutating:
        if not args.apply:
            raise ConfigOperationError("mutating template action requires --apply")
        if not _confirm_plan(args, plan, "Run this adapter-owned action?"):
            emit(plan, json_output=args.json)
            return 0
    result = ComponentRunner(topology).run_argv(component, args.tool_action, argv)
    emit({**plan, "result": result.as_dict()}, json_output=args.json)
    return 0 if result.ok else 1


def cmd_init(args: argparse.Namespace) -> int:
    env = dict(os.environ)
    if args.config_home:
        env["LLMOPS_CONFIG_HOME"] = args.config_home
    paths = resolve_paths(env)
    source = Path(args.model_defaults_from).expanduser() if args.model_defaults_from else Path.home() / ".config" / "llm-ops"
    candidates: dict[str, ModelCandidate] = {}
    if source.resolve() != paths.config_home.resolve() and source.exists():
        candidates = discover_model_profiles(source)
    selected = list(dict.fromkeys(args.import_model or []))
    if args.import_all_models:
        selected = sorted(candidates)
    if args.no_model_import:
        selected = []
    defaults = {
        "llm": args.default_chat,
        "embedding": args.default_embedding,
        "tts": args.default_tts,
    }
    explicit_import = bool(selected or args.import_all_models or args.no_model_import)
    if candidates and not explicit_import and not args.json and sys.stdin.isatty():
        print("Existing model profiles:")
        for candidate in candidates.values():
            print(f"  {candidate.name} ({candidate.model_type})")
        choice = input("Import model defaults? [s]elect/[a]ll/[n]one: ").strip().lower()
        if choice in {"a", "all"}:
            selected = sorted(candidates)
        elif choice in {"s", "select"}:
            names = input("Model names (comma-separated): ").strip()
            selected = list(dict.fromkeys(item.strip() for item in names.split(",") if item.strip()))
        elif choice not in {"", "n", "none"}:
            raise InitError(f"unsupported model import choice: {choice}")
        for model_type, label in (("llm", "chat"), ("embedding", "embedding"), ("tts", "TTS")):
            choices = [name for name in selected if name in candidates and candidates[name].model_type == model_type]
            if not choices:
                continue
            answer = input(f"Default {label} profile [{'/'.join(choices)}; blank for none]: ").strip()
            if answer:
                defaults[model_type] = answer
    if selected and not candidates:
        raise InitError(f"no model defaults found under: {source}")
    result = initialize(
        paths,
        preset=args.preset,
        force=args.force,
        user=args.user or os.environ.get("USER", "operator"),
        model_host=args.model_host,
        agent_host=args.agent_host,
        model_candidates=candidates,
        import_models=selected,
        default_chat=defaults["llm"],
        default_embedding=defaults["embedding"],
        default_tts=defaults["tts"],
        install_root=os.environ.get("LLMOPS_HOME", "~/.local/llm-ops"),
        public_bin_dir=os.environ.get("LLMOPS_PUBLIC_BIN_DIR", "~/.local/bin"),
    )
    emit(
        {
            "ok": True,
            "preset": args.preset,
            "created": [str(path) for path in result.created],
            "imported_models": list(result.imported_models),
            "converted_secret_fields": list(result.converted_secrets),
        },
        json_output=args.json,
    )
    return 0


def cmd_migrate_config(args: argparse.Namespace) -> int:
    env = dict(os.environ)
    if args.config_home:
        env["LLMOPS_CONFIG_HOME"] = args.config_home
    result = migrate(
        Path(args.legacy_home),
        resolve_paths(env),
        dry_run=args.dry_run,
        force=args.force,
        allow_partial=args.allow_partial,
    )
    emit(
        {
            "ok": True,
            "unchanged": result.unchanged,
            "source_hash": result.source_hash,
            "written": [str(path) for path in result.written],
            "mappings": list(result.mappings),
            "warnings": list(result.warnings),
            "skipped": list(result.skipped),
        },
        json_output=args.json,
    )
    return 0


def cmd_migrate_schema(args: argparse.Namespace) -> int:
    paths = authority_paths(args.config_home)
    plan = migrate_schema_v2(
        paths,
        apply=False,
        authority_host=args.authority_host,
    )
    if not _confirm_plan(args, plan, "Migrate this canonical configuration to schema version 2?"):
        emit(plan, json_output=args.json)
        return 0
    emit(
        migrate_schema_v2(
            paths,
            apply=True,
            expected_hash=args.expected_hash,
            authority_host=args.authority_host,
        ),
        json_output=args.json,
    )
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    if args.stack:
        stack = CURRENT_TOPOLOGY.stacks.get(args.stack)
        if stack is None:
            raise TopologyError(f"stack not found: {args.stack}")
        operations = stack_plan(stack, args.action)
    else:
        operations = []
        for name in sorted(CURRENT_TOPOLOGY.stacks):
            operations.extend(stack_plan(CURRENT_TOPOLOGY.stacks[name], args.action))
    emit(operation_payload(operations), json_output=args.json)
    return 0


def cmd_component_list(args: argparse.Namespace) -> int:
    catalog = _load_observer_catalog()
    current_host = _current_snapshot_host()
    if catalog is not None and current_host in set(catalog.get("trusted_control_hosts", [])):
        components = [item for item in catalog["components"] if isinstance(item, dict)]
        if args.stack:
            components = [item for item in components if item.get("stack") == args.stack]
            if not components:
                raise TopologyError(f"stack not found: {args.stack}")
        emit(
            [
                {
                    "component": item.get("id", ""),
                    "host": item.get("host", ""),
                    "driver": item.get("driver", ""),
                    "profile": item.get("profile", ""),
                    "enabled": item.get("enabled", False),
                    "ownership": item.get("ownership", ""),
                }
                for item in components
            ],
            json_output=args.json,
        )
        return 0
    components = CURRENT_TOPOLOGY.all_components()
    if args.stack:
        if args.stack not in CURRENT_TOPOLOGY.stacks:
            raise TopologyError(f"stack not found: {args.stack}")
        components = list(CURRENT_TOPOLOGY.stacks[args.stack].components.values())
    payload = [
        {
            "component": item.qualified_id,
            "host": item.host,
            "driver": item.driver,
            "profile": item.profile,
            "enabled": item.enabled,
            "ownership": item.ownership,
        }
        for item in components
    ]
    emit(payload, json_output=args.json)
    return 0


def component_operations(args: argparse.Namespace) -> list[Any]:
    component = CURRENT_TOPOLOGY.resolve_component(args.component)
    return component_plan(
        CURRENT_TOPOLOGY,
        component,
        args.action,
        cascade=getattr(args, "cascade", False),
        no_deps=getattr(args, "no_deps", False),
    )


def cmd_component_plan(args: argparse.Namespace) -> int:
    emit(operation_payload(component_operations(args)), json_output=args.json)
    return 0


def cmd_component_status(args: argparse.Namespace) -> int:
    component = CURRENT_TOPOLOGY.resolve_component(args.component)
    if args.action == "logs":
        result = ComponentRunner(CURRENT_TOPOLOGY).logs(component, channel=args.channel)
        payload = result.as_dict()
        payload.update(
            {
                "host": component.host,
                "execution_user": component.execution_user or CURRENT_TOPOLOGY.hosts[component.host].user,
                "channel": args.channel,
            }
        )
        emit(payload, json_output=args.json)
        return 0 if result.ok else 1
    status_args = argparse.Namespace(
        selector=component.qualified_id,
        all=True,
        verbose=True,
        workers=1,
        host_timeout=20,
        status_host=None,
        local=True,
    )
    payload = _collect_status(status_args)
    emit(payload[0], json_output=args.json)
    return _status_exit_code(payload)


def cmd_component_version(args: argparse.Namespace) -> int:
    """Report configured and observed runtime identity for one component."""

    component = CURRENT_TOPOLOGY.resolve_component(args.component)
    status_args = argparse.Namespace(
        selector=component.qualified_id,
        all=True,
        verbose=False,
        workers=1,
        host_timeout=20,
        status_host=None,
        local=True,
    )
    item = _collect_status(status_args)[0]
    payload = {
        key: item.get(key, "")
        for key in (
            "component",
            "host",
            "execution_user",
            "component_version",
            "toolkit_version",
            "desired_runtime",
            "observed_runtime",
            "runtime_drift",
            "drift",
        )
    }
    emit(payload, json_output=args.json)
    return 1 if payload["runtime_drift"] else 0


def cmd_component_configure(args: argparse.Namespace) -> int:
    topology = desired_topology()
    component = topology.resolve_component(args.component)
    if args.set_values or args.unset_values:
        plan = configure_component_schema(
            topology,
            component.qualified_id,
            assignments=args.set_values,
            unsets=args.unset_values,
            apply=False,
        )
        plan["restart_affected"] = bool(args.restart_affected)
        if not args.apply:
            emit(plan, json_output=args.json)
            return 0
        if not args.yes:
            if args.json or not sys.stdin.isatty():
                raise ConfigOperationError("component configure --apply requires --yes in non-interactive mode")
            print(json.dumps(plan, indent=2, sort_keys=True))
            if input("Apply this schema-driven component configuration? [y/N]: ").strip().lower() not in {"y", "yes"}:
                return 0
        payload = configure_component_schema(
            topology,
            component.qualified_id,
            assignments=args.set_values,
            unsets=args.unset_values,
            apply=True,
            expected_hash=args.expected_hash,
        )
        if args.restart_affected:
            refreshed = desired_topology()
            desired_states = LifecycleStateStore(refreshed.paths.lifecycle_state_file).load()
            restarted: list[str] = []
            skipped: list[str] = []
            executor = Executor(refreshed)
            for reference in payload["affected_components"]:
                affected = refreshed.resolve_component(reference)
                desired = desired_states.get(
                    affected.qualified_id,
                    "running" if affected.enabled else "disabled",
                )
                if desired != "running" or not executor.runner.is_running(affected):
                    skipped.append(affected.qualified_id)
                    continue
                executor.execute_component(affected, "restart")
                restarted.append(affected.qualified_id)
            payload["restarted"] = restarted
            payload["restart_skipped"] = skipped
        emit(payload, json_output=args.json)
        return 0
    raise ConfigOperationError("component configure requires --set or --unset")


def _status_components(selector: Optional[str], *, include_disabled: bool) -> list[Any]:
    components = CURRENT_TOPOLOGY.all_components()
    if not include_disabled:
        components = [component for component in components if component.enabled]
    if not selector:
        return components

    folded = selector.casefold()
    exact = [
        component
        for component in components
        if component.qualified_id.casefold() == folded
        or component.component_id.casefold() == folded
    ]
    if len(exact) > 1:
        choices = ", ".join(component.qualified_id for component in exact)
        raise TopologyError(f"ambiguous component '{selector}'; use one of: {choices}")
    if exact:
        return exact

    matches = [
        component
        for component in components
        if component.stack.casefold() == folded
        or component.profile.casefold() == folded
        or component.driver.casefold() == folded
        or component.host.casefold() == folded
        or folded in {tag.casefold() for tag in component.tags}
    ]
    if not matches:
        raise TopologyError(f"status selector matched no components: {selector}")
    return matches


def _human_status(payload: list[dict[str, Any]]) -> None:
    """Render shared status records with semantic text and color."""

    columns = (
        ("condition", "CONDITION"),
        ("lifecycle", "LIFECYCLE"),
        ("desired_lifecycle", "DESIRED"),
        ("health", "HEALTH"),
        ("component", "COMPONENT"),
        ("host", "HOST"),
        ("execution_user", "RUN_AS"),
        ("driver", "DRIVER"),
        ("component_version", "COMPONENT_VERSION"),
        ("toolkit_version", "TOOLKIT_VERSION"),
        ("drift", "DRIFT"),
    )
    from .llmops_ui import status_cell_style

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    for _, header in columns:
        table.add_column(header, no_wrap=True)
    for item in payload:
        table.add_row(
            *(
                Text(
                    str(item.get(column, "")),
                    style=status_cell_style(column, item),
                )
                for column, _ in columns
            )
        )
    counts: dict[str, int] = {}
    for item in payload:
        counts[item["condition"]] = counts.get(item["condition"], 0) + 1
    console = Console(width=max(240, Console().width))
    console.print(table)
    console.print("  ".join(f"{name}={counts[name]}" for name in sorted(counts)))


def _condition(
    *,
    lifecycle: str,
    desired_lifecycle: str,
    health: str,
    observability: str,
    drift: str,
) -> str:
    """Derive an operator condition without hiding lifecycle or health."""

    if observability == "authority-only":
        return "unobserved"
    if observability == "unreachable" or lifecycle == "unknown":
        return "error"
    if lifecycle == "disabled":
        return "ok"
    if lifecycle == "stopped":
        if desired_lifecycle == "stopped":
            return "down"
        return "error"
    if health in {"degraded", "unhealthy"} or drift not in {"", "none"}:
        return "attention"
    return "ok"


def _observed_runtime(observation: Any) -> str:
    """Return an immutable release identifier observed in the live process command."""

    values = [
        observation.lifecycle_result.command,
        observation.lifecycle_result.stdout,
        observation.lifecycle_result.stderr,
    ]
    if observation.runtime_result is not None:
        values.extend(
            (
                observation.runtime_result.command,
                observation.runtime_result.stdout,
                observation.runtime_result.stderr,
            )
        )
    text = "\n".join(str(value) for value in values if value)
    started = re.findall(
        r"started_runtime_root=(?:[^\n]*/)?(?:releases|versions)/([^/\s'\"]+)",
        text,
    )
    if started:
        return started[-1]
    matches = re.findall(r"(?:^|/)(?:releases|versions)/([^/\s'\"]+)", text)
    return matches[-1] if matches else ""


def _component_version(component: Any, observation: Any) -> str:
    """Return the observed component release or an adapter-provided profile version."""

    observed = _observed_runtime(observation)
    if observed:
        return observed
    try:
        profile = load_profile(CURRENT_TOPOLOGY.paths, component)
    except TopologyError:
        return ""
    if profile.get("template_id") == "rtk":
        match = re.search(
            r"(?:^|\n)rtk\s+([^\s]+)",
            observation.lifecycle_result.stdout,
        )
        if match:
            return match.group(1)
    value = profile.get("version", "")
    return str(value) if isinstance(value, (str, int, float)) else ""


def _inspect_status(components: list[Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    runner = ComponentRunner(CURRENT_TOPOLOGY)
    enabled = [component for component in components if component.enabled]
    workers = min(max(1, args.workers), max(1, len(enabled)))
    def inspect(component: Any) -> tuple[str, Any, str]:
        try:
            return component.qualified_id, runner.inspect(component), ""
        except (DriverError, OSError) as exc:
            return component.qualified_id, None, str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        inspected = list(pool.map(inspect, enabled))
    by_component = {component: (result, error) for component, result, error in inspected}
    payload: list[dict[str, Any]] = []
    metadata = _runtime_metadata()
    desired_states = LifecycleStateStore(CURRENT_TOPOLOGY.paths.lifecycle_state_file).load()
    include_detail = args.verbose or (bool(args.selector) and len(components) == 1)
    for component in components:
        observation, error = by_component.get(component.qualified_id, (None, ""))
        if not component.enabled:
            lifecycle = "disabled"
            health = "not-applicable"
            observability = "observed"
            result = None
        elif observation is None:
            lifecycle = "unknown"
            health = "unknown"
            observability = "unreachable" if "timed out" in error.casefold() else "observed"
            result = None
        else:
            lifecycle = observation.lifecycle
            health = observation.health
            observability = observation.observability
            result = observation.lifecycle_result
        desired_lifecycle = desired_states.get(
            component.qualified_id,
            "running" if component.enabled else "disabled",
        )
        observed_runtime = "" if observation is None else _observed_runtime(observation)
        desired_runtime = metadata["toolkit_version"]
        runtime_drift = bool(observed_runtime and observed_runtime != desired_runtime)
        drift = "stale-runtime" if runtime_drift else metadata["drift"]
        condition = _condition(
            lifecycle=lifecycle,
            desired_lifecycle=desired_lifecycle,
            health=health,
            observability=observability,
            drift=drift,
        )
        item = {
            "lifecycle": lifecycle,
            "desired_lifecycle": desired_lifecycle,
            "health": health,
            "condition": condition,
            "observability": observability,
            "component": component.qualified_id,
            "host": component.host,
            "execution_user": component.execution_user or CURRENT_TOPOLOGY.hosts[component.host].user,
            "driver": component.driver,
            "profile": component.profile,
            "tags": list(component.tags),
            "returncode": None if result is None else result.returncode,
            "component_version": "" if observation is None else _component_version(component, observation),
            **metadata,
            "desired_runtime": desired_runtime,
            "observed_runtime": observed_runtime,
            "runtime_drift": runtime_drift,
            "drift": drift,
        }
        if error:
            item["error"] = error
        if include_detail:
            item["stdout"] = "" if result is None else result.stdout
            item["stderr"] = "" if result is None else result.stderr
        payload.append(item)
    return payload


def _runtime_metadata() -> dict[str, Any]:
    """Return local runtime and configuration identity for status records."""

    release_root = Path(sys.executable).absolute().parents[2]
    release_file = release_root / "RELEASE.json"
    version = __version__
    try:
        released = json.loads(release_file.read_text(encoding="utf-8"))
        version = str(released.get("version") or version)
    except (OSError, json.JSONDecodeError):
        pass
    catalog = CURRENT_TOPOLOGY.paths.config_home / "catalog.json"
    catalog_hash = hashlib.sha256(catalog.read_bytes()).hexdigest() if catalog.is_file() else ""
    config_hash = ""
    valid = True
    try:
        config_hash, valid, _ = snapshot_hash(CURRENT_TOPOLOGY.paths.config_home)
    except ReconcileError:
        valid = False
    current_host = _current_snapshot_host()
    loaded_catalog = _load_observer_catalog()
    authority = bool(current_host and loaded_catalog and current_host in loaded_catalog.get("trusted_control_hosts", []))
    install_base = release_root.parent.parent
    sync_file = install_base / "config-revisions" / ".last-sync"
    try:
        last_sync = sync_file.read_text(encoding="utf-8").strip()
    except OSError:
        last_sync = ""
    return {
        "toolkit_version": version,
        "catalog_hash": catalog_hash,
        "config_hash": config_hash,
        "authority": authority,
        "drift": "none" if valid else "configuration",
        "last_sync": last_sync,
    }


def _load_observer_catalog(config_home: Optional[Path] = None) -> Optional[dict[str, Any]]:
    path = (config_home or CURRENT_TOPOLOGY.paths.config_home) / "catalog.json"
    if not path.is_file():
        return None
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TopologyError(f"invalid observer catalog {path}: {exc}") from exc
    if not isinstance(catalog, dict) or catalog.get("schema_version") != 1:
        raise TopologyError(f"invalid observer catalog schema: {path}")
    if not isinstance(catalog.get("hosts"), list) or not isinstance(catalog.get("components"), list):
        raise TopologyError(f"observer catalog is incomplete: {path}")
    trusted = catalog.get("trusted_control_hosts", [])
    if not isinstance(trusted, list) or any(not isinstance(item, str) for item in trusted):
        raise TopologyError(f"observer catalog has invalid trusted_control_hosts: {path}")
    authority_host = catalog.get("authority_host", "")
    if authority_host and authority_host not in trusted:
        raise TopologyError(f"observer catalog has invalid authority_host: {path}")
    return catalog


def _is_authority_operation(args: argparse.Namespace) -> bool:
    """Return whether a command must inspect or mutate canonical desired state."""

    if args.command == "migrate-schema":
        return True
    if args.command == "config" and getattr(args, "config_command", "") in {
        "display",
        "reconcile",
    }:
        return True
    if args.command == "template" and getattr(args, "template_action", "") == "import":
        return True
    if args.command == "profile" and getattr(args, "profile_action", "") in {
        "create",
        "edit",
        "clone",
    }:
        return True
    return args.command == "component" and getattr(args, "component_command", "") in {
        "add",
        "configure",
        "clone",
        "retire",
        "restore",
    }


def _route_authority_operation(
    args: argparse.Namespace,
    operation: list[str],
    *,
    config_home: Path,
) -> Optional[int]:
    """Forward canonical operations from a trusted peer to the authority host."""

    if not _is_authority_operation(args):
        return None
    if any(
        token in {"--config-home", "--inventory"}
        or token.startswith(("--config-home=", "--inventory="))
        for token in operation
    ):
        return None
    catalog = _load_observer_catalog(config_home)
    if catalog is None:
        return None
    current_host = _current_snapshot_host(config_home)
    trusted = set(catalog.get("trusted_control_hosts", []))
    if current_host not in trusted:
        raise TopologyError(
            f"host is not trusted to request authority mutations: {current_host or 'unknown'}"
        )
    authority_host = str(catalog.get("authority_host", ""))
    if not authority_host or authority_host == current_host:
        return None
    target = _catalog_hosts(catalog).get(authority_host)
    if target is None:
        raise TopologyError(f"catalog authority host not found: {authority_host}")
    command = _host_command(target, operation, json_output=args.json)
    return _execute_host_operation(
        authority_host,
        command,
        json_output=args.json,
        timeout=900,
    )


def _catalog_hosts(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("name", "")): item
        for item in catalog["hosts"]
        if isinstance(item, dict) and item.get("name")
    }


def _validate_host_operation(operation: list[str]) -> None:
    if not operation:
        raise TopologyError("host operation is required")
    if any(
        token == "--local"
        or token in {"--config-home", "--inventory"}
        or token.startswith(("--config-home=", "--inventory="))
        for token in operation
    ):
        raise TopologyError("host operations cannot override deployed configuration")
    allowed: dict[str, set[str] | None] = {
        "status": None,
        "doctor": None,
        "component": {"list", "plan", "start", "stop", "restart", "status", "logs", "version"},
        "stack": {"list", "plan", "start", "stop", "restart", "status"},
        "topology": {"show"},
    }
    command = operation[0]
    if command not in allowed:
        raise TopologyError(f"host operation is not allowed: {command}")
    subcommands = allowed[command]
    if subcommands is not None and (len(operation) < 2 or operation[1] not in subcommands):
        raise TopologyError(f"host {command} operation is not allowed")


def _host_command(host: dict[str, Any], operation: list[str], *, json_output: bool) -> list[str]:
    remote = [_remote_llmops_path(str(host.get("public_bin_dir", "~/.local/bin"))), *map(shlex.quote, operation)]
    if json_output and "--json" not in operation:
        remote.append("--json")
    return [
        "ssh",
        "-p",
        str(host.get("port", 22)),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{host['user']}@{host['host']}",
        " ".join(remote),
    ]


def _host_context(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = _load_observer_catalog()
    if catalog is None:
        raise TopologyError("host operations require a deployed observer catalog")
    current_host = _current_snapshot_host()
    if current_host not in set(catalog.get("trusted_control_hosts", [])):
        raise TopologyError(f"host is not trusted for remote control: {current_host or 'unknown'}")
    hosts = _catalog_hosts(catalog)
    target = hosts.get(args.host)
    if target is None:
        raise TopologyError(f"catalog host not found: {args.host}")
    return catalog, target


def cmd_host_list(args: argparse.Namespace) -> int:
    catalog = _load_observer_catalog()
    if catalog is None:
        raise TopologyError("host list requires a deployed observer catalog")
    trusted = set(catalog.get("trusted_control_hosts", []))
    payload = [
        {
            "host": name,
            "address": item.get("host", ""),
            "user": item.get("user", ""),
            "role": item.get("role", ""),
            "trusted_control": name in trusted,
        }
        for name, item in sorted(_catalog_hosts(catalog).items())
    ]
    emit(payload, json_output=args.json)
    return 0


def cmd_host_operation(args: argparse.Namespace) -> int:
    _, target = _host_context(args)
    operation = list(args.operation)
    if operation and operation[0] == "--":
        operation = operation[1:]
    _validate_host_operation(operation)
    command = _host_command(target, operation, json_output=args.json)
    if args.host_action == "plan":
        emit({"host": args.host, "command": " ".join(shlex.quote(item) for item in command)}, json_output=args.json)
        return 0
    return _execute_host_operation(args.host, command, json_output=args.json, timeout=args.host_timeout)


def _execute_host_operation(host_name: str, command: list[str], *, json_output: bool, timeout: int) -> int:
    """Execute one allowlisted command on a trusted catalog host."""

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TopologyError(f"host operation failed: {exc}") from exc
    if json_output:
        try:
            remote_output: Any = json.loads(completed.stdout)
        except json.JSONDecodeError:
            remote_output = completed.stdout.strip()
        emit(
            {
                "host": host_name,
                "returncode": completed.returncode,
                "output": remote_output,
                "stderr": completed.stderr.strip(),
            },
            json_output=True,
        )
    else:
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode


def _catalog_component_exact(catalog: dict[str, Any], reference: str) -> dict[str, Any]:
    """Resolve a qualified or unique short component ID from the observer catalog."""

    folded = reference.replace("/", ":", 1).casefold()
    matches = [
        item
        for item in catalog["components"]
        if isinstance(item, dict)
        and (
            str(item.get("id", "")).casefold() == folded
            or str(item.get("component_id", "")).casefold() == folded
        )
    ]
    if not matches:
        raise TopologyError(f"component not found: {reference}")
    if len(matches) > 1:
        choices = ", ".join(str(item["id"]) for item in matches)
        raise TopologyError(f"ambiguous component '{reference}'; use one of: {choices}")
    return matches[0]


def cmd_remote_component(args: argparse.Namespace) -> int:
    """Delegate a non-local component action to its authorized owning host."""

    catalog = _load_observer_catalog()
    if catalog is None:
        raise TopologyError(f"component not found: {args.component}")
    current_host = _current_snapshot_host()
    if current_host not in set(catalog.get("trusted_control_hosts", [])):
        raise TopologyError(f"host is not trusted for remote control: {current_host or 'unknown'}")
    item = _catalog_component_exact(catalog, args.component)
    target_name = str(item.get("host", ""))
    target = _catalog_hosts(catalog).get(target_name)
    if target is None:
        raise TopologyError(f"catalog host not found: {target_name}")
    component_id = str(item["id"])
    if args.component_command == "plan":
        operation = ["component", "plan", args.action, component_id]
    else:
        operation = ["component", args.component_command, component_id]
    if getattr(args, "cascade", False):
        operation.append("--cascade")
    if getattr(args, "no_deps", False):
        operation.append("--no-deps")
    if getattr(args, "force", False):
        operation.append("--force")
    if args.component_command == "logs" and getattr(args, "channel", "service") != "service":
        operation.extend(("--channel", args.channel))
    command = _host_command(target, operation, json_output=args.json)
    return _execute_host_operation(target_name, command, json_output=args.json, timeout=900)


def _catalog_components(
    catalog: dict[str, Any], selector: Optional[str], *, include_disabled: bool
) -> list[dict[str, Any]]:
    components = [item for item in catalog["components"] if isinstance(item, dict)]
    if not include_disabled:
        components = [item for item in components if item.get("enabled") is True]
    if not selector:
        return components
    folded = selector.casefold()
    exact = [
        item
        for item in components
        if str(item.get("id", "")).casefold() == folded
        or str(item.get("component_id", "")).casefold() == folded
    ]
    if len(exact) > 1:
        choices = ", ".join(str(item["id"]) for item in exact)
        raise TopologyError(f"ambiguous component '{selector}'; use one of: {choices}")
    if exact:
        return exact
    matches = [
        item
        for item in components
        if str(item.get("stack", "")).casefold() == folded
        or str(item.get("profile", "")).casefold() == folded
        or str(item.get("driver", "")).casefold() == folded
        or str(item.get("host", "")).casefold() == folded
        or folded in {str(tag).casefold() for tag in item.get("tags", [])}
    ]
    if not matches:
        raise TopologyError(f"status selector matched no components: {selector}")
    return matches


def _current_snapshot_host(config_home: Optional[Path] = None) -> Optional[str]:
    path = (config_home or CURRENT_TOPOLOGY.paths.config_home) / "resolved.json"
    try:
        resolved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    host = resolved.get("host") if isinstance(resolved, dict) else None
    return host if isinstance(host, str) and host else None


def _remote_llmops_path(public_bin_dir: str) -> str:
    if public_bin_dir == "~":
        return '"$HOME"/llmops'
    if public_bin_dir.startswith("~/"):
        return '"$HOME"/' + shlex.quote(public_bin_dir[2:] + "/llmops")
    return shlex.quote(str(Path(public_bin_dir).expanduser() / "llmops"))


def _remote_status(
    host_name: str, host: dict[str, Any], selector: Optional[str], args: argparse.Namespace
) -> tuple[list[dict[str, Any]], str]:
    command = [
        "ssh",
        "-p",
        str(host.get("port", 22)),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{host['user']}@{host['host']}",
    ]
    remote = [_remote_llmops_path(str(host.get("public_bin_dir", "~/.local/bin"))), "status"]
    if selector:
        remote.append(shlex.quote(selector))
    remote.extend(("--host", shlex.quote(host_name), "--local", "--json"))
    if args.all:
        remote.append("--all")
    if args.verbose:
        remote.append("--verbose")
    command.append(" ".join(remote))
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=args.host_timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], str(exc)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        return [], detail
    if not isinstance(payload, list):
        return [], "remote status returned an invalid payload"
    return [item for item in payload if isinstance(item, dict)], ""


def _catalog_status(args: argparse.Namespace, catalog: dict[str, Any]) -> list[dict[str, Any]]:
    selected = _catalog_components(catalog, args.selector, include_disabled=args.all)
    by_host: dict[str, list[dict[str, Any]]] = {}
    for item in selected:
        by_host.setdefault(str(item.get("host", "")), []).append(item)
    hosts = {
        str(item.get("name", "")): item
        for item in catalog["hosts"]
        if isinstance(item, dict) and item.get("name")
    }
    current_host = _current_snapshot_host()

    def inspect_host(host_name: str) -> tuple[str, list[dict[str, Any]], str]:
        if host_name == current_host:
            local_ids = {str(item.get("id")) for item in by_host[host_name]}
            local = [
                component
                for component in _status_components(args.selector, include_disabled=args.all)
                if component.qualified_id in local_ids
            ]
            return host_name, _inspect_status(local, args), ""
        host = hosts.get(host_name)
        if host is None:
            return host_name, [], f"observer catalog has no host record for {host_name}"
        if host.get("peer_observable", True) is False:
            return host_name, [], "authority-only"
        payload, error = _remote_status(host_name, host, args.selector, args)
        return host_name, payload, error

    workers = min(max(1, args.workers), max(1, len(by_host)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(inspect_host, sorted(by_host)))
    payload: list[dict[str, Any]] = []
    for host_name, items, error in results:
        if not error:
            payload.extend(items)
            continue
        for component in by_host[host_name]:
            if component.get("enabled", True) is False:
                payload.append(
                    {
                        "lifecycle": "disabled",
                        "desired_lifecycle": "disabled",
                        "health": "not-applicable",
                        "condition": "ok",
                        "observability": "observed",
                        "component": component.get("id", ""),
                        "host": host_name,
                        "execution_user": str(hosts.get(host_name, {}).get("user", "")),
                        "driver": component.get("driver", ""),
                        "profile": component.get("profile", ""),
                        "tags": component.get("tags", []),
                        "returncode": None,
                        "component_version": "",
                        "toolkit_version": "",
                        "drift": "unknown",
                    }
                )
                continue
            if error == "authority-only":
                payload.append(
                    {
                        "lifecycle": "unknown",
                        "desired_lifecycle": "running",
                        "health": "unknown",
                        "condition": "unobserved",
                        "observability": "authority-only",
                        "component": component.get("id", ""),
                        "host": host_name,
                        "execution_user": str(hosts.get(host_name, {}).get("user", "")),
                        "driver": component.get("driver", ""),
                        "profile": component.get("profile", ""),
                        "tags": component.get("tags", []),
                        "returncode": None,
                        "component_version": "",
                        "toolkit_version": "",
                        "drift": "unknown",
                    }
                )
                continue
            payload.append(
                {
                    "lifecycle": "unknown",
                    "desired_lifecycle": "running",
                    "health": "unknown",
                    "condition": "error",
                    "observability": "unreachable",
                    "component": component.get("id", ""),
                    "host": host_name,
                    "execution_user": str(hosts.get(host_name, {}).get("user", "")),
                    "driver": component.get("driver", ""),
                    "profile": component.get("profile", ""),
                    "tags": component.get("tags", []),
                    "returncode": 255,
                    "component_version": "",
                    "toolkit_version": "",
                    "drift": "unknown",
                    "error": error,
                }
            )
    return sorted(payload, key=lambda item: str(item.get("component", "")))


def _collect_status(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Collect status using the same observer semantics for every interface."""

    catalog = None if args.local else _load_observer_catalog()
    if catalog is None:
        components = _status_components(args.selector, include_disabled=args.all)
        if getattr(args, "status_host", None):
            components = [component for component in components if component.host == args.status_host]
        payload = _inspect_status(components, args)
    else:
        payload = _catalog_status(args, catalog)
    return payload


def cmd_status(args: argparse.Namespace) -> int:
    payload = _collect_status(args)
    if args.json:
        emit(payload, json_output=True)
    else:
        _human_status(payload)
        if args.selector and len(payload) == 1:
            detail = payload[0].get("stdout", "") or payload[0].get("stderr", "")
            if detail:
                print(f"\n{detail}")
    return _status_exit_code(payload)


def _status_exit_code(payload: list[dict[str, Any]]) -> int:
    """Return stable status severity for CLI and automation."""

    conditions = {str(item.get("condition", "error")) for item in payload}
    if "error" in conditions:
        return 2
    if "attention" in conditions:
        return 1
    return 0


def cmd_component_mutate(args: argparse.Namespace) -> int:
    component = CURRENT_TOPOLOGY.resolve_component(args.component)
    executor = Executor(CURRENT_TOPOLOGY)
    results = executor.execute_component(
        component,
        args.action,
        cascade=args.cascade,
        no_deps=args.no_deps,
        force=args.force,
    )
    emit([result.as_dict() for result in results], json_output=args.json)
    return 0


def cmd_stack_list(args: argparse.Namespace) -> int:
    payload = [
        {
            "stack": stack.name,
            "components": len(stack.components),
            "enabled": sum(1 for item in stack.components.values() if item.enabled),
            "path": str(stack.path),
        }
        for stack in CURRENT_TOPOLOGY.stacks.values()
    ]
    emit(payload, json_output=args.json)
    return 0


def stack_operations(args: argparse.Namespace) -> list[Any]:
    stack_name = args.stack
    if stack_name is None:
        if len(CURRENT_TOPOLOGY.stacks) != 1:
            choices = ", ".join(sorted(CURRENT_TOPOLOGY.stacks)) or "none configured"
            raise TopologyError(f"stack name is required; available stacks: {choices}")
        stack_name = next(iter(CURRENT_TOPOLOGY.stacks))
    stack = CURRENT_TOPOLOGY.stacks.get(stack_name)
    if stack is None:
        raise TopologyError(f"stack not found: {stack_name}")
    return stack_plan(stack, args.action)


def cmd_stack_plan(args: argparse.Namespace) -> int:
    emit(operation_payload(stack_operations(args)), json_output=args.json)
    return 0


def cmd_stack_run(args: argparse.Namespace) -> int:
    if args.action == "status":
        stack_name = args.stack
        if stack_name is None:
            if len(CURRENT_TOPOLOGY.stacks) != 1:
                choices = ", ".join(sorted(CURRENT_TOPOLOGY.stacks)) or "none configured"
                raise TopologyError(f"stack name is required; available stacks: {choices}")
            stack_name = next(iter(CURRENT_TOPOLOGY.stacks))
        status_args = argparse.Namespace(
            selector=stack_name,
            all=True,
            verbose=False,
            workers=8,
            host_timeout=20,
            status_host=None,
            local=True,
        )
        payload = _collect_status(status_args)
        emit(payload, json_output=args.json)
        return _status_exit_code(payload)
    executor = Executor(CURRENT_TOPOLOGY)
    operations = stack_operations(args)
    results = executor.execute(operations)
    emit([result.as_dict() for result in results], json_output=args.json)
    return 0 if all(result.ok for result in results) else 1


def normalize_global_options(argv: list[str]) -> list[str]:
    """Allow global options before or after the selected command."""

    globals_first: list[str] = []
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--json":
            globals_first.append(token)
        elif token in {"--config-home", "--inventory"}:
            if index + 1 >= len(argv):
                remaining.append(token)
            else:
                globals_first.extend((token, argv[index + 1]))
                index += 1
        elif token.startswith("--config-home=") or token.startswith("--inventory="):
            globals_first.append(token)
        else:
            remaining.append(token)
        index += 1
    return globals_first + remaining


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM-Ops-Kit operator control")
    parser.add_argument("--config-home")
    parser.add_argument("--inventory")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--probe", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    init = sub.add_parser("init")
    init.add_argument("--preset", choices=("single-host", "local-lan"), default="single-host")
    init.add_argument("--user")
    init.add_argument("--model-host", default="model-host.local")
    init.add_argument("--agent-host", default="agent-host.local")
    init.add_argument("--model-defaults-from")
    init.add_argument("--import-model", action="append", default=[])
    import_mode = init.add_mutually_exclusive_group()
    import_mode.add_argument("--import-all-models", action="store_true")
    import_mode.add_argument("--no-model-import", action="store_true")
    init.add_argument("--default-chat")
    init.add_argument("--default-embedding")
    init.add_argument("--default-tts")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init, topology_required=False)

    migrate_config = sub.add_parser("migrate-config")
    migrate_config.add_argument("--legacy-home", default="~/.llm-ops")
    migrate_config.add_argument("--dry-run", action="store_true")
    migrate_config.add_argument("--force", action="store_true")
    migrate_config.add_argument("--allow-partial", action="store_true")
    migrate_config.set_defaults(func=cmd_migrate_config, topology_required=False)

    migrate_schema = sub.add_parser("migrate-schema")
    migrate_schema.add_argument("--expected-hash")
    migrate_schema.add_argument(
        "--authority-host",
        help="set the trusted desired-state authority while migrating",
    )
    migrate_schema_action = migrate_schema.add_mutually_exclusive_group()
    migrate_schema_action.add_argument("--plan", action="store_true")
    migrate_schema_action.add_argument("--apply", action="store_true")
    migrate_schema.add_argument("--yes", action="store_true")
    migrate_schema.set_defaults(func=cmd_migrate_schema, topology_required=False)

    plan = sub.add_parser("plan")
    plan.add_argument("--action", choices=("start", "stop", "restart"), default="start")
    plan.add_argument("--stack")
    plan.set_defaults(func=cmd_plan)

    status = sub.add_parser("status")
    status.add_argument("selector", nargs="?")
    status.add_argument("--all", action="store_true", help="include disabled components")
    status.add_argument("--verbose", action="store_true", help="include driver output for every match")
    status.add_argument("--workers", type=int, default=8)
    status.add_argument("--host-timeout", type=int, default=20)
    status.add_argument("--host", dest="status_host", help=argparse.SUPPRESS)
    status.add_argument("--local", action="store_true", help=argparse.SUPPRESS)
    status.set_defaults(func=cmd_status)

    host = sub.add_parser("host")
    host_sub = host.add_subparsers(dest="host_action", required=True)
    host_list = host_sub.add_parser("list")
    host_list.set_defaults(func=cmd_host_list)
    for action in ("plan", "run"):
        host_operation = host_sub.add_parser(action)
        host_operation.add_argument("host")
        host_operation.add_argument("operation", nargs=argparse.REMAINDER)
        host_operation.add_argument("--host-timeout", type=int, default=900)
        host_operation.set_defaults(func=cmd_host_operation)

    config = sub.add_parser("config")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_show = config_sub.add_parser("show")
    config_show.set_defaults(func=cmd_config_show)
    config_effective = config_sub.add_parser("effective")
    config_effective.add_argument("scope", nargs="?", choices=("component",))
    config_effective.add_argument("component", nargs="?")
    config_effective.set_defaults(func=cmd_config_effective)
    config_hash = config_sub.add_parser("hash")
    config_hash.set_defaults(func=cmd_config_hash)
    config_display = config_sub.add_parser("display")
    config_display.add_argument("--organization")
    config_display.add_argument("--site")
    display_action = config_display.add_mutually_exclusive_group()
    display_action.add_argument("--plan", action="store_true")
    display_action.add_argument("--apply", action="store_true")
    config_display.add_argument("--yes", action="store_true")
    config_display.set_defaults(func=cmd_config_display)
    config_reconcile = config_sub.add_parser("reconcile")
    reconcile_action = config_reconcile.add_mutually_exclusive_group()
    reconcile_action.add_argument("--plan", action="store_true")
    reconcile_action.add_argument("--apply", action="store_true")
    config_reconcile.add_argument("--host", action="append", default=[])
    config_reconcile.add_argument("--all-hosts", action="store_true")
    config_reconcile.add_argument("--yes", action="store_true")
    config_reconcile.set_defaults(func=cmd_config_reconcile)

    adapter = sub.add_parser("adapter")
    adapter_sub = adapter.add_subparsers(dest="adapter_action", required=True)
    adapter_list = adapter_sub.add_parser("list")
    adapter_list.set_defaults(func=cmd_adapter, topology_required=False)
    adapter_show = adapter_sub.add_parser("show")
    adapter_show.add_argument("adapter")
    adapter_show.set_defaults(func=cmd_adapter, topology_required=False)
    adapter_doctor = adapter_sub.add_parser("doctor")
    adapter_doctor.set_defaults(func=cmd_adapter, topology_required=False)

    template = sub.add_parser("template")
    template_sub = template.add_subparsers(dest="template_action", required=True)
    template_list = template_sub.add_parser("list")
    template_list.set_defaults(func=cmd_template, topology_required=False)
    template_doctor = template_sub.add_parser("doctor")
    template_doctor.set_defaults(func=cmd_template, topology_required=False)
    for action in ("show", "fields"):
        item = template_sub.add_parser(action)
        item.add_argument("template")
        item.set_defaults(func=cmd_template, topology_required=False)
    template_import = template_sub.add_parser("import")
    template_import.add_argument("file")
    template_import.add_argument("--expected-hash")
    template_import_action = template_import.add_mutually_exclusive_group()
    template_import_action.add_argument("--plan", action="store_true")
    template_import_action.add_argument("--apply", action="store_true")
    template_import.add_argument("--yes", action="store_true")
    template_import.set_defaults(func=cmd_template, topology_required=False)

    profile = sub.add_parser("profile")
    profile_sub = profile.add_subparsers(dest="profile_action", required=True)
    profile_list = profile_sub.add_parser("list")
    profile_list.set_defaults(func=cmd_profile)
    for action in ("show", "fields"):
        item = profile_sub.add_parser(action)
        item.add_argument("profile")
        item.set_defaults(func=cmd_profile)
    profile_create = profile_sub.add_parser("create")
    profile_create.add_argument("profile")
    profile_create.add_argument("--template", required=True)
    profile_create.add_argument("--values")
    profile_create.add_argument("--expected-hash")
    profile_create_action = profile_create.add_mutually_exclusive_group()
    profile_create_action.add_argument("--plan", action="store_true")
    profile_create_action.add_argument("--apply", action="store_true")
    profile_create.add_argument("--yes", action="store_true")
    profile_create.set_defaults(func=cmd_profile)
    profile_edit = profile_sub.add_parser("edit")
    profile_edit.add_argument("profile")
    profile_edit.add_argument("--set", dest="set_values", action="append", default=[])
    profile_edit.add_argument("--unset", dest="unset_values", action="append", default=[])
    profile_edit.add_argument("--confirm-shared", action="store_true")
    profile_edit.add_argument("--expected-hash")
    profile_edit_action = profile_edit.add_mutually_exclusive_group()
    profile_edit_action.add_argument("--plan", action="store_true")
    profile_edit_action.add_argument("--apply", action="store_true")
    profile_edit.add_argument("--yes", action="store_true")
    profile_edit.set_defaults(func=cmd_profile)
    profile_clone = profile_sub.add_parser("clone")
    profile_clone.add_argument("profile")
    profile_clone.add_argument("new_name")
    profile_clone.add_argument("--expected-hash")
    profile_clone_action = profile_clone.add_mutually_exclusive_group()
    profile_clone_action.add_argument("--plan", action="store_true")
    profile_clone_action.add_argument("--apply", action="store_true")
    profile_clone.add_argument("--yes", action="store_true")
    profile_clone.set_defaults(func=cmd_profile)

    topology_parser = sub.add_parser("topology")
    topology_sub = topology_parser.add_subparsers(dest="topology_command", required=True)
    topology_show = topology_sub.add_parser("show")
    topology_show.add_argument("--component")
    topology_show.add_argument("--host", dest="topology_host")
    topology_show.add_argument("--stack")
    topology_show.add_argument("--adapter")
    topology_show.add_argument("--format", choices=("table", "json", "mermaid", "dot"), default="table")
    topology_show.set_defaults(func=cmd_topology_show)

    operation = sub.add_parser("operation")
    operation_sub = operation.add_subparsers(dest="operation_command", required=True)
    operation_list = operation_sub.add_parser("list")
    operation_list.add_argument("--limit", type=int, default=50)
    operation_list.set_defaults(func=cmd_operation_list)
    operation_show = operation_sub.add_parser("show")
    operation_show.add_argument("operation_id")
    operation_show.set_defaults(func=cmd_operation_show)

    component = sub.add_parser("component")
    component_sub = component.add_subparsers(dest="component_command", required=True)
    component_list = component_sub.add_parser("list")
    component_list.add_argument("--stack")
    component_list.set_defaults(func=cmd_component_list)
    component_plan_parser = component_sub.add_parser("plan")
    component_plan_parser.add_argument("action", choices=("start", "stop", "restart"))
    component_plan_parser.add_argument("component")
    component_plan_parser.add_argument("--cascade", action="store_true")
    component_plan_parser.add_argument("--no-deps", action="store_true")
    component_plan_parser.set_defaults(func=cmd_component_plan)
    for action in ("start", "stop", "restart"):
        action_parser = component_sub.add_parser(action)
        action_parser.set_defaults(action=action, func=cmd_component_mutate)
        action_parser.add_argument("component")
        action_parser.add_argument("--cascade", action="store_true")
        action_parser.add_argument("--no-deps", action="store_true")
        action_parser.add_argument("--force", action="store_true")
    for action in ("status", "logs"):
        action_parser = component_sub.add_parser(action)
        action_parser.set_defaults(action=action, func=cmd_component_status)
        action_parser.add_argument("component")
        if action == "logs":
            action_parser.add_argument(
                "--channel",
                choices=("service", "raw-request", "rendered-prompt", "raw-response"),
                default="service",
            )
    component_version = component_sub.add_parser("version")
    component_version.add_argument("component")
    component_version.set_defaults(component_command="version", func=cmd_component_version)
    component_fields = component_sub.add_parser("fields")
    component_fields.add_argument("component")
    component_fields.set_defaults(func=cmd_component_fields)
    component_details = component_sub.add_parser("details")
    component_details.add_argument("component")
    component_details.set_defaults(func=cmd_component_details)
    component_add = component_sub.add_parser("add")
    component_add.add_argument("component_id")
    component_add.add_argument("--template", required=True)
    component_add.add_argument("--profile", required=True)
    component_add.add_argument("--stack", required=True)
    component_add.add_argument("--host", required=True)
    component_add.add_argument("--execution-user")
    component_add.add_argument(
        "--connect",
        action="append",
        default=[],
        help="typed endpoint binding name=stack:component@endpoint",
    )
    component_add.add_argument("--depends-on", action="append", default=[])
    component_add.add_argument("--create-profile", action="store_true")
    component_add.add_argument("--set-profile", dest="profile_set", action="append", default=[])
    component_add.add_argument("--expected-hash")
    component_add_action = component_add.add_mutually_exclusive_group()
    component_add_action.add_argument("--plan", action="store_true")
    component_add_action.add_argument("--apply", action="store_true")
    component_add.add_argument("--yes", action="store_true")
    component_add.set_defaults(func=cmd_component_add)
    component_clone = component_sub.add_parser("clone")
    component_clone.add_argument("component")
    component_clone.add_argument("new_id")
    profile_mode = component_clone.add_mutually_exclusive_group(required=True)
    profile_mode.add_argument("--share-profile", action="store_true")
    profile_mode.add_argument("--clone-profile", dest="share_profile", action="store_false")
    component_clone.add_argument("--expected-hash")
    component_clone_action = component_clone.add_mutually_exclusive_group()
    component_clone_action.add_argument("--plan", action="store_true")
    component_clone_action.add_argument("--apply", action="store_true")
    component_clone.add_argument("--yes", action="store_true")
    component_clone.set_defaults(func=cmd_component_clone)
    for action in ("retire", "restore"):
        lifecycle_edit = component_sub.add_parser(action)
        lifecycle_edit.add_argument("component")
        lifecycle_edit.add_argument("--expected-hash")
        lifecycle_edit_action = lifecycle_edit.add_mutually_exclusive_group()
        lifecycle_edit_action.add_argument("--plan", action="store_true")
        lifecycle_edit_action.add_argument("--apply", action="store_true")
        lifecycle_edit.add_argument("--yes", action="store_true")
        lifecycle_edit.set_defaults(func=cmd_component_retire)
    component_action = component_sub.add_parser("action")
    component_action.add_argument("component")
    component_action.add_argument("tool_action")
    component_action.add_argument("--plan", action="store_true")
    component_action.add_argument("--apply", action="store_true")
    component_action.add_argument("--yes", action="store_true")
    component_action.set_defaults(func=cmd_component_action)
    configure = component_sub.add_parser("configure")
    configure.add_argument("component")
    configure.add_argument("--set", dest="set_values", action="append", default=[])
    configure.add_argument("--unset", dest="unset_values", action="append", default=[])
    configure.add_argument("--expected-hash")
    configure.add_argument("--restart-affected", action="store_true")
    configure_action = configure.add_mutually_exclusive_group()
    configure_action.add_argument("--plan", action="store_true")
    configure_action.add_argument("--apply", action="store_true")
    configure.add_argument("--yes", action="store_true")
    configure.set_defaults(func=cmd_component_configure)

    stack = sub.add_parser("stack")
    stack_sub = stack.add_subparsers(dest="stack_command", required=True)
    stack_list = stack_sub.add_parser("list")
    stack_list.set_defaults(func=cmd_stack_list)
    stack_plan_parser = stack_sub.add_parser("plan")
    stack_plan_parser.add_argument("action", choices=("start", "stop", "restart"))
    stack_plan_parser.add_argument("stack")
    stack_plan_parser.set_defaults(func=cmd_stack_plan)
    for action in ("start", "stop", "restart"):
        action_parser = stack_sub.add_parser(action)
        action_parser.set_defaults(action=action, func=cmd_stack_run)
        action_parser.add_argument("stack")
    stack_status = stack_sub.add_parser("status")
    stack_status.set_defaults(action="status", func=cmd_stack_run)
    stack_status.add_argument("stack", nargs="?")
    return parser


CURRENT_TOPOLOGY: Topology


def main(argv: Optional[list[str]] = None) -> int:
    global CURRENT_TOPOLOGY
    parser = build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    normalized_argv = normalize_global_options(raw_argv)
    args = parser.parse_args(normalized_argv)
    try:
        paths = resolve_paths(
            {
                **os.environ,
                **({"LLMOPS_CONFIG_HOME": args.config_home} if args.config_home else {}),
            }
        )
        routed = _route_authority_operation(
            args,
            normalized_argv,
            config_home=paths.config_home,
        )
        if routed is not None:
            return routed
        if getattr(args, "topology_required", True):
            CURRENT_TOPOLOGY = build_topology(
                config_home=args.config_home,
                inventory=args.inventory,
            )
        if (
            args.command == "component"
            and getattr(args, "component_command", "") in {"plan", "start", "stop", "restart", "status", "logs", "version"}
        ):
            try:
                CURRENT_TOPOLOGY.resolve_component(args.component)
            except TopologyError as exc:
                if str(exc) != f"component not found: {args.component}":
                    raise
                return cmd_remote_component(args)
        return args.func(args)
    except (
        ConfigError,
        InitError,
        InventoryError,
        MigrationError,
        TopologyError,
        DriverError,
        ExecutionError,
        LifecycleStateError,
        AdapterError,
        ReconcileError,
        ConfigOperationError,
        TemplateError,
    ) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"llmops: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
