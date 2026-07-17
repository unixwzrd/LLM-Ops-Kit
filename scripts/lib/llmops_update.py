#!/usr/bin/env python3
"""Repository-free release discovery and atomic local runtime updates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
        bundle.extractall(destination)
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
    print(f"current: {payload.get('current') or 'not installed'}")
    print(f"available: {payload['available']}")
    print(f"action: {payload['action']}")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description="Check, plan, or apply a verified LLM-Ops-Kit release")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="Report the current and available release (default)")
    action.add_argument("--plan", action="store_true", help="Describe the update without downloading or changing files")
    action.add_argument("--apply", action="store_true", help="Download, verify, and atomically install the release")
    parser.add_argument("--version", help="Release tag; defaults to the latest GitHub release")
    parser.add_argument("--repository", default=os.environ.get("LLMOPS_GITHUB_REPOSITORY", "unixwzrd/LLM-Ops-Kit"))
    parser.add_argument("--archive", type=Path, help="Use a local release artifact")
    parser.add_argument("--checksum-file", type=Path, help="SHA-256 file for --archive")
    parser.add_argument("--prefix", type=Path, default=Path(os.environ.get("LLMOPS_HOME", "~/.local/llm-ops")).expanduser())
    parser.add_argument("--public-bin-dir", type=Path, default=Path(os.environ.get("LLMOPS_PUBLIC_BIN_DIR", "~/.local/bin")).expanduser())
    parser.add_argument("--state-home", type=Path, default=Path(os.environ.get("LLMOPS_STATE_HOME", "~/.local/state/llm-ops")).expanduser())
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Run release discovery or a verified local update."""

    args = build_parser().parse_args(argv)
    try:
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
