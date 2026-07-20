#!/usr/bin/env python
"""Release-source documentation and privacy checks."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOCAL_LINK = re.compile(r"\[[^]]+\]\((?!https?://|mailto:|#)([^)#]+)(?:#[^)]*)?\)")
PRIVATE_PATTERN = re.compile(r"/Users/|/Volumes/|\bmiafour\b|\b10\.0\.0\.\d+\b")
EMBEDDED_PYTHON = re.compile(r"\bpython(?:3)?\b[^\n]*<<")


def tracked_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        return [ROOT / item.decode() for item in completed.stdout.split(b"\0") if item and (ROOT / item.decode()).exists()]
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
    ]


class ReleaseHygieneTests(unittest.TestCase):
    def test_public_markdown_links_resolve(self) -> None:
        missing: list[str] = []
        for path in tracked_files():
            if path.suffix.lower() != ".md":
                continue
            for target in LOCAL_LINK.findall(path.read_text(encoding="utf-8")):
                clean = target.strip("<>").replace("%20", " ")
                if not (path.parent / clean).resolve().exists():
                    missing.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual(missing, [])

    def test_tracked_release_has_no_private_machine_defaults(self) -> None:
        findings: list[str] = []
        for path in tracked_files():
            if path.resolve() == Path(__file__).resolve():
                continue
            if path.suffix.lower() not in {".py", ".sh", ".md", ".json", ""}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if PRIVATE_PATTERN.search(text):
                findings.append(str(path.relative_to(ROOT)))
        self.assertEqual(findings, [])

    def test_obsolete_runtime_paths_are_not_tracked(self) -> None:
        names = {str(path.relative_to(ROOT)) for path in tracked_files()}
        obsolete = [name for name in names if name == "bin" or name.startswith(("bin/", "deploy/", "docs/internal/"))]
        self.assertEqual(obsolete, [])

    def test_shell_scripts_do_not_embed_python_heredocs(self) -> None:
        findings: list[str] = []
        for path in tracked_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.suffix != ".sh" and not text.startswith("#!/usr/bin/env bash"):
                continue
            if EMBEDDED_PYTHON.search(text):
                findings.append(str(path.relative_to(ROOT)))
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
