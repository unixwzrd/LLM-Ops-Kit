#!/usr/bin/env python
"""Repository-free release discovery and atomic local runtime updates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


class UpdateError(RuntimeError):
    """Raised when an update cannot be planned or applied safely."""


VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
USER_AGENT = "LLM-Ops-Kit update"


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of path."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def current_version(install_base: Path) -> Optional[str]:
    """Return the active immutable release version, if installed."""

    current = install_base / "current"
    if not current.is_symlink():
        return None
    release_file = current / "RELEASE.json"
    try:
        value = json.loads(release_file.read_text(encoding="utf-8")).get("version")
        if isinstance(value, str) and value:
            return value
    except (OSError, json.JSONDecodeError):
        pass
    return current.resolve().name


def resolve_latest(repository: str) -> str:
    """Resolve the latest GitHub release tag through its stable redirect."""

    request = urllib.request.Request(
        f"https://github.com/{repository}/releases/latest",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            version = response.geturl().rstrip("/").rsplit("/", 1)[-1]
    except (OSError, urllib.error.URLError) as exc:
        raise UpdateError(f"could not resolve the latest release: {exc}") from exc
    if not VERSION_RE.fullmatch(version):
        raise UpdateError(f"GitHub returned an invalid release version: {version}")
    return version


def archive_version(path: Path) -> str:
    """Extract a release version from a canonical artifact filename."""

    name = path.name
    prefix = "LLM-Ops-Kit-"
    suffix = ".tar.xz"
    if not name.startswith(prefix) or not name.endswith(suffix):
        raise UpdateError(f"invalid release archive name: {name}")
    version = name[len(prefix) : -len(suffix)]
    if not VERSION_RE.fullmatch(version):
        raise UpdateError(f"invalid release version: {version}")
    return version


def download(url: str, destination: Path) -> None:
    """Download one release asset with bounded retries."""

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Optional[Exception] = None
    for _attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response, destination.open("wb") as stream:
                shutil.copyfileobj(response, stream)
            return
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
    raise UpdateError(f"download failed: {url}: {last_error}")


def verify_archive(archive: Path, checksum_file: Path) -> None:
    """Verify archive against the first digest in checksum_file."""

    try:
        expected = checksum_file.read_text(encoding="utf-8").split()[0].lower()
    except (OSError, IndexError) as exc:
        raise UpdateError(f"could not read checksum file: {checksum_file}") from exc
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise UpdateError(f"invalid checksum file: {checksum_file}")
    if sha256(archive) != expected:
        raise UpdateError(f"archive checksum mismatch: {archive}")


def safe_extract(archive: Path, destination: Path) -> Path:
    """Extract a verified archive after rejecting unsafe member paths."""

    destination_resolved = destination.resolve()
    with tarfile.open(archive, "r:xz") as bundle:
        members = bundle.getmembers()
        for member in members:
            target = (destination / member.name).resolve()
            if destination_resolved not in target.parents and target != destination_resolved:
                raise UpdateError(f"unsafe archive member: {member.name}")
            if member.issym() or member.islnk():
                raise UpdateError(f"release archives may not contain links: {member.name}")
        bundle.extractall(destination, filter="data")
    installers = list(destination.glob("*/scripts/install-runtime.sh"))
    if len(installers) != 1:
        raise UpdateError("release archive must contain exactly one runtime installer")
    return installers[0]


def release_assets(
    *,
    repository: str,
    version: str,
    archive: Optional[Path],
    checksum_file: Optional[Path],
    temporary: Path,
) -> tuple[Path, Path]:
    """Return local verified release asset paths."""

    if archive is not None:
        if checksum_file is None:
            raise UpdateError("--archive requires --checksum-file")
        return archive.expanduser().resolve(), checksum_file.expanduser().resolve()
    archive_name = f"LLM-Ops-Kit-{version}.tar.xz"
    base = f"https://github.com/{repository}/releases/download/{version}"
    downloaded_archive = temporary / archive_name
    downloaded_checksum = temporary / f"{archive_name}.sha256"
    download(f"{base}/{archive_name}", downloaded_archive)
    download(f"{base}/{archive_name}.sha256", downloaded_checksum)
    return downloaded_archive, downloaded_checksum


def emit(payload: dict[str, object], *, json_output: bool) -> None:
    """Print stable JSON or concise operator output."""

    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    current_label = "controller current" if payload.get("current_scope") == "controller" else "current"
    print(f"{current_label}: {payload.get('current') or 'not installed'}")
    print(f"available: {payload['available']}")
    print(f"action: {payload['action']}")


def _catalog_path(prefix: Path, config_home: Optional[Path]) -> Path:
    if config_home is not None:
        return config_home.expanduser() / "catalog.json"
    configured = os.environ.get("LLMOPS_CONFIG_HOME")
    if configured:
        candidate = Path(configured).expanduser() / "catalog.json"
        if candidate.is_file():
            return candidate
    managed = prefix / "current-config" / "catalog.json"
    return managed if managed.is_file() else prefix / "current" / "config" / "catalog.json"


def _load_hosts(prefix: Path, config_home: Optional[Path]) -> dict[str, dict[str, object]]:
    path = _catalog_path(prefix, config_home)
    if not path.is_file() and config_home is not None:
        inventory = config_home.expanduser() / "inventory.json"
        if inventory.is_file():
            path = inventory
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UpdateError(f"could not load host catalog {path}: {exc}") from exc
    hosts = catalog.get("hosts") if isinstance(catalog, dict) else None
    if not isinstance(hosts, list):
        raise UpdateError(f"host catalog is incomplete: {path}")
    return {
        str(item["name"]): item
        for item in hosts
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def _ssh_base(host: dict[str, object]) -> list[str]:
    return [
        "ssh",
        "-p",
        str(host.get("port", 22)),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{host['user']}@{host['host']}",
    ]


def _remote_public_command(host: dict[str, object]) -> str:
    root = str(host.get("public_bin_dir", "~/.local/bin"))
    if root.startswith("~/"):
        return '"$HOME"/' + shlex.quote(root[2:] + "/llmops")
    return shlex.quote(str(Path(root) / "llmops"))


def _remote_path(value: object) -> str:
    """Return a shell expression for an absolute or home-relative remote path."""

    path = str(value)
    if path.startswith("~/"):
        return '"$HOME"/' + shlex.quote(path[2:])
    return shlex.quote(path)


def _select_hosts(args: argparse.Namespace) -> list[tuple[str, dict[str, object]]]:
    hosts = _load_hosts(args.prefix, args.config_home)
    requested = list(dict.fromkeys(args.hosts or []))
    if args.all_hosts:
        requested = sorted(name for name, host in hosts.items() if host.get("peer_observable", True) is not False)
    missing = [name for name in requested if name not in hosts]
    if missing:
        raise UpdateError(f"catalog host not found: {', '.join(missing)}")
    return [(name, hosts[name]) for name in requested]


def _run_remote(host: dict[str, object], script: str, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            _ssh_base(host) + [script],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"SSH operation failed for {host.get('name', host.get('host'))}: {exc}") from exc


def _remote_preflight(name: str, host: dict[str, object], timeout: int) -> dict[str, object]:
    install_root = _remote_path(host.get("install_root", "~/.local/llm-ops"))
    command = (
        "set -eu; test \"$(uname -s)\" = Darwin; "
        "available=$(df -Pk \"$HOME\" | awk 'NR==2 {print $4}'); "
        "test \"$available\" -ge 204800; "
        f"release={install_root}/current/RELEASE.json; "
        "if test -f \"$release\"; then cat \"$release\"; else printf '{\"installed\":false}\\n'; fi"
    )
    completed = _run_remote(host, command, timeout)
    if completed.returncode != 0:
        raise UpdateError(f"remote preflight failed for {name}: {completed.stderr.strip() or completed.stdout.strip()}")
    try:
        detail = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise UpdateError(f"remote preflight returned invalid release metadata for {name}") from exc
    installed_version = detail.get("version") if isinstance(detail, dict) else None
    return {
        "host": name,
        "ok": True,
        "installed": installed_version is not None,
        "version": installed_version or "",
    }


def _remote_stage(
    name: str,
    host: dict[str, object],
    archive: Path,
    checksum_file: Path,
    version: str,
    timeout: int,
) -> tuple[str, str]:
    relative = f".cache/llm-ops/updates/{version}"
    completed = _run_remote(host, f"mkdir -p {shlex.quote(relative)}", timeout)
    if completed.returncode != 0:
        raise UpdateError(f"could not create update stage on {name}: {completed.stderr.strip()}")
    destination = f"{host['user']}@{host['host']}:{relative}/"
    scp = ["scp", "-P", str(host.get("port", 22)), "-o", "BatchMode=yes", str(archive), str(checksum_file), destination]
    try:
        copied = subprocess.run(scp, capture_output=True, text=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"update transfer failed for {name}: {exc}") from exc
    if copied.returncode != 0:
        raise UpdateError(f"update transfer failed for {name}: {copied.stderr.strip()}")
    return f"$HOME/{relative}/{archive.name}", f"$HOME/{relative}/{checksum_file.name}"


def _remote_apply(
    name: str,
    host: dict[str, object],
    archive: str,
    checksum: str,
    version: str,
    timeout: int,
) -> dict[str, object]:
    llmops = _remote_public_command(host)
    install_root = _remote_path(host.get("install_root", "~/.local/llm-ops"))
    public_bin = _remote_path(host.get("public_bin_dir", "~/.local/bin"))
    state_home = _remote_path(host.get("state_home", "~/.local/state/llm-ops"))
    install_args = f"--prefix {install_root} --public-bin-dir {public_bin} --state-home {state_home}"
    script = (
        f"if test -x {llmops}; then "
        f"{llmops} update --apply --archive \"{archive}\" --checksum-file \"{checksum}\" {install_args}; "
        "else "
        f"stage=$(dirname \"{archive}\"); cd \"$stage\"; "
        f"shasum -a 256 -c \"{checksum}\"; rm -rf extracted; mkdir extracted; "
        f"tar -xJf \"{archive}\" -C extracted; "
        "installer=$(find extracted -path '*/scripts/install-runtime.sh' -type f -print -quit); "
        "test -n \"$installer\"; "
        f"/usr/local/bin/bash \"$installer\" --source \"$(dirname \"$(dirname \"$installer\")\")\" --release-id {shlex.quote(version)} {install_args}; "
        "fi"
    )
    completed = _run_remote(host, script, timeout)
    if completed.returncode != 0:
        raise UpdateError(f"remote update failed for {name}: {completed.stderr.strip() or completed.stdout.strip()}")
    try:
        verification = _remote_verify(name, host, version, timeout)
    except UpdateError as exc:
        rollback = _remote_rollback(name, host, timeout)
        raise UpdateError(f"{exc}; verification rollback: {json.dumps(rollback, sort_keys=True)}") from exc
    return {"host": name, "ok": True, "output": completed.stdout.strip(), **verification}


def _remote_verify(name: str, host: dict[str, object], version: str, timeout: int) -> dict[str, object]:
    """Verify the active release and canonical configuration after remote apply."""

    llmops = _remote_public_command(host)
    install_root = _remote_path(host.get("install_root", "~/.local/llm-ops"))
    script = "; ".join(
        [
            "set -eu",
            f"root={install_root}",
            'active=$(basename "$(readlink "$root/current")")',
            'printf "VERSION=%s\\n" "$active"',
            'catalog="$root/current-config/catalog.json"',
            'if test -f "$catalog"; then printf "CATALOG=%s\\n" "$(shasum -a 256 "$catalog" | awk \'{print $1}\')"; else printf "CATALOG=\\n"; fi',
            f"{llmops} config hash --json",
        ]
    )
    completed = _run_remote(host, script, timeout)
    if completed.returncode != 0:
        raise UpdateError(f"remote verification failed for {name}: {completed.stderr.strip() or completed.stdout.strip()}")
    lines = completed.stdout.splitlines()
    if len(lines) < 3 or not lines[0].startswith("VERSION=") or not lines[1].startswith("CATALOG="):
        raise UpdateError(f"remote verification returned invalid output for {name}")
    observed_version = lines[0].split("=", 1)[1]
    try:
        config = json.loads("\n".join(lines[2:]))
    except json.JSONDecodeError as exc:
        raise UpdateError(f"remote verification returned invalid configuration identity for {name}") from exc
    if observed_version != version:
        raise UpdateError(f"remote verification version mismatch for {name}: expected {version}, observed {observed_version}")
    if not isinstance(config, dict) or not config.get("ok") or not config.get("valid"):
        raise UpdateError(f"remote configuration verification failed for {name}: {config}")
    return {
        "version": observed_version,
        "catalog_hash": lines[1].split("=", 1)[1],
        "config_hash": str(config.get("config_hash", "")),
    }


def _remote_rollback(name: str, host: dict[str, object], timeout: int) -> dict[str, object]:
    llmops = _remote_public_command(host)
    install_root = _remote_path(host.get("install_root", "~/.local/llm-ops"))
    public_bin = _remote_path(host.get("public_bin_dir", "~/.local/bin"))
    state_home = _remote_path(host.get("state_home", "~/.local/state/llm-ops"))
    completed = _run_remote(
        host,
        f"{llmops} update --rollback --prefix {install_root} --public-bin-dir {public_bin} --state-home {state_home}",
        timeout,
    )
    return {
        "host": name,
        "ok": completed.returncode == 0,
        "output": completed.stdout.strip(),
        "error": completed.stderr.strip(),
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description="Check, plan, or apply a verified LLM-Ops-Kit release")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="Report the current and available release (default)")
    action.add_argument("--plan", action="store_true", help="Describe the update without downloading or changing files")
    action.add_argument("--apply", action="store_true", help="Download, verify, and atomically install the release")
    action.add_argument("--rollback", action="store_true", help="Exchange current and previous local releases")
    parser.add_argument("--version", help="Release tag; defaults to the latest GitHub release")
    parser.add_argument("--repository", default=os.environ.get("LLMOPS_GITHUB_REPOSITORY", "unixwzrd/LLM-Ops-Kit"))
    parser.add_argument("--archive", type=Path, help="Use a local release artifact")
    parser.add_argument("--checksum-file", type=Path, help="SHA-256 file for --archive")
    parser.add_argument("--prefix", type=Path, default=Path(os.environ.get("LLMOPS_HOME", "~/.local/llm-ops")).expanduser())
    parser.add_argument("--public-bin-dir", type=Path, default=Path(os.environ.get("LLMOPS_PUBLIC_BIN_DIR", "~/.local/bin")).expanduser())
    parser.add_argument("--state-home", type=Path, default=Path(os.environ.get("LLMOPS_STATE_HOME", "~/.local/state/llm-ops")).expanduser())
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--host", "--hosts", dest="hosts", action="append", default=[], help="Update one catalog host; repeatable")
    parser.add_argument("--all-hosts", action="store_true", help="Update every host in the observer catalog")
    parser.add_argument("--config-home", type=Path)
    parser.add_argument("--host-timeout", type=int, default=900)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Run release discovery or a verified local update."""

    args = build_parser().parse_args(argv)
    try:
        if args.rollback:
            installer = args.prefix / "current" / "scripts" / "install-runtime.sh"
            if not installer.is_file():
                raise UpdateError(f"active rollback installer is missing: {installer}")
            completed = subprocess.run(
                ["/usr/local/bin/bash", str(installer), "--prefix", str(args.prefix), "--public-bin-dir", str(args.public_bin_dir), "--state-home", str(args.state_home), "--rollback"],
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise UpdateError(f"rollback failed with status {completed.returncode}")
            return 0
        if not REPOSITORY_RE.fullmatch(args.repository):
            raise UpdateError("invalid GitHub repository; expected owner/name")
        if args.archive is not None:
            available = archive_version(args.archive)
        else:
            available = args.version or resolve_latest(args.repository)
            if not VERSION_RE.fullmatch(available):
                raise UpdateError(f"invalid release version: {available}")
        installed = current_version(args.prefix)
        action = "apply" if args.apply else "plan" if args.plan else "check"
        payload: dict[str, object] = {
            "ok": True,
            "action": action,
            "current": installed,
            "available": available,
            "update_available": installed != available,
            "repository": args.repository,
        }
        selected_hosts = _select_hosts(args) if args.hosts or args.all_hosts else []
        if selected_hosts:
            preflight = [_remote_preflight(name, host, args.host_timeout) for name, host in selected_hosts]
            payload["hosts"] = preflight
            payload["current_scope"] = "controller"
            payload["update_available"] = any(item.get("version") != available for item in preflight)
            if not args.apply:
                emit(payload, json_output=args.json)
                return 0
            with tempfile.TemporaryDirectory(prefix="llmops-update-") as temporary_name:
                temporary = Path(temporary_name)
                archive, checksum_file = release_assets(
                    repository=args.repository,
                    version=available,
                    archive=args.archive,
                    checksum_file=args.checksum_file,
                    temporary=temporary,
                )
                verify_archive(archive, checksum_file)
                staged = [
                    (name, host, *_remote_stage(name, host, archive, checksum_file, available, args.host_timeout))
                    for name, host in selected_hosts
                ]
                updated: list[tuple[str, dict[str, object]]] = []
                results: list[dict[str, object]] = []
                try:
                    for name, host, remote_archive, remote_checksum in staged:
                        results.append(_remote_apply(name, host, remote_archive, remote_checksum, available, args.host_timeout))
                        updated.append((name, host))
                except UpdateError as exc:
                    rollbacks = [_remote_rollback(name, host, args.host_timeout) for name, host in reversed(updated)]
                    raise UpdateError(f"{exc}; rollback results: {json.dumps(rollbacks, sort_keys=True)}") from exc
                payload["hosts"] = results
            emit(payload, json_output=args.json)
            return 0
        if not args.apply:
            emit(payload, json_output=args.json)
            return 0
        if installed == available:
            payload["action"] = "none"
            emit(payload, json_output=args.json)
            return 0
        with tempfile.TemporaryDirectory(prefix="llmops-update-") as temporary_name:
            temporary = Path(temporary_name)
            archive, checksum_file = release_assets(
                repository=args.repository,
                version=available,
                archive=args.archive,
                checksum_file=args.checksum_file,
                temporary=temporary,
            )
            verify_archive(archive, checksum_file)
            installer = safe_extract(archive, temporary / "extracted")
            command = [
                "/usr/local/bin/bash",
                str(installer),
                "--source",
                str(installer.parents[1]),
                "--prefix",
                str(args.prefix),
                "--public-bin-dir",
                str(args.public_bin_dir),
                "--state-home",
                str(args.state_home),
                "--release-id",
                available,
            ]
            completed = subprocess.run(command, text=True, check=False)
            if completed.returncode != 0:
                raise UpdateError(f"release installer failed with status {completed.returncode}")
        emit(payload, json_output=args.json)
        return 0
    except (OSError, UpdateError) as exc:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"llmops update: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
