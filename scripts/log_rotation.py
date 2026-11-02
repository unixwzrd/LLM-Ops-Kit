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
        reopen_standard_streams: bool = False,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        self.rotate_seconds = max(0, int(rotate_seconds))
        self.keep = max(0, int(keep))
        self.fsync = bool(fsync)
        self._time_fn = time_fn or time.time
        self.reopen_standard_streams = bool(reopen_standard_streams)
        self._lock = threading.Lock()
        self._next_rotation_at = self._compute_next_rotation_at()

    def _compute_next_rotation_at(self) -> float | None:
        if self.rotate_seconds <= 0:
            return None
        return float(self._time_fn()) + float(self.rotate_seconds)

    def _rotated_path(self, index: int) -> Path:
        return self.path.with_name(f"{self.path.name}.{index}.log")

    def _matching_standard_streams(self) -> dict[int, bool]:
        """Find only standard descriptors already redirected to this log inode."""
        if not self.reopen_standard_streams or not self.path.exists():
            return {}
        target = self.path.stat()
        matching = {}
        for descriptor in (1, 2):
            try:
                current = os.fstat(descriptor)
                if (current.st_dev, current.st_ino) == (target.st_dev, target.st_ino):
                    matching[descriptor] = os.get_inheritable(descriptor)
            except OSError:
                continue
        return matching

    def _reopen_standard_streams(self, descriptors: dict[int, bool]) -> None:
        """Keep opted-in stdout/stderr on the active file after rename rotation."""
        if not descriptors:
            return
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
        try:
            for destination, inheritable in descriptors.items():
                os.dup2(descriptor, destination, inheritable=inheritable)
        finally:
            os.close(descriptor)

    def _rotate_locked(self) -> None:
        descriptors = self._matching_standard_streams()
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
        self._reopen_standard_streams(descriptors)
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
