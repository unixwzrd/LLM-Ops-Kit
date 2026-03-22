#!/usr/bin/env python
"""Simple time-based log rotation with numbered suffixes."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path


class RotatingLogWriter:
    def __init__(
        self,
        path: Path | str,
        *,
        rotate_seconds: int = 86400,
        keep: int = 5,
        fsync: bool = True,
        time_fn: callable | None = None,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        self.rotate_seconds = max(0, int(rotate_seconds))
        self.keep = max(0, int(keep))
        self.fsync = bool(fsync)
        self._time_fn = time_fn or time.time
        self._lock = threading.Lock()
        self._next_rotation_at = self._compute_next_rotation_at()

    def _compute_next_rotation_at(self) -> float | None:
        if self.rotate_seconds <= 0:
            return None
        return float(self._time_fn()) + float(self.rotate_seconds)

    def _rotated_path(self, index: int) -> Path:
        return self.path.with_name(f"{self.path.name}.{index}.log")

    def _rotate_locked(self) -> None:
        if self.keep > 0:
            oldest = self._rotated_path(self.keep - 1)
            if oldest.exists():
                oldest.unlink()
            for index in range(self.keep - 2, -1, -1):
                current = self._rotated_path(index)
                if current.exists():
                    current.rename(self._rotated_path(index + 1))
            if self.path.exists():
                self.path.rename(self._rotated_path(0))
        elif self.path.exists():
            self.path.unlink()
        self._next_rotation_at = self._compute_next_rotation_at()

    def _maybe_rotate_locked(self) -> None:
        if self.rotate_seconds <= 0:
            return
        deadline = self._next_rotation_at
        now = float(self._time_fn())
        if deadline is None:
            self._next_rotation_at = now + float(self.rotate_seconds)
            return
        if now >= deadline:
            self._rotate_locked()

    def write(self, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._maybe_rotate_locked()
            with self.path.open("a", encoding="utf-8", buffering=1) as f:
                f.write(text)
                f.flush()
                if self.fsync:
                    os.fsync(f.fileno())
