"""Installed LLM-Ops-Kit command router."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from . import __version__, llmops_cli, llmops_update


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
    if arguments == ["--version"]:
        print(__version__)
        return 0
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
