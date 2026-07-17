#!/usr/bin/env python3
"""Immutable multi-host deployment for canonical LLM-Ops-Kit releases."""

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
import tarfile
import time
from pathlib import Path
from typing import Any, Optional

MODULE_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = MODULE_DIR.parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(MODULE_DIR))

from llmops_config import ConfigError, load_config
from llmops_inventory import HostRecord, InventoryError, load_inventory, select_hosts
from llmops_paths import resolve_paths
from llmops_topology import Topology, TopologyError, load_stacks, validate_topology, write_host_snapshot


class DeploymentError(RuntimeError):
    """Raised when a deployment cannot be planned or completed safely."""


INTERNAL_COMMANDS = (
    "llmops",
    "llmops-control",
    "modelctl",
    "model-proxy",
    "tts-bridge",
    "tts",
    "runtime-maintenance",
    "precheck",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _remote_path(path: str) -> str:
    if path == "~":
        return '"$HOME"'
    if path.startswith("~/"):
        return '"$HOME"/' + shlex.quote(path[2:])
    return shlex.quote(path)


def _run(command: list[str], *, dry_run: bool = False, attempts: int = 1) -> tuple[int, str]:
    rendered = " ".join(shlex.quote(token) for token in command)
    if dry_run:
        return 0, rendered
    output = ""
    for attempt in range(1, attempts + 1):
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
        if completed.returncode == 0:
            return 0, output
        if attempt < attempts:
            time.sleep(min(4.0, 0.5 * (2 ** (attempt - 1))))
    return completed.returncode, output


def _scp_base(host: HostRecord) -> list[str]:
    command = ["scp", "-P", str(host.port), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
    if host.ssh_key_path is not None:
        command.extend(["-i", str(host.ssh_key_path)])
    if host.proxy_jump:
        command.extend(["-o", f"ProxyJump={host.proxy_jump}"])
    return command


def _host_command(host: HostRecord, script: str) -> list[str]:
    if host.transport == "local":
        return ["/bin/sh", "-c", script]
    return host.ssh_base() + [script]


def _copy_to_host(host: HostRecord, source: Path, destination: str, *, dry_run: bool) -> tuple[int, str]:
    if host.transport == "local":
        target = Path(destination).expanduser()
        if dry_run:
            return 0, f"cp {source} {target}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return 0, ""
    return _run(_scp_base(host) + [str(source), f"{host.destination}:{destination}"], dry_run=dry_run, attempts=3)


def _topology(config_home: Optional[str], inventory_path: Optional[str]) -> Topology:
    env = dict(os.environ)
    if config_home:
        env["LLMOPS_CONFIG_HOME"] = config_home
    paths = resolve_paths(env)
    inventory_file = Path(inventory_path).expanduser() if inventory_path else paths.inventory_file
    topology = Topology(
        stacks=load_stacks(paths),
        hosts=load_inventory(inventory_file),
        paths=paths,
        config=load_config(paths=paths),
    )
    errors = validate_topology(topology)
    if errors:
        raise DeploymentError("invalid topology:\n" + "\n".join(f"- {error}" for error in errors))
    return topology


def _selected(topology: Topology, args: argparse.Namespace) -> dict[str, HostRecord]:
    return select_hosts(topology.hosts, names=args.host_name, role=args.role, tags=args.tag)


def _source_root(args: argparse.Namespace, topology: Topology) -> Path:
    deployment = topology.config.data.get("deployment", {})
    configured = deployment.get("source_root") if isinstance(deployment, dict) else None
    source = Path(args.source or configured or REPO_ROOT).expanduser().resolve()
    if not (source / "scripts").is_dir() or not (source / "bin").is_dir():
        raise DeploymentError(f"invalid deployment source checkout: {source}")
    return source


def _git_provenance(source_root: Path) -> dict[str, Any]:
    revision = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    status = subprocess.run(["git", "-C", str(source_root), "status", "--porcelain"], capture_output=True, text=True, check=False)
    describe = subprocess.run(["git", "-C", str(source_root), "describe", "--tags", "--always", "--dirty"], capture_output=True, text=True, check=False)
    if revision.returncode != 0 or status.returncode != 0:
        raise DeploymentError(f"deployment source is not a Git checkout: {source_root}")
    return {
        "root": str(source_root),
        "git_commit": revision.stdout.strip(),
        "git_dirty": bool(status.stdout.strip()),
        "toolkit_version": describe.stdout.strip() if describe.returncode == 0 else "unknown",
    }


def _build_package(stage: Path, source_root: Path) -> Path:
    package = stage / "package" / "llm-ops-kit.tar.gz"
    package.parent.mkdir(parents=True, exist_ok=True)
    tracked = subprocess.run(
        ["git", "-C", str(source_root), "ls-files", "-z", "--", "scripts", "bin"],
        capture_output=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise DeploymentError(f"cannot enumerate tracked deployment files: {tracked.stderr.decode(errors='replace')}")
    names = [Path(raw.decode()) for raw in tracked.stdout.split(b"\0") if raw]
    names = [
        name
        for name in names
        if "tests" not in name.parts
        and "__pycache__" not in name.parts
        and not name.name.endswith((".pyc", ".pyo", ".DS_Store"))
    ]
    if not names:
        raise DeploymentError(f"deployment source has no tracked runtime files: {source_root}")
    with tarfile.open(package, "w:gz") as archive:
        for name in sorted(names):
            source = source_root / name
            if not source.exists() and not source.is_symlink():
                raise DeploymentError(f"tracked deployment file is missing: {source}")
            archive.add(source, arcname=Path("LLM-Ops-Kit") / name, recursive=False)
    return package


def _snapshot(stage: Path, topology: Topology, host: HostRecord) -> Path:
    host_dir = stage / "hosts" / host.name
    snapshot = host_dir / "snapshot"
    archive_path = host_dir / "config.tar.gz"
    write_host_snapshot(topology, host_name=host.name, destination=snapshot)
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(snapshot.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(snapshot), recursive=False)
    shutil.rmtree(snapshot)
    return archive_path


def stage_bundle(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    """Build one checksummed package and one role-filtered snapshot per host."""

    topology = _topology(args.config_home, args.inventory)
    hosts = _selected(topology, args)
    source_root = _source_root(args, topology)
    provenance = _git_provenance(source_root)
    if provenance["git_dirty"] and not args.allow_dirty:
        raise DeploymentError("deployment refuses a dirty source tree; commit changes or use --allow-dirty")
    bundle_id = args.bundle_id or time.strftime("%Y%m%d-%H%M%S")
    stage = Path(args.stage_root).expanduser() / bundle_id
    if args.dry_run:
        return stage, {"bundle_id": bundle_id, "hosts": sorted(hosts), "dry_run": True}
    if stage.exists():
        raise DeploymentError(f"stage already exists: {stage}")
    stage.mkdir(parents=True)
    package = _build_package(stage, source_root)
    host_entries: list[dict[str, Any]] = []
    for host in hosts.values():
        snapshot = _snapshot(stage, topology, host)
        host_entries.append(
            {
                "name": host.name,
                "role": host.role,
                "host": host.host,
                "user": host.user,
                "port": host.port,
                "transport": host.transport,
                "install_root": host.install_root,
                "public_bin_dir": host.public_bin_dir,
                "config_sha256": _sha256(snapshot),
            }
        )
    manifest = {
        "schema_version": 2,
        "bundle_id": bundle_id,
        "created_at": int(time.time()),
        "package_sha256": _sha256(package),
        "source": provenance,
        "hosts": sorted(host_entries, key=lambda item: item["name"]),
    }
    (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validate_stage(stage, hosts)
    return stage, manifest


def validate_stage(stage: Path, hosts: dict[str, HostRecord]) -> dict[str, Any]:
    """Validate every checksummed stage artifact."""

    manifest_path = stage / "manifest.json"
    package = stage / "package" / "llm-ops-kit.tar.gz"
    if not manifest_path.is_file() or not package.is_file():
        raise DeploymentError(f"incomplete stage: {stage}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 2 or manifest.get("bundle_id") != stage.name:
        raise DeploymentError(f"invalid stage manifest: {manifest_path}")
    if manifest.get("package_sha256") != _sha256(package):
        raise DeploymentError(f"package checksum mismatch: {package}")
    entries = {item["name"]: item for item in manifest.get("hosts", [])}
    for name in hosts:
        snapshot = stage / "hosts" / name / "config.tar.gz"
        if name not in entries or not snapshot.is_file():
            raise DeploymentError(f"stage missing host snapshot: {name}")
        if entries[name].get("config_sha256") != _sha256(snapshot):
            raise DeploymentError(f"host snapshot checksum mismatch: {snapshot}")
    return manifest


def _push_one(stage: Path, host: HostRecord, *, dry_run: bool) -> dict[str, Any]:
    root = _remote_path(host.install_root)
    package_dir = f"{host.install_root}/packages/{stage.name}"
    outputs: list[str] = []
    code, output = _run(
        _host_command(host, f"mkdir -p {root}/packages/{shlex.quote(stage.name)} {root}/config"),
        dry_run=dry_run,
        attempts=3,
    )
    outputs.append(output)
    if code == 0:
        for source, destination in (
            (stage / "package" / "llm-ops-kit.tar.gz", f"{package_dir}/llm-ops-kit.tar.gz"),
            (stage / "manifest.json", f"{package_dir}/manifest.json"),
            (stage / "hosts" / host.name / "config.tar.gz", f"{package_dir}/config.tar.gz"),
        ):
            code, output = _copy_to_host(host, source, destination, dry_run=dry_run)
            outputs.append(output)
            if code != 0:
                break
    return {"host": host.name, "ok": code == 0, "returncode": code, "output": "\n".join(filter(None, outputs))}


def push_bundle(stage: Path, hosts: dict[str, HostRecord], *, dry_run: bool, workers: int) -> list[dict[str, Any]]:
    validate_stage(stage, hosts)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda host: _push_one(stage, host, dry_run=dry_run), hosts.values()))
    return sorted(results, key=lambda item: item["host"])


def _link_script(host: HostRecord) -> str:
    names = " ".join(shlex.quote(name) for name in INTERNAL_COMMANDS)
    public_bin = _remote_path(host.public_bin_dir)
    return (
        f"public_bin={public_bin}; "
        'mkdir -p "$root/bin" "$public_bin"; '
        f"for name in {names}; do "
        'source="$current/scripts/$name"; test -x "$source" || continue; '
        'ln -sfn "$source" "$root/bin/$name"; done; '
        'ln -sfn "$current/scripts/llmops" "$public_bin/llmops"'
    )


def _apply_one(stage: Path, host: HostRecord, manifest: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    entry = next(item for item in manifest["hosts"] if item["name"] == host.name)
    root = _remote_path(host.install_root)
    script = "; ".join(
        [
            "set -eu",
            f"root={root}",
            f"bundle={shlex.quote(stage.name)}",
            f"expected_package={shlex.quote(manifest['package_sha256'])}",
            f"expected_config={shlex.quote(entry['config_sha256'])}",
            'package="$root/packages/$bundle/llm-ops-kit.tar.gz"',
            'config_archive="$root/packages/$bundle/config.tar.gz"',
            'manifest="$root/packages/$bundle/manifest.json"',
            'release="$root/releases/$bundle"',
            'current="$root/current"',
            'old=""; previous_old=""; previous_existed=0; switched=0; release_created=0',
            'checksum() { shasum -a 256 "$1" | awk \'{print $1}\'; }',
            'replace_link() { src=$1; dst=$2; if mv -fh "$src" "$dst" 2>/dev/null; then return 0; fi; rm -f "$dst"; mv -f "$src" "$dst"; }',
            'rollback_apply() { rc=$?; trap - EXIT HUP INT TERM; if [ "$switched" -eq 1 ]; then if [ -n "$old" ]; then ln -s "$old" "$root/.current.rollback.$$"; replace_link "$root/.current.rollback.$$" "$current"; else rm -f "$current"; fi; if [ "$previous_existed" -eq 1 ]; then ln -s "$previous_old" "$root/.previous.rollback.$$"; replace_link "$root/.previous.rollback.$$" "$root/previous"; else rm -f "$root/previous"; fi; fi; if [ "$release_created" -eq 1 ]; then rm -rf "$release"; fi; exit "$rc"; }',
            'trap rollback_apply EXIT HUP INT TERM',
            'test -f "$package" && test -f "$config_archive" && test -f "$manifest"',
            'test "$(checksum "$package")" = "$expected_package"',
            'test "$(checksum "$config_archive")" = "$expected_config"',
            'test ! -e "$release"',
            'mkdir -p "$release/config"',
            'release_created=1',
            'tar -xzf "$package" -C "$release" --strip-components=1',
            'tar -xzf "$config_archive" -C "$release/config"',
            'cp "$manifest" "$release/manifest.json"',
            'cp "$config_archive" "$release/config.tar.gz"',
            'printf \'%s\\n\' "$bundle" > "$release/BUNDLE_ID"',
            'if [ -L "$current" ]; then old=$(readlink "$current"); elif [ -e "$current" ]; then exit 3; fi',
            'if [ -L "$root/previous" ]; then previous_old=$(readlink "$root/previous"); previous_existed=1; fi',
            'switched=1',
            'if [ -n "$old" ]; then ln -s "$old" "$root/.previous.$$"; replace_link "$root/.previous.$$" "$root/previous"; fi',
            'ln -s "$release" "$root/.current.$$"',
            'replace_link "$root/.current.$$" "$current"',
            _link_script(host),
            'test -x "$current/scripts/llmops" && test -x "$current/scripts/llmops-control"',
            'trap - EXIT HUP INT TERM',
        ]
    )
    code, output = _run(_host_command(host, script), dry_run=dry_run, attempts=3)
    return {"host": host.name, "ok": code == 0, "returncode": code, "output": output}


def apply_bundle(stage: Path, hosts: dict[str, HostRecord], *, dry_run: bool, workers: int) -> list[dict[str, Any]]:
    manifest = validate_stage(stage, hosts)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda host: _apply_one(stage, host, manifest, dry_run=dry_run), hosts.values()))
    return sorted(results, key=lambda item: item["host"])


def _drift_one(stage: Path, host: HostRecord, manifest: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    root = _remote_path(host.install_root)
    script = "; ".join(
        [
            "set -eu",
            f"root={root}",
            'current="$root/current"',
            'test -L "$current"',
            'printf "bundle_id=%s\\n" "$(cat "$current/BUNDLE_ID")"',
            'printf "manifest_sha256=%s\\n" "$(shasum -a 256 "$current/manifest.json" | awk \'{print $1}\')"',
            'printf "config_sha256=%s\\n" "$(shasum -a 256 "$current/config.tar.gz" | awk \'{print $1}\')"',
        ]
    )
    code, output = _run(_host_command(host, script), dry_run=dry_run, attempts=3)
    if dry_run:
        return {"host": host.name, "ok": True, "dry_run": True, "command": output}
    observed = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    entry = next(item for item in manifest["hosts"] if item["name"] == host.name)
    expected = {
        "bundle_id": stage.name,
        "manifest_sha256": _sha256(stage / "manifest.json"),
        "config_sha256": entry["config_sha256"],
    }
    differences = {key: {"expected": value, "observed": observed.get(key, "")} for key, value in expected.items() if observed.get(key) != value}
    return {"host": host.name, "ok": code == 0 and not differences, "reachable": code == 0, "differences": differences, "error": output if code else ""}


def drift_bundle(stage: Path, hosts: dict[str, HostRecord], *, dry_run: bool, workers: int) -> list[dict[str, Any]]:
    manifest = validate_stage(stage, hosts)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda host: _drift_one(stage, host, manifest, dry_run=dry_run), hosts.values()))
    return sorted(results, key=lambda item: item["host"])


def _rollback_one(host: HostRecord, *, dry_run: bool) -> dict[str, Any]:
    root = _remote_path(host.install_root)
    script = "; ".join(
        [
            "set -eu",
            f"root={root}",
            'current="$root/current"; previous="$root/previous"',
            'test -L "$current" && test -L "$previous"',
            'current_target=$(readlink "$current"); previous_target=$(readlink "$previous")',
            'test -d "$current_target" && test -d "$previous_target"',
            'replace_link() { src=$1; dst=$2; if mv -fh "$src" "$dst" 2>/dev/null; then return 0; fi; rm -f "$dst"; mv -f "$src" "$dst"; }',
            'ln -s "$previous_target" "$root/.current.$$"; ln -s "$current_target" "$root/.previous.$$"',
            'replace_link "$root/.current.$$" "$current"; replace_link "$root/.previous.$$" "$previous"',
            _link_script(host),
            'printf "current=%s\\nprevious=%s\\n" "$(readlink "$current")" "$(readlink "$previous")"',
        ]
    )
    code, output = _run(_host_command(host, script), dry_run=dry_run, attempts=3)
    return {"host": host.name, "ok": code == 0, "returncode": code, "output": output}


def _stage_for(args: argparse.Namespace) -> Path:
    if args.stage:
        return Path(args.stage).expanduser()
    stages = sorted(path for path in Path(args.stage_root).expanduser().glob("*") if path.is_dir())
    if not stages:
        raise DeploymentError(f"no staged bundles under: {args.stage_root}")
    return stages[-1]


def _emit(action: str, results: list[dict[str, Any]], *, json_output: bool) -> int:
    ok = all(item.get("ok", False) for item in results)
    if json_output:
        print(json.dumps({"ok": ok, "action": action, "hosts": results}, indent=2, sort_keys=True))
    else:
        for item in results:
            print(f"[{item['host']}] {action} {'OK' if item.get('ok') else 'FAILED'}")
            if item.get("output"):
                print(item["output"])
            for key, difference in item.get("differences", {}).items():
                print(f"  {key}: expected={difference['expected']} observed={difference['observed']}")
    return 0 if ok else 1


def cmd_deploy(args: argparse.Namespace) -> int:
    stage, manifest = stage_bundle(args)
    topology = _topology(args.config_home, args.inventory)
    hosts = _selected(topology, args)
    if args.dry_run:
        return _emit("deploy-plan", [{"host": name, "ok": True, "output": str(stage)} for name in hosts], json_output=args.json)
    pushed = push_bundle(stage, hosts, dry_run=False, workers=args.workers)
    if not all(item["ok"] for item in pushed):
        return _emit("push", pushed, json_output=args.json)
    applied = apply_bundle(stage, hosts, dry_run=False, workers=args.workers)
    if not all(item["ok"] for item in applied):
        return _emit("apply", applied, json_output=args.json)
    return _emit("deploy", drift_bundle(stage, hosts, dry_run=False, workers=args.workers), json_output=args.json)


def cmd_drift(args: argparse.Namespace) -> int:
    topology = _topology(args.config_home, args.inventory)
    hosts = _selected(topology, args)
    return _emit("drift", drift_bundle(_stage_for(args), hosts, dry_run=args.dry_run, workers=args.workers), json_output=args.json)


def cmd_rollback(args: argparse.Namespace) -> int:
    topology = _topology(args.config_home, args.inventory)
    hosts = _selected(topology, args)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda host: _rollback_one(host, dry_run=args.dry_run), hosts.values()))
    return _emit("rollback", sorted(results, key=lambda item: item["host"]), json_output=args.json)


def _selectors(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config-home")
    parser.add_argument("--inventory")
    parser.add_argument("--host-name", action="append")
    parser.add_argument("--role", choices=("admin", "llm", "agent", "hybrid"))
    parser.add_argument("--tag", action="append")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM-Ops-Kit immutable deployment")
    subparsers = parser.add_subparsers(dest="command", required=True)
    deploy = subparsers.add_parser("deploy")
    _selectors(deploy)
    deploy.add_argument("--stage-root", default=str(resolve_paths().stage_dir))
    deploy.add_argument("--source")
    deploy.add_argument("--bundle-id")
    deploy.add_argument("--allow-dirty", action="store_true")
    deploy.set_defaults(func=cmd_deploy)
    drift = subparsers.add_parser("drift")
    _selectors(drift)
    drift.add_argument("--stage-root", default=str(resolve_paths().stage_dir))
    drift.add_argument("--stage")
    drift.set_defaults(func=cmd_drift)
    rollback = subparsers.add_parser("rollback")
    _selectors(rollback)
    rollback.set_defaults(func=cmd_rollback)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, DeploymentError, InventoryError, TopologyError) as exc:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"llmops: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
