"""Installed LLM-Ops-Kit command router."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from . import llmops_cli, llmops_update


def main(argv: Optional[list[str]] = None) -> int:
    """Dispatch the public command surface without shell-profile dependencies."""

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
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help", "help"}:
        llmops_cli.print_public_help()
        return 0
    command = arguments[0]
    if command == "rollback":
        return llmops_update.main(["--rollback", *arguments[1:]])
    if command == "update":
        return llmops_update.main(arguments[1:])
    if command == "tui":
        from .llmops_tui import main as tui_main

        return tui_main(arguments[1:])
    return llmops_cli.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
