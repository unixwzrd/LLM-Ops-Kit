"""Installed LLM-Ops-Kit command router."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Optional

from . import __version__, llmops_cli, llmops_update


def _auto_update_target(config_home: Path) -> tuple[str, str]:
    """Return the manifest-approved toolkit version and release repository."""

    try:
        document = json.loads((config_home / "products.json").read_text(encoding="utf-8"))
        product = document["products"]["llm-ops-kit"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return "", ""
    if product.get("auto_update") is not True:
        return "", ""
    target = str(product.get("latest_version", ""))
    repository = str(
        product.get("release_repository", "unixwzrd/LLM-Ops-Kit")
    )
    if not llmops_update.VERSION_RE.fullmatch(target):
        return "", ""
    if not llmops_update.REPOSITORY_RE.fullmatch(repository):
        return "", ""
    return target, repository


def _auto_update(
    install_base: Path,
    config_home: Path,
    arguments: list[str],
) -> Optional[Path]:
    """Apply one approved local runtime update before normal dispatch."""

    if os.environ.get("LLMOPS_AUTO_UPDATE_ACTIVE") == "1":
        return None
    if arguments and arguments[0] in {"update", "rollback"}:
        return None
    target, repository = _auto_update_target(config_home)
    if not target or llmops_update.current_version(install_base) == target:
        return None
    public_bin = Path(
        os.environ.get("LLMOPS_PUBLIC_BIN_DIR", str(Path.home() / ".local/bin"))
    ).expanduser()
    state_home = Path(
        os.environ.get(
            "LLMOPS_STATE_HOME", str(Path.home() / ".local/state/llm-ops")
        )
    ).expanduser()
    previous = os.environ.get("LLMOPS_AUTO_UPDATE_ACTIVE")
    os.environ["LLMOPS_AUTO_UPDATE_ACTIVE"] = "1"
    stdout = StringIO()
    stderr = StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = llmops_update.main(
                [
                    "--apply",
                    "--version",
                    target,
                    "--repository",
                    repository,
                    "--prefix",
                    str(install_base),
                    "--public-bin-dir",
                    str(public_bin),
                    "--state-home",
                    str(state_home),
                ]
            )
    finally:
        if previous is None:
            os.environ.pop("LLMOPS_AUTO_UPDATE_ACTIVE", None)
        else:
            os.environ["LLMOPS_AUTO_UPDATE_ACTIVE"] = previous
    if result != 0:
        detail = stderr.getvalue().strip() or stdout.getvalue().strip()
        print(
            f"llmops: automatic update to {target} failed; continuing with the current runtime"
            + (f": {detail}" if detail else ""),
            file=sys.stderr,
        )
        return None
    updated = install_base / "current" / "app" / "bin" / "llmops"
    return updated if updated.is_file() else None


def tui_authority_command(config_home: Path, arguments: list[str]) -> Optional[list[str]]:
    """Return an SSH command that runs the TUI on its designated authority."""

    if os.environ.get("LLMOPS_TUI_AUTHORITY_ROUTED") == "1":
        return None
    try:
        catalog = json.loads((config_home / "catalog.json").read_text(encoding="utf-8"))
        resolved = json.loads((config_home / "resolved.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    current_host = str(resolved.get("host", ""))
    authority_host = str(catalog.get("authority_host", ""))
    trusted = set(catalog.get("trusted_control_hosts", []))
    if not authority_host or authority_host == current_host:
        return None
    if current_host not in trusted or authority_host not in trusted:
        raise RuntimeError("TUI authority routing requires trusted current and authority hosts")
    hosts = {
        str(item.get("name", "")): item
        for item in catalog.get("hosts", [])
        if isinstance(item, dict) and item.get("name")
    }
    target = hosts.get(authority_host)
    if target is None:
        raise RuntimeError(f"TUI authority host is absent from the catalog: {authority_host}")
    operation = ["tui", *arguments]
    command = llmops_cli._host_command(target, operation, json_output=False)
    command.insert(1, "-t")
    command.insert(1, "-q")
    command[-1] = f"LLMOPS_TUI_AUTHORITY_ROUTED=1 {command[-1]}"
    return command


def main(argv: Optional[list[str]] = None) -> int:
    """Dispatch the public command surface without shell-profile dependencies."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    release_root = Path(sys.executable).absolute().parents[2]
    install_base = release_root.parent.parent
    install_state = install_base / "install.json"
    if install_state.is_file():
        try:
            layout = json.loads(install_state.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            layout = {}
        if isinstance(layout, dict):
            os.environ.setdefault("LLMOPS_HOME", str(layout.get("install_root", install_base)))
            if layout.get("public_bin_dir"):
                os.environ.setdefault("LLMOPS_PUBLIC_BIN_DIR", str(layout["public_bin_dir"]))
    managed_config = install_base / "current-config"
    deployed_config = managed_config if managed_config.is_dir() else release_root / "config"
    updated = _auto_update(install_base, deployed_config, arguments)
    if updated is not None:
        environment = os.environ.copy()
        environment["LLMOPS_AUTO_UPDATE_ACTIVE"] = "1"
        os.execve(updated, [str(updated), *arguments], environment)
    if arguments == ["--version"]:
        print(__version__)
        return 0
    if "LLMOPS_CONFIG_HOME" not in os.environ and (deployed_config / "config.json").is_file():
        os.environ["LLMOPS_CONFIG_HOME"] = str(deployed_config)
    if not arguments or arguments[0] in {"-h", "--help", "help"}:
        llmops_cli.print_public_help()
        return 0
    command = arguments[0]
    if command == "rollback":
        return llmops_update.main(["--rollback", *arguments[1:]])
    if command == "update":
        return llmops_update.main(arguments[1:])
    if command == "tui":
        authority_command = tui_authority_command(deployed_config, arguments[1:])
        if authority_command is not None:
            return subprocess.run(authority_command, check=False).returncode
        from .llmops_tui import main as tui_main

        return tui_main(arguments[1:])
    return llmops_cli.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
