#!/usr/bin/env python
"""Plan and apply fail-closed retention for installer-owned toolkit releases."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from .llmops_executor import ExecutionError, operation_lock
except ImportError:  # Direct source execution.
    from llmops_executor import ExecutionError, operation_lock


class MaintenanceError(RuntimeError):
    """Raised when release retention cannot be evaluated safely."""


@dataclass(frozen=True)
class LinkSnapshot:
    """Identity of an immutable-release selector."""

    exists: bool
    inode: Optional[int]
    target: Optional[str]


@dataclass(frozen=True)
class NodeSnapshot:
    """Filesystem identity pinned by a retention plan."""

    device: int
    inode: int


INSPECTION_TIMEOUT = 10
MAX_REFERENCE_FILES = 4096
MAX_REFERENCE_FILE_BYTES = 1024 * 1024
CONFIG_SUFFIXES = {".env", ".json", ".plist", ".toml", ".yaml", ".yml"}
STATE_SUFFIXES = {".json", ".pid", ".state"}


def _node_snapshot(path: Path) -> NodeSnapshot:
    stat = path.stat(follow_symlinks=False)
    return NodeSnapshot(stat.st_dev, stat.st_ino)


def _link_snapshot(path: Path) -> LinkSnapshot:
    if os.path.lexists(path) and not path.is_symlink():
        raise MaintenanceError(f"release selector is not a symlink: {path}")
    if not path.is_symlink():
        return LinkSnapshot(False, None, None)
    stat = path.lstat()
    return LinkSnapshot(True, stat.st_ino, os.readlink(path))


def _load_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaintenanceError(f"invalid {label}: {path}") from exc
    if not isinstance(value, dict):
        raise MaintenanceError(f"invalid {label}: {path}")
    return value


def _require_owned_safe(path: Path, label: str, *, directory: bool = False) -> os.stat_result:
    try:
        value = path.lstat()
    except OSError as exc:
        raise MaintenanceError(f"could not inspect {label}: {path}") from exc
    expected = stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode)
    if not expected or stat.S_ISLNK(value.st_mode) or value.st_uid != os.getuid():
        raise MaintenanceError(f"unsafe {label}: {path}")
    if value.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise MaintenanceError(f"{label} is group/world writable: {path}")
    return value


def owned_install_root(metadata_path: Path) -> Path:
    """Return the canonical installer-owned root from install metadata."""

    _require_owned_safe(metadata_path, "install metadata")
    metadata = _load_object(metadata_path, "install metadata")
    if (
        metadata.get("schema_version") != 1
        or not isinstance(metadata.get("install_root"), str)
        or not isinstance(metadata.get("public_bin_dir"), str)
        or not isinstance(metadata.get("active_release"), str)
        or not isinstance(metadata.get("state_home"), str)
    ):
        raise MaintenanceError(f"incomplete install metadata: {metadata_path}")
    configured = Path(str(metadata["install_root"])).expanduser()
    if configured.is_symlink() or not configured.is_dir():
        raise MaintenanceError(f"install root must be a real directory: {configured}")
    canonical = configured.resolve(strict=True)
    if metadata_path.resolve(strict=True) != canonical / "install.json":
        raise MaintenanceError("install metadata is not inside its canonical install root")
    root_stat = canonical.stat()
    if root_stat.st_uid != os.getuid():
        raise MaintenanceError(f"install root is not owned by uid {os.getuid()}: {canonical}")
    if root_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise MaintenanceError(f"install root is group/world writable: {canonical}")
    return canonical


def _selector_target(root: Path, name: str) -> tuple[LinkSnapshot, Optional[Path]]:
    selector = root / name
    snapshot = _link_snapshot(selector)
    if not snapshot.exists:
        return snapshot, None
    target = (selector.parent / str(snapshot.target)).resolve(strict=False)
    releases = root / "releases"
    if target.parent != releases or not target.is_dir():
        raise MaintenanceError(f"{name} does not select a complete owned release")
    return snapshot, target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _release_metadata(path: Path) -> Optional[str]:
    """Return a validated release version, or None for an unmanaged entry."""

    release_file = path / "RELEASE.json"
    manifest_file = path / "release-manifest.json"
    if not release_file.is_file() or not manifest_file.is_file():
        return None
    _require_owned_safe(release_file, "release metadata")
    _require_owned_safe(manifest_file, "release manifest")
    try:
        release = _load_object(release_file, "release metadata")
        manifest = _load_object(manifest_file, "release manifest")
    except MaintenanceError:
        return None
    version = release.get("version")
    if (
        release.get("schema_version") != 1
        or manifest.get("schema_version") != 1
        or manifest.get("name") != "LLM-Ops-Kit"
        or not isinstance(version, str)
        or manifest.get("version") != version
        or path.name != version
        or not isinstance(manifest.get("files"), list)
        or not manifest["files"]
    ):
        return None
    records = {
        item.get("path"): item
        for item in manifest["files"]
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    for relative in ("scripts/llmops", "scripts/install-runtime.sh"):
        installed = path / relative
        record = records.get(relative)
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("sha256"), str)
            or not isinstance(record.get("mode"), int)
            or installed.is_symlink()
            or not installed.is_file()
            or not os.access(installed, os.X_OK)
            or installed.stat().st_mode & 0o777 != record["mode"]
        ):
            return None
        try:
            if _sha256(installed) != record["sha256"]:
                return None
        except OSError:
            return None
    app = path / "app/bin/llmops"
    scripts = path / "scripts"
    if app.is_symlink() or not app.is_file() or not os.access(app, os.X_OK):
        return None
    if scripts.is_symlink() or not scripts.is_dir():
        return None
    return version


def _validate_tree(path: Path, install_root: Path, root_device: int) -> None:
    if (
        path.is_symlink()
        or not path.is_dir()
        or os.path.ismount(path)
        or path.stat().st_uid != os.getuid()
        or path.stat().st_dev != root_device
        or path.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise MaintenanceError(f"unsafe release directory: {path}")
    def walk_error(error: OSError) -> None:
        raise MaintenanceError(f"could not inspect release tree: {error.filename or path}") from error

    for directory, names, files in os.walk(path, followlinks=False, onerror=walk_error):
        current = Path(directory)
        current_stat = current.stat()
        if current_stat.st_dev != root_device or (current != path and os.path.ismount(current)):
            raise MaintenanceError(f"nested mount in release: {current}")
        if current_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise MaintenanceError(f"release directory is group/world writable: {current}")
        for name in [*names, *files]:
            child = current / name
            child_stat = child.lstat()
            if child_stat.st_uid != os.getuid():
                raise MaintenanceError(f"release entry is not owned by uid {os.getuid()}: {child}")
            if child_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise MaintenanceError(f"release entry is group/world writable: {child}")
            if child.is_symlink():
                try:
                    child.resolve(strict=False).relative_to(path)
                except ValueError as exc:
                    try:
                        relative = child.relative_to(path)
                        child.resolve(strict=True).relative_to(install_root / "python")
                    except (OSError, ValueError) as managed_exc:
                        raise MaintenanceError(f"symlink escapes release: {child}") from managed_exc
                    if relative.parent != Path("app/bin") or not relative.name.startswith("python"):
                        raise MaintenanceError(f"unexpected managed-runtime symlink: {child}") from exc


def _bounded_files(
    root: Path,
    *,
    launch_agents: bool = False,
    suffixes: set[str] = CONFIG_SUFFIXES,
) -> list[Path]:
    if not os.path.lexists(root):
        return []
    if root.is_symlink() or not root.is_dir() or root.stat().st_uid != os.getuid():
        raise MaintenanceError(f"unsafe reference source: {root}")
    if root.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise MaintenanceError(f"reference source is group/world writable: {root}")
    files: list[Path] = []
    try:
        if launch_agents:
            candidates = list(root.iterdir())
        else:
            candidates = []

            def walk_error(error: OSError) -> None:
                raise MaintenanceError(
                    f"could not inspect reference source: {error.filename or root}"
                ) from error

            for directory, names, filenames in os.walk(root, followlinks=False, onerror=walk_error):
                current = Path(directory)
                for name in names:
                    if (current / name).is_symlink():
                        raise MaintenanceError(
                            f"unexpected symlink in reference source: {current / name}"
                        )
                candidates.extend(current / name for name in filenames)
        for item in candidates:
            if item.is_symlink():
                raise MaintenanceError(f"unexpected symlink in reference source: {item}")
            if not item.is_file() or (launch_agents and item.suffix != ".plist"):
                continue
            if not launch_agents and item.suffix.lower() not in suffixes:
                continue
            item_stat = item.stat()
            if item_stat.st_uid != os.getuid():
                raise MaintenanceError(f"unowned reference source: {item}")
            if item_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise MaintenanceError(f"reference source is group/world writable: {item}")
            if item_stat.st_size > MAX_REFERENCE_FILE_BYTES:
                raise MaintenanceError(f"reference source exceeds size limit: {item}")
            files.append(item)
            if len(files) > MAX_REFERENCE_FILES:
                raise MaintenanceError(f"reference source exceeds file limit: {root}")
    except OSError as exc:
        raise MaintenanceError(f"could not inspect reference source: {root}") from exc
    return files


def _reference_tokens(path: Path) -> set[str]:
    tokens = {str(path), str(path.resolve(strict=True))}
    install_root = path.parent.parent
    for name in ("current", "previous"):
        selector = install_root / name
        if selector.is_symlink() and selector.resolve(strict=False) == path:
            tokens.add(str(selector))
    return tokens


def _static_references(
    path: Path,
    roots: tuple[Path, ...],
    launch_agents_dir: Path,
    state_home: Path,
) -> list[str]:
    tokens = _reference_tokens(path)
    references: list[str] = []
    for root in roots:
        for source in _bounded_files(root):
            try:
                content = source.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise MaintenanceError(f"could not read reference source: {source}") from exc
            if any(token in content for token in tokens):
                references.append("configuration")
                break
    for source in _bounded_files(launch_agents_dir, launch_agents=True):
        try:
            content = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise MaintenanceError(f"could not read launchd plist: {source}") from exc
        if any(token in content for token in tokens):
            references.append("launchd-plist")
            break
    for source in _bounded_files(state_home / "run", suffixes=STATE_SUFFIXES):
        try:
            content = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise MaintenanceError(f"could not read runtime state: {source}") from exc
        if any(token in content for token in tokens):
            references.append("runtime-state")
            break
    return sorted(set(references))


def _references(
    path: Path,
    *,
    config_roots: tuple[Path, ...],
    launch_agents_dir: Path,
    state_home: Path,
) -> list[dict[str, object]]:
    """Return process and open-file references, failing closed on inspection errors."""

    tokens = {token + "/" for token in _reference_tokens(path)}
    try:
        ps = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            check=False,
            timeout=INSPECTION_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise MaintenanceError("process inspection timed out") from exc
    if ps.returncode != 0:
        raise MaintenanceError("could not inspect processes with ps")
    references: list[dict[str, object]] = []
    for line in ps.stdout.splitlines():
        if not any(token in line for token in tokens):
            continue
        pid = line.strip().split(maxsplit=1)[0]
        if pid.isdigit():
            references.append({"category": "process", "pid": int(pid)})
    try:
        lsof = subprocess.run(
            ["lsof", "-Fn", "+D", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=INSPECTION_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise MaintenanceError("lsof is required for release retention") from exc
    except subprocess.TimeoutExpired as exc:
        raise MaintenanceError("open-file inspection timed out") from exc
    if lsof.returncode not in {0, 1} or (lsof.returncode == 1 and lsof.stderr.strip()):
        raise MaintenanceError(f"could not inspect open files with lsof: {path}")
    if lsof.returncode == 0:
        pids = [line[1:] for line in lsof.stdout.splitlines() if line.startswith("p")]
        references.extend({"category": "open-files", "pid": int(pid)} for pid in pids if pid.isdigit())
    references.extend(
        {"category": category}
        for category in _static_references(
            path, config_roots, launch_agents_dir, state_home
        )
    )
    return sorted(
        {json.dumps(item, sort_keys=True): item for item in references}.values(),
        key=lambda item: (str(item["category"]), int(item.get("pid", 0))),
    )


def _reference_roots(root: Path, configured: tuple[Path, ...]) -> tuple[Path, ...]:
    roots: list[Path] = []
    current_config = root / "current-config"
    if os.path.lexists(current_config):
        if not current_config.is_symlink():
            raise MaintenanceError(f"current-config is not a symlink: {current_config}")
        target = current_config.resolve(strict=True)
        try:
            target.relative_to(root / "config-revisions")
        except ValueError as exc:
            raise MaintenanceError("current-config escapes owned configuration revisions") from exc
        roots.append(target)
    for candidate in configured:
        expanded = candidate.expanduser()
        if not expanded.exists():
            continue
        resolved = expanded.resolve(strict=True)
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _validate_releases_root(releases: Path) -> NodeSnapshot:
    releases_stat = releases.stat() if releases.exists() else None
    if (
        releases.is_symlink()
        or not releases.is_dir()
        or os.path.ismount(releases)
        or releases_stat is None
        or releases_stat.st_uid != os.getuid()
        or releases_stat.st_dev != releases.parent.stat().st_dev
    ):
        raise MaintenanceError(f"unsafe releases directory: {releases}")
    if releases_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise MaintenanceError(f"releases directory is group/world writable: {releases}")
    return _node_snapshot(releases)


@contextmanager
def install_mutation_lock(root: Path):
    """Use the shell-compatible atomic lock held by every installer mutation."""

    lock = root / "update.lock"
    token = f"{os.getpid()}-{uuid.uuid4().hex}"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise MaintenanceError(f"another install mutation holds {lock}") from exc
    except OSError as exc:
        raise MaintenanceError(f"could not acquire install mutation lock: {lock}") from exc
    owner = lock / "owner"
    lock_snapshot = _node_snapshot(lock)
    try:
        _require_owned_safe(lock, "install mutation lock", directory=True)
        owner.write_text(token + "\n", encoding="utf-8")
        owner.chmod(0o600)
        yield
    finally:
        try:
            if _node_snapshot(lock) == lock_snapshot and owner.read_text(encoding="utf-8").strip() == token:
                owner.unlink()
                lock.rmdir()
        except OSError:
            pass


def _inventory(
    root: Path,
    *,
    drop_previous: bool,
    config_roots: tuple[Path, ...],
    launch_agents_dir: Path,
    state_home: Path,
) -> tuple[list[dict[str, object]], LinkSnapshot, LinkSnapshot, NodeSnapshot]:
    releases = root / "releases"
    releases_snapshot = _validate_releases_root(releases)
    current_snapshot, current = _selector_target(root, "current")
    previous_snapshot, previous = _selector_target(root, "previous")
    if current is None:
        raise MaintenanceError("current release selector is required")
    metadata = _load_object(root / "install.json", "install metadata")
    active_release = Path(str(metadata["active_release"])).expanduser().resolve(strict=False)
    if active_release != current:
        raise MaintenanceError("current selector does not match installer metadata")
    references_roots = _reference_roots(root, config_roots)
    rows: list[dict[str, object]] = []
    for path in sorted(releases.iterdir(), key=lambda item: item.name):
        row: dict[str, object] = {"release": path.name, "path": str(path), "action": "keep"}
        if path.is_symlink() or not path.is_dir():
            row.update(action="blocked", reason="unexpected release entry")
        else:
            try:
                release_version = _release_metadata(path)
            except MaintenanceError as exc:
                row.update(action="blocked", reason=str(exc))
                rows.append(row)
                continue
            if release_version is None:
                row.update(action="skip", reason="unmanaged or incomplete release retained")
            elif path == current:
                row["reason"] = "current"
            elif path == previous and not drop_previous:
                row["reason"] = "previous"
            else:
                try:
                    _validate_tree(path, root, releases.stat().st_dev)
                    release_snapshot = _node_snapshot(path)
                    references = _references(
                        path,
                        config_roots=references_roots,
                        launch_agents_dir=launch_agents_dir,
                        state_home=state_home,
                    )
                except MaintenanceError as exc:
                    row.update(action="blocked", reason=str(exc))
                else:
                    if references:
                        row.update(action="skip", reason="active references", references=references)
                    else:
                        row.update(action="remove", reason="retention candidate")
                        row["release_device"] = release_snapshot.device
                        row["release_inode"] = release_snapshot.inode
                        row["release_manifest_sha256"] = _sha256(path / "release-manifest.json")
        rows.append(row)
    return rows, current_snapshot, previous_snapshot, releases_snapshot


def maintain_releases(
    metadata_path: Path,
    *,
    apply: bool = False,
    drop_previous: bool = False,
    config_roots: tuple[Path, ...] = (),
    launch_agents_dir: Optional[Path] = None,
    plan_digest: Optional[str] = None,
) -> dict[str, object]:
    """Plan or apply immutable toolkit release retention."""

    if drop_previous:
        raise MaintenanceError("--drop-previous is not supported; previous remains protected")
    root = owned_install_root(metadata_path)
    metadata = _load_object(metadata_path, "install metadata")
    configured_state_home = Path(str(metadata["state_home"])).expanduser()
    if configured_state_home.is_symlink():
        raise MaintenanceError(f"canonical state root is a symlink: {configured_state_home}")
    state_home = configured_state_home.resolve(strict=True)
    state_stat = state_home.stat()
    if state_stat.st_uid != os.getuid() or state_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise MaintenanceError(f"unsafe canonical state root: {state_home}")
    run_root = state_home / "run"
    run_stat = _require_owned_safe(run_root, "runtime state root", directory=True)
    if run_stat.st_dev != state_stat.st_dev:
        raise MaintenanceError(f"runtime state root is on another device: {run_root}")
    lifecycle_lock_path = run_root / "orchestrator.lock"
    if os.path.lexists(lifecycle_lock_path):
        _require_owned_safe(lifecycle_lock_path, "lifecycle lock")
    launch_agents = launch_agents_dir or Path.home() / "Library/LaunchAgents"

    def evaluate_and_apply() -> dict[str, object]:
        rows, current_snapshot, previous_snapshot, releases_snapshot = _inventory(
            root,
            drop_previous=drop_previous,
            config_roots=config_roots,
            launch_agents_dir=launch_agents,
            state_home=state_home,
        )
        expected_previous = previous_snapshot
        removed: list[str] = []
        identity = {
            "current": current_snapshot.__dict__,
            "previous": previous_snapshot.__dict__,
            "releases": releases_snapshot.__dict__,
            "targets": [
                {
                    key: row[key]
                    for key in (
                        "release",
                        "release_device",
                        "release_inode",
                        "release_manifest_sha256",
                    )
                }
                for row in rows
                if row["action"] == "remove"
            ],
        }
        computed_digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if apply:
            if not plan_digest or plan_digest != computed_digest:
                raise MaintenanceError("--apply requires the matching reviewed --plan-digest")
            blocked = [row for row in rows if row["action"] == "blocked"]
            if blocked:
                names = ", ".join(str(row["release"]) for row in blocked)
                raise MaintenanceError(f"release inventory is not clean: {names}")
            for row in rows:
                if row["action"] != "remove":
                    continue
                current_now = _link_snapshot(root / "current")
                previous_now = _link_snapshot(root / "previous")
                if current_now != current_snapshot or previous_now != expected_previous:
                    raise MaintenanceError("current or previous release changed during maintenance")
                if owned_install_root(metadata_path) != root:
                    raise MaintenanceError("canonical install root changed during maintenance")
                if _validate_releases_root(root / "releases") != releases_snapshot:
                    raise MaintenanceError("releases directory changed during maintenance")
                path = Path(str(row["path"]))
                expected_release = NodeSnapshot(
                    int(row["release_device"]), int(row["release_inode"])
                )
                if _node_snapshot(path) != expected_release:
                    raise MaintenanceError(f"release identity drifted before removal: {path}")
                if _release_metadata(path) != row["release"]:
                    raise MaintenanceError(f"release metadata drifted before removal: {path}")
                _validate_tree(path, root, (root / "releases").stat().st_dev)
                references = _references(
                    path,
                    config_roots=_reference_roots(root, config_roots),
                    launch_agents_dir=launch_agents,
                    state_home=state_home,
                )
                if references:
                    row.update(action="skip", reason="active references", references=references)
                    continue
                if _link_snapshot(root / "current") != current_snapshot:
                    raise MaintenanceError("current release changed after final reference check")
                if _link_snapshot(root / "previous") != expected_previous:
                    raise MaintenanceError("previous release changed after final reference check")
                if _validate_releases_root(root / "releases") != releases_snapshot:
                    raise MaintenanceError("releases directory changed after final reference check")
                if _node_snapshot(path) != expected_release:
                    raise MaintenanceError(f"release identity changed after final reference check: {path}")
                shutil.rmtree(path)
                row["action"] = "removed"
                removed.append(str(row["release"]))
        return {
            "ok": True,
            "mode": "apply" if apply else "plan",
            "install_root": str(root),
            "protected": ["current"] + ([] if drop_previous else ["previous"]),
            "releases_device": releases_snapshot.device,
            "releases_inode": releases_snapshot.inode,
            "plan_digest": computed_digest,
            "releases": rows,
            "removed": removed,
        }

    if not apply:
        return evaluate_and_apply()
    try:
        with install_mutation_lock(root):
            with operation_lock(lifecycle_lock_path):
                return evaluate_and_apply()
    except ExecutionError as exc:
        raise MaintenanceError(str(exc)) from exc


def render_text(payload: dict[str, object]) -> str:
    """Render a concise CLI retention report."""

    lines = [f"mode={payload['mode']}", f"install_root={payload['install_root']}"]
    for row in payload["releases"]:
        assert isinstance(row, dict)
        lines.append(f"{row['action']}: {row['release']} ({row.get('reason', '')})")
    return "\n".join(lines)
