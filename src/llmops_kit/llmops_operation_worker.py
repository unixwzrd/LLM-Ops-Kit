"""Detached worker for one persisted LLM-Ops-Kit operation."""

from __future__ import annotations

import contextlib
import io
import sys
import time
from pathlib import Path

from . import entrypoint
from .llmops_operations import load_record, update_record


def main(argv: list[str] | None = None) -> int:
    """Execute the argv stored in an operation record and persist its result."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        return 2
    path = Path(arguments[0])
    record = load_record(path)
    update_record(
        path,
        state="running",
        started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = 2
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = entrypoint.main(list(record.get("argv", [])))
    except BaseException as exc:  # Persist worker failures before exiting.
        print(f"{type(exc).__name__}: {exc}", file=stderr)
        code = 2
    update_record(
        path,
        state="succeeded" if code == 0 else "failed",
        finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        returncode=code,
        output_summary=(stdout.getvalue() or stderr.getvalue()).strip()[-2000:],
        error="" if code == 0 else stderr.getvalue().strip()[-2000:],
        result={"returncode": code, "ok": code == 0},
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
