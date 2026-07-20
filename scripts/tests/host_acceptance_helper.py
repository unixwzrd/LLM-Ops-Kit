#!/usr/bin/env python
"""Structured file operations used by host_install_acceptance.sh."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def configure_inventory(path: Path, *, install_root: str, public_bin: str) -> None:
    inventory = json.loads(path.read_text(encoding="utf-8"))
    for host in inventory["hosts"]:
        host["install_root"] = install_root
        host["public_bin_dir"] = public_bin
        host["transport"] = "local"
    path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("configure-inventory")
    inventory.add_argument("path", type=Path)
    inventory.add_argument("install_root")
    inventory.add_argument("public_bin")

    digest = subparsers.add_parser("tree-digest")
    digest.add_argument("root", type=Path)
    digest.add_argument("output", type=Path)

    args = parser.parse_args()
    if args.command == "configure-inventory":
        configure_inventory(args.path, install_root=args.install_root, public_bin=args.public_bin)
    else:
        args.output.write_text(tree_digest(args.root) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
