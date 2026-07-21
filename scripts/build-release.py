#!/usr/bin/env python
"""Build a deterministic runtime-only LLM-Ops-Kit release archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Optional


class ReleaseBuildError(RuntimeError):
    """Raised when a release artifact cannot be built safely."""


ARCHIVE_ROOT_PREFIX = "LLM-Ops-Kit"
PUBLIC_FILES = ("README.md", "LICENSE.md", "CHANGELOG.md")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MAINTAINER_FILES = {
    Path("scripts/bootstrap-install.sh"),
    Path("scripts/build-release.py"),
    Path("scripts/precheck"),
}


def build_wheelhouse(source: Path, destination: Path) -> list[dict[str, object]]:
    """Build the project wheel and download locked dependencies for offline install."""

    uv = shutil.which("uv")
    if uv is None:
        raise ReleaseBuildError("uv is required to build release artifacts")
    destination.mkdir(parents=True, exist_ok=True)
    commands = [
        [uv, "build", "--wheel", "--out-dir", str(destination), str(source)],
        [
            uv,
            "export",
            "--project",
            str(source),
            "--locked",
            "--extra",
            "tui",
            "--no-emit-project",
            "--format",
            "requirements.txt",
            "--output-file",
            str(destination / "requirements-tui.txt"),
        ],
    ]
    for command in commands:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise ReleaseBuildError(completed.stderr.strip() or "wheelhouse build failed")
    (destination / ".gitignore").unlink(missing_ok=True)
    for platform_tag in ("macosx_11_0_arm64", "macosx_10_13_x86_64"):
        download = subprocess.run(
            [
                uv,
                "run",
                "--isolated",
                "--no-project",
                "--with",
                "pip",
                "pip",
                "download",
                "--require-hashes",
                "--only-binary=:all:",
                "--platform",
                platform_tag,
                "--python-version",
                "312",
                "--implementation",
                "cp",
                "--abi",
                "cp312",
                "--destination-directory",
                str(destination),
                "--requirement",
                str(destination / "requirements-tui.txt"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if download.returncode != 0:
            raise ReleaseBuildError(download.stderr.strip() or f"dependency download failed for {platform_tag}")
    records: list[dict[str, object]] = []
    for path in sorted(destination.iterdir()):
        if path.is_file():
            records.append(
                {
                    "path": str(path.relative_to(destination.parent)),
                    "sha256": sha256(path),
                    "mode": path.stat().st_mode & 0o777,
                }
            )
    return records


def run_git(source: Path, *args: str) -> str:
    """Run Git in source and return stripped stdout."""

    completed = subprocess.run(
        ["git", "-C", str(source), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ReleaseBuildError(completed.stderr.strip() or "Git command failed")
    return completed.stdout.strip()


def git_checkout(source: Path) -> bool:
    """Return whether source is inside a Git work tree."""

    completed = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def exported_release_metadata(source: Path) -> tuple[str, int]:
    """Read commit metadata substituted by ``git archive``."""

    try:
        metadata = json.loads((source / "RELEASE.json").read_text(encoding="utf-8"))
        commit = str(metadata["git_commit"])
        timestamp_text = str(metadata["git_timestamp"])
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ReleaseBuildError(
            "non-checkout release source requires exported RELEASE.json metadata"
        ) from exc
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not timestamp_text.isdigit():
        raise ReleaseBuildError(
            "RELEASE.json metadata was not expanded; create source with git archive"
        )
    return commit, int(timestamp_text)


def project_version(source: Path) -> str:
    """Read the package version from the authoritative project metadata."""

    try:
        text = (source / "pyproject.toml").read_text(encoding="utf-8")
    except OSError as exc:
        raise ReleaseBuildError("pyproject.toml is required for release builds") from exc
    match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    if match is None or not VERSION_RE.fullmatch(match.group(1)):
        raise ReleaseBuildError("pyproject.toml contains no valid project version")
    return match.group(1)


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of path."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tracked_runtime_files(source: Path) -> list[Path]:
    """Return tracked files allowed in the public runtime artifact."""

    if git_checkout(source):
        raw = subprocess.run(
            ["git", "-C", str(source), "ls-files", "-z", "--", "scripts", *PUBLIC_FILES],
            capture_output=True,
            check=False,
        )
        if raw.returncode != 0:
            raise ReleaseBuildError("could not enumerate tracked runtime files")
        files = [Path(item.decode()) for item in raw.stdout.split(b"\0") if item]
    else:
        files = [Path(name) for name in PUBLIC_FILES if (source / name).is_file()]
        files.extend(
            path.relative_to(source)
            for path in (source / "scripts").rglob("*")
            if path.is_file()
        )
    selected = [
        path
        for path in files
        if "tests" not in path.parts
        and path not in MAINTAINER_FILES
        and "__pycache__" not in path.parts
        and not path.name.endswith((".pyc", ".pyo", ".DS_Store"))
        and (source / path).is_file()
    ]
    if Path("scripts/install-runtime.sh") not in selected or Path("scripts/llmops") not in selected:
        raise ReleaseBuildError("tracked runtime payload is incomplete")
    return sorted(selected)


def copy_payload(source: Path, payload: Path, files: list[Path]) -> list[dict[str, object]]:
    """Copy selected files and return their release manifest records."""

    records: list[dict[str, object]] = []
    for relative in files:
        source_file = source / relative
        destination = payload / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination)
        records.append(
            {
                "path": str(relative),
                "sha256": sha256(destination),
                "mode": destination.stat().st_mode & 0o777,
            }
        )
    return records


def normalize_tree(root: Path, timestamp: int) -> None:
    """Normalize mtimes so identical inputs produce identical archives."""

    for path in sorted(root.rglob("*")):
        os.utime(path, (timestamp, timestamp), follow_symlinks=False)
    os.utime(root, (timestamp, timestamp), follow_symlinks=False)


def normalized_tar_info(info: tarfile.TarInfo, timestamp: int) -> tarfile.TarInfo:
    """Remove host ownership metadata from a release member."""

    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = timestamp
    return info


def build_release(
    *,
    source: Path,
    output_dir: Path,
    version: Optional[str],
    allow_dirty: bool,
) -> tuple[Path, Path, Path, Path, Path]:
    """Build and return archive, checksum, and manifest paths."""

    source = source.expanduser().resolve()
    if git_checkout(source):
        status = run_git(source, "status", "--porcelain")
        if status and not allow_dirty:
            raise ReleaseBuildError("release build refuses a dirty source tree")
        commit = run_git(source, "rev-parse", "HEAD")
        timestamp = int(run_git(source, "show", "-s", "--format=%ct", "HEAD"))
    else:
        status = ""
        commit, timestamp = exported_release_metadata(source)
    resolved_version = version or project_version(source)
    if not VERSION_RE.fullmatch(resolved_version):
        raise ReleaseBuildError(f"invalid release version: {resolved_version}")
    files = tracked_runtime_files(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"{ARCHIVE_ROOT_PREFIX}-{resolved_version}.tar.xz"
    archive = output_dir / archive_name
    checksum = output_dir / f"{archive_name}.sha256"
    manifest_output = output_dir / f"{ARCHIVE_ROOT_PREFIX}-{resolved_version}.manifest.json"
    bootstrap = output_dir / "install-llmops"
    bootstrap_checksum = output_dir / "install-llmops.sha256"
    for path in (archive, checksum, manifest_output, bootstrap, bootstrap_checksum):
        if path.exists():
            raise ReleaseBuildError(f"release output already exists: {path}")

    with tempfile.TemporaryDirectory(prefix="llmops-release-") as temporary:
        payload = Path(temporary) / f"{ARCHIVE_ROOT_PREFIX}-{resolved_version}"
        payload.mkdir()
        records = copy_payload(source, payload, files)
        records.extend(build_wheelhouse(source, payload / "wheelhouse"))
        manifest = {
            "schema_version": 1,
            "name": "LLM-Ops-Kit",
            "version": resolved_version,
            "git_commit": commit,
            "git_dirty": bool(status),
            "created_at": timestamp,
            "files": records,
        }
        manifest_path = payload / "release-manifest.json"
        manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        manifest_path.write_text(manifest_text, encoding="utf-8")
        release_path = payload / "RELEASE.json"
        release_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "version": resolved_version,
                    "git_commit": commit,
                    "git_dirty": bool(status),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        normalize_tree(payload, timestamp)
        with tarfile.open(archive, "w:xz", format=tarfile.PAX_FORMAT) as bundle:
            bundle.add(
                payload,
                arcname=payload.name,
                recursive=True,
                filter=lambda info: normalized_tar_info(info, timestamp),
            )
        manifest_output.write_text(manifest_text, encoding="utf-8")

    checksum.write_text(f"{sha256(archive)}  {archive.name}\n", encoding="utf-8")
    shutil.copy2(source / "scripts" / "bootstrap-install.sh", bootstrap)
    bootstrap.chmod(0o755)
    bootstrap_checksum.write_text(f"{sha256(bootstrap)}  {bootstrap.name}\n", encoding="utf-8")
    return archive, checksum, manifest_output, bootstrap, bootstrap_checksum


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description="Build a runtime-only LLM-Ops-Kit release")
    parser.add_argument("--source", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--version")
    parser.add_argument("--allow-dirty", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Run the release builder."""

    args = build_parser().parse_args(argv)
    try:
        outputs = build_release(
            source=Path(args.source),
            output_dir=Path(args.output_dir).expanduser(),
            version=args.version,
            allow_dirty=args.allow_dirty,
        )
    except (OSError, ReleaseBuildError, ValueError) as exc:
        print(f"build-release: {exc}", file=os.sys.stderr)
        return 2
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
