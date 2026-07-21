#!/usr/bin/env python
"""Persistent desired lifecycle state for managed components."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


SCHEMA_VERSION = 1
VALID_STATES = {"running", "stopped", "disabled"}


class LifecycleStateError(RuntimeError):
    """Raised when desired lifecycle state is invalid or unreadable."""


class LifecycleStateStore:
    """Read and transactionally replace component desired lifecycle state."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LifecycleStateError(f"invalid lifecycle state {self.path}: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
            raise LifecycleStateError(f"invalid lifecycle state schema: {self.path}")
        components = payload.get("components")
        if not isinstance(components, dict):
            raise LifecycleStateError(f"invalid lifecycle component map: {self.path}")
        states = {str(key): str(value) for key, value in components.items()}
        invalid = sorted({value for value in states.values() if value not in VALID_STATES})
        if invalid:
            raise LifecycleStateError(
                f"invalid desired lifecycle value in {self.path}: {', '.join(invalid)}"
            )
        return states

    def save(self, states: dict[str, str]) -> None:
        invalid = sorted({value for value in states.values() if value not in VALID_STATES})
        if invalid:
            raise LifecycleStateError(f"invalid desired lifecycle value: {', '.join(invalid)}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "components": dict(sorted(states.items())),
        }
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            dir=self.path.parent,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
