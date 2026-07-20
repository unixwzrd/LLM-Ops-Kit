#!/usr/bin/env python
"""Operator CLI for LLM-Ops-Kit component and stack orchestration."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

try:
    from . import __version__
except ImportError:
    __version__ = "source"

try:
    from .llmops_adapters import AdapterError, discover_adapters, validate_adapters
    from .llmops_config import ConfigError, load_config
    from .llmops_config_sync import ReconcileError, apply_snapshot, reconcile_plan, snapshot_hash
    from .llmops_drivers import ComponentRunner, DriverError, build_component_command
    from .llmops_executor import ExecutionError, Executor, component_plan, stack_plan
    from .llmops_inventory import InventoryError, load_inventory
    from .llmops_init import InitError, ModelCandidate, discover_model_profiles, initialize
    from .llmops_migration import MigrationError, migrate
    from .llmops_paths import LlmOpsPaths, resolve_paths
    from .llmops_probe import probe_topology
    from .llmops_topology import Topology, TopologyError, load_stacks, validate_topology
except ImportError:  # Direct source execution.
    from llmops_adapters import AdapterError, discover_adapters, validate_adapters
    from llmops_config import ConfigError, load_config
    from llmops_config_sync import ReconcileError, apply_snapshot, reconcile_plan, snapshot_hash
    from llmops_drivers import ComponentRunner, DriverError, build_component_command
    from llmops_executor import ExecutionError, Executor, component_plan, stack_plan
    from llmops_inventory import InventoryError, load_inventory
    from llmops_init import InitError, ModelCandidate, discover_model_profiles, initialize
    from llmops_migration import MigrationError, migrate
    from llmops_paths import LlmOpsPaths, resolve_paths
    from llmops_probe import probe_topology
    from llmops_topology import Topology, TopologyError, load_stacks, validate_topology


PUBLIC_COMMANDS = {
    "status": "Show aggregate local and remote component status",
    "host": "List trusted hosts or run a restricted operation on a peer",
    "component": "Inspect or operate one independently managed component",
    "stack": "Inspect or operate a dependency group of components",
    "adapter": "List and validate installed lifecycle adapters",
    "plan": "Preview dependency-ordered operations",
    "doctor": "Validate configuration and probe hosts and dependencies",
    "config": "Show or reconcile canonical configuration",
    "init": "Create guided single-host or local-LAN configuration",
    "migrate-config": "Convert supported proof-of-concept configuration once",
    "rollback": "Return to the previous immutable runtime",
    "update": "Check, plan, or apply verified local and remote releases",
    "tui": "Open the optional Textual operations console",
}


def print_public_help() -> None:
    """Print the stable top-level command summary."""

    print("Usage: llmops <command> [args...]\n\nCommands:")
    width = max(map(len, PUBLIC_COMMANDS))
    for command, description in PUBLIC_COMMANDS.items():
        print(f"  {command.ljust(width)}  {description}")
    print("\nRun `llmops <command> --help` for command-specific options.")


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


def cmd_config_reconcile(args: argparse.Namespace) -> int:
    """Plan or apply authority-generated role-filtered snapshots."""

    names = list(dict.fromkeys(args.host or []))
    if args.all_hosts:
        names = sorted(CURRENT_TOPOLOGY.hosts)
    if not names:
        raise ReconcileError("select at least one --host or use --all-hosts")
    plan, snapshots = reconcile_plan(CURRENT_TOPOLOGY, names)
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
            apply_snapshot(CURRENT_TOPOLOGY.hosts[item["host"]], snapshots[item["host"]], item["desired_hash"])
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
    errors = validate_adapters(
        registry,
        (driver for manifest in registry.values() for driver in manifest.drivers),
    )
    emit({"ok": not errors, "adapters": len(registry), "errors": errors}, json_output=args.json)
    return 0 if not errors else 2


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
    result = ComponentRunner(CURRENT_TOPOLOGY).run(component, args.action)
    emit(result.as_dict(), json_output=args.json)
    return 0 if result.ok else 1


def _component_changes(args: argparse.Namespace) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for field in ("host", "profile", "ownership"):
        value = getattr(args, field, None)
        if value is not None:
            changes[field] = value
    if args.enabled is not None:
        changes["enabled"] = args.enabled
    if args.depends_on is not None:
        changes["depends_on"] = args.depends_on
    if args.health_timeout is not None:
        changes["health_timeout"] = args.health_timeout
    return changes


def configure_component(component: Any, changes: dict[str, Any], *, apply: bool) -> dict[str, Any]:
    """Plan or transactionally apply supported component configuration fields."""

    if not changes:
        raise TopologyError("component configure requires at least one changed field")
    if changes.get("ownership") not in {None, "managed", "external"}:
        raise TopologyError("ownership must be managed or external")
    if "health_timeout" in changes and not 1 <= changes["health_timeout"] <= 3600:
        raise TopologyError("health timeout must be 1..3600 seconds")
    stack = CURRENT_TOPOLOGY.stacks[component.stack]
    command = ["llmops", "component", "configure", component.qualified_id]
    for key in ("host", "profile", "ownership"):
        if key in changes:
            command.extend((f"--{key}", str(changes[key])))
    if "enabled" in changes:
        command.append("--enable" if changes["enabled"] else "--disable")
    for dependency in changes.get("depends_on", []):
        command.extend(("--depends-on", dependency))
    if "health_timeout" in changes:
        command.extend(("--health-timeout", str(changes["health_timeout"])))
    command.append("--apply" if apply else "--plan")
    payload = {
        "component": component.qualified_id,
        "path": str(stack.path),
        "changes": changes,
        "command": command,
    }
    if not apply:
        return payload
    document = json.loads(stack.path.read_text(encoding="utf-8"))
    item = next((entry for entry in document["components"] if entry.get("id") == component.component_id), None)
    if item is None:
        raise TopologyError(f"component source not found: {component.qualified_id}")
    for key in ("host", "profile", "ownership", "enabled", "depends_on"):
        if key in changes:
            item[key] = changes[key]
    if "health_timeout" in changes:
        health = item.setdefault("health", {"type": component.health.kind})
        health["timeout_seconds"] = changes["health_timeout"]
    backup = stack.path.with_name(f"{stack.path.name}.backup-{time.strftime('%Y%m%dT%H%M%S')}")
    temporary = stack.path.with_name(f".{stack.path.name}.new-{os.getpid()}")
    shutil.copy2(stack.path, backup)
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, stack.path)
    try:
        refreshed = build_topology(config_home=str(CURRENT_TOPOLOGY.paths.config_home), inventory=str(CURRENT_TOPOLOGY.paths.inventory_file))
        errors = validate_topology(refreshed)
        if errors:
            raise TopologyError("invalid component update:\n" + "\n".join(errors))
    except Exception:
        os.replace(backup, stack.path)
        raise
    payload["backup"] = str(backup)
    payload["applied"] = True
    return payload


def cmd_component_configure(args: argparse.Namespace) -> int:
    component = CURRENT_TOPOLOGY.resolve_component(args.component)
    changes = _component_changes(args)
    payload = configure_component(component, changes, apply=False)
    if not args.apply:
        emit(payload, json_output=args.json)
        return 0
    if not args.yes:
        if args.json or not sys.stdin.isatty():
            raise TopologyError("component configure --apply requires --yes in non-interactive mode")
        print(json.dumps(payload, indent=2, sort_keys=True))
        if input("Apply this component configuration? [y/N]: ").strip().lower() not in {"y", "yes"}:
            return 0
    emit(configure_component(component, changes, apply=True), json_output=args.json)
    return 0


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
    columns = ("status", "component", "host", "driver", "profile", "version", "drift")
    widths = {
        column: max(len(column.upper()), *(len(str(item.get(column, ""))) for item in payload))
        for column in columns
    }
    print("  ".join(column.upper().ljust(widths[column]) for column in columns))
    print("  ".join("-" * widths[column] for column in columns))
    for item in payload:
        print("  ".join(str(item.get(column, "")).ljust(widths[column]) for column in columns))
    counts: dict[str, int] = {}
    for item in payload:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    print("\n" + "  ".join(f"{name}={counts[name]}" for name in sorted(counts)))


def _status_state(*, enabled: bool, returncode: Optional[int], error: str = "") -> str:
    if not enabled:
        return "disabled"
    if error:
        return "error"
    if returncode == 0:
        return "running"
    if returncode == 255:
        return "unreachable"
    return "not-running"


def _inspect_status(components: list[Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    runner = ComponentRunner(CURRENT_TOPOLOGY)
    enabled = [component for component in components if component.enabled]
    workers = min(max(1, args.workers), max(1, len(enabled)))
    def inspect(component: Any) -> tuple[str, Any, str]:
        try:
            return component.qualified_id, runner.status(component), ""
        except (DriverError, OSError) as exc:
            return component.qualified_id, None, str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        inspected = list(pool.map(inspect, enabled))
    by_component = {component: (result, error) for component, result, error in inspected}
    payload: list[dict[str, Any]] = []
    metadata = _runtime_metadata()
    include_detail = args.verbose or (bool(args.selector) and len(components) == 1)
    for component in components:
        result, error = by_component.get(component.qualified_id, (None, ""))
        status = _status_state(
            enabled=component.enabled,
            returncode=None if result is None else result.returncode,
            error=error,
        )
        item = {
            "status": status,
            "component": component.qualified_id,
            "host": component.host,
            "driver": component.driver,
            "profile": component.profile,
            "tags": list(component.tags),
            "returncode": None if result is None else result.returncode,
            **metadata,
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
        "version": version,
        "catalog_hash": catalog_hash,
        "config_hash": config_hash,
        "authority": authority,
        "drift": "none" if valid else "configuration",
        "last_sync": last_sync,
    }


def _load_observer_catalog() -> Optional[dict[str, Any]]:
    path = CURRENT_TOPOLOGY.paths.config_home / "catalog.json"
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
    return catalog


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
        "component": {"list", "plan", "start", "stop", "restart", "status", "logs"},
        "stack": {"list", "plan", "start", "stop", "restart", "status"},
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
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=args.host_timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TopologyError(f"host operation failed: {exc}") from exc
    if args.json:
        try:
            remote_output: Any = json.loads(completed.stdout)
        except json.JSONDecodeError:
            remote_output = completed.stdout.strip()
        emit(
            {
                "host": args.host,
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


def _current_snapshot_host() -> Optional[str]:
    path = CURRENT_TOPOLOGY.paths.config_home / "resolved.json"
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
    host: dict[str, Any], selector: Optional[str], args: argparse.Namespace
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
    remote.extend(("--local", "--json"))
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
        payload, error = _remote_status(host, args.selector, args)
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
            if error == "authority-only":
                payload.append(
                    {
                        "status": "authority-only",
                        "component": component.get("id", ""),
                        "host": host_name,
                        "driver": component.get("driver", ""),
                        "profile": component.get("profile", ""),
                        "tags": component.get("tags", []),
                        "returncode": None,
                    }
                )
                continue
            payload.append(
                {
                    "status": "unreachable",
                    "component": component.get("id", ""),
                    "host": host_name,
                    "driver": component.get("driver", ""),
                    "profile": component.get("profile", ""),
                    "tags": component.get("tags", []),
                    "returncode": 255,
                    "error": error,
                }
            )
    return sorted(payload, key=lambda item: str(item.get("component", "")))


def cmd_status(args: argparse.Namespace) -> int:
    catalog = None if args.local else _load_observer_catalog()
    if catalog is None:
        components = _status_components(args.selector, include_disabled=args.all)
        payload = _inspect_status(components, args)
    else:
        payload = _catalog_status(args, catalog)
    if args.json:
        emit(payload, json_output=True)
    else:
        _human_status(payload)
        if args.selector and len(payload) == 1:
            detail = payload[0].get("stdout", "") or payload[0].get("stderr", "")
            if detail:
                print(f"\n{detail}")
    return 0 if all(item["status"] in {"running", "disabled", "authority-only"} for item in payload) else 1


def cmd_component_mutate(args: argparse.Namespace) -> int:
    component = CURRENT_TOPOLOGY.resolve_component(args.component)
    executor = Executor(CURRENT_TOPOLOGY)
    if args.action == "stop" and not args.cascade:
        dependents = executor.active_dependents(component)
        if dependents and not args.force:
            names = ", ".join(item.qualified_id for item in dependents)
            raise ExecutionError(
                f"{component.qualified_id}: active dependents: {names}; use --force or --cascade"
            )
    results = executor.execute(component_operations(args))
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
    executor = Executor(CURRENT_TOPOLOGY)
    operations = stack_operations(args)
    results = executor.inspect(operations) if args.action == "status" else executor.execute(operations)
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
    config_hash = config_sub.add_parser("hash")
    config_hash.set_defaults(func=cmd_config_hash)
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
    configure = component_sub.add_parser("configure")
    configure.add_argument("component")
    configure.add_argument("--host")
    configure.add_argument("--profile")
    configure.add_argument("--ownership", choices=("managed", "external"))
    enabled = configure.add_mutually_exclusive_group()
    enabled.add_argument("--enable", dest="enabled", action="store_true")
    enabled.add_argument("--disable", dest="enabled", action="store_false")
    configure.set_defaults(enabled=None)
    configure.add_argument("--depends-on", action="append")
    configure.add_argument("--health-timeout", type=int)
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
    args = parser.parse_args(normalize_global_options(raw_argv))
    try:
        if getattr(args, "topology_required", True):
            CURRENT_TOPOLOGY = build_topology(
                config_home=args.config_home,
                inventory=args.inventory,
            )
        return args.func(args)
    except (
        ConfigError,
        InitError,
        InventoryError,
        MigrationError,
        TopologyError,
        DriverError,
        ExecutionError,
        AdapterError,
        ReconcileError,
    ) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"llmops: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
