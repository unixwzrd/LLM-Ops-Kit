#!/usr/bin/env python
"""Write the installer state document without embedding Python in shell code."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def write_state(
    path: Path, *, install_root: str, public_bin: str, state_home: str, release: str
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "install_root": install_root,
                "public_bin_dir": public_bin,
                "state_home": state_home,
                "active_release": release,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state_file", type=Path)
    parser.add_argument("install_root")
    parser.add_argument("public_bin")
    parser.add_argument("state_home_or_release")
    parser.add_argument("release", nargs="?")
    args = parser.parse_args()
    if args.release is None:
        state_home = os.environ.get("LLMOPS_STATE_HOME", str(args.state_file.parent))
        release = args.state_home_or_release
    else:
        state_home = args.state_home_or_release
        release = args.release
    write_state(
        args.state_file,
        install_root=args.install_root,
        public_bin=args.public_bin,
        state_home=state_home,
        release=release,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
