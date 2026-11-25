"""Opt-in, owner-private, bounded capture of generated TTS response audio."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class AudioCapture:
    """Save responses and optionally target text, never headers or references.

    A filesystem lock and directory accounting enforce limits across threads,
    processes and restarts. Existing captures are never overwritten or rotated.
    """

    def __init__(self, config: dict[str, object]) -> None:
        allowed = {"enabled", "directory", "max_responses", "max_bytes", "pcm_sample_rate", "voice", "include_text"}
        if set(config) - allowed or config.get("enabled") is not True:
            raise ValueError("invalid enabled audio capture configuration")
        self.max_responses = self._integer(config.get("max_responses", 10))
        self.max_bytes = self._integer(config.get("max_bytes", 25 * 1024 * 1024))
        if self.max_responses > 100 or self.max_bytes > 25 * 1024 * 1024:
            raise ValueError("capture is capped at 100 responses and 25 MiB")
        self.sample_rate = self._integer(config["pcm_sample_rate"]) if "pcm_sample_rate" in config else None
        self.include_text = config.get("include_text", False)
        if not isinstance(self.include_text, bool):
            raise ValueError("capture include_text must be boolean")
        self.voice = config.get("voice", "")
        if not isinstance(self.voice, str):
            raise ValueError("capture voice must be a string")
        directory = config.get("directory")
        if not isinstance(directory, str) or not Path(directory).is_absolute():
            raise ValueError("capture directory must be an absolute path")
        path = Path(directory)
        if path.is_symlink():
            raise ValueError("capture directory must not be a symlink")
        path.mkdir(mode=0o700, exist_ok=True)
        self.directory = path.resolve(strict=True)
        self._check_private(self.directory, directory=True)
        self._mutex = threading.Lock()
        self._error = ""
        self._budget_exhausted = False
        # Validate old contents before accepting this destination on restart.
        with self._locked():
            self._usage()

    @staticmethod
    def _integer(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("capture limits and PCM sample rate must be positive integers")
        return value

    @staticmethod
    def _check_private(path: Path, *, directory: bool = False) -> None:
        info = path.lstat()
        valid_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if not valid_type or info.st_uid != os.geteuid() or info.st_mode & 0o077 or (not directory and info.st_nlink != 1):
            raise ValueError("audio capture requires owner-private files and directory")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self._mutex:
            self._check_private(self.directory, directory=True)
            fd = os.open(self.directory / "capture.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                    raise ValueError("unsafe audio capture lock")
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                os.close(fd)

    def _usage(self) -> tuple[int, int]:
        count, size = 0, 0
        for path in self.directory.iterdir():
            self._check_private(path)
            size += path.stat().st_size
            if path.name != "capture.lock" and path.suffix != ".json":
                count += 1
        return count, size

    @staticmethod
    def _write_new(path: Path, body: bytes) -> None:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(body)

    def save(self, body: bytes, audio_format: str, *, voice: str = "", delivered: bool = True,
             text: str | None = None) -> str | None:
        """Capture a successful upstream body; recording failure never breaks speech."""
        if self._error or self._budget_exhausted or not body or (self.voice and voice.casefold() != self.voice.casefold()):
            return None
        try:
            extension = {"wav": "wav", "mp3": "mp3", "flac": "flac", "pcm": "pcm"}.get(audio_format)
            if extension is None:
                return None
            now = datetime.now(timezone.utc)
            capture_id = now.strftime("%Y%m%dT%H%M%S.%fZ-") + uuid.uuid4().hex[:12]
            filename = capture_id + "." + extension
            metadata = {
                "capture_id": capture_id, "captured_at": now.isoformat(),
                "audio_file": filename, "response_format": audio_format,
                "response_bytes": len(body), "response_sha256": hashlib.sha256(body).hexdigest(),
                "pcm_sample_rate": self.sample_rate if audio_format == "pcm" else None,
                "client_write_completed": delivered,
            }
            if self.include_text:
                if not isinstance(text, str):
                    raise ValueError("capture target text was not supplied")
                metadata["input_text"] = text
            encoded = json.dumps(metadata, indent=2).encode("utf-8")
            with self._locked():
                count, used = self._usage()
                if count >= self.max_responses or used + len(body) + len(encoded) > self.max_bytes:
                    self._budget_exhausted = True
                    return None
                self._write_new(self.directory / filename, body)
                self._write_new(self.directory / (capture_id + ".json"), encoded)
            return capture_id
        except (OSError, ValueError) as exc:
            self._error = type(exc).__name__
            return None

    def status(self) -> dict[str, object]:
        """Return metadata only; never expose capture paths or recorded speech."""
        try:
            with self._locked():
                count, used = self._usage()
        except (OSError, ValueError) as exc:
            self._error = type(exc).__name__
            count, used = 0, 0
        return {"enabled": True, "include_text": self.include_text, "responses": count, "bytes": used,
                "max_responses": self.max_responses, "max_bytes": self.max_bytes,
                "stopped": bool(self._error or self._budget_exhausted or count >= self.max_responses or used >= self.max_bytes),
                "error_type": self._error}


def load_capture(path: Path) -> AudioCapture | None:
    """Read a local opt-in configuration; a missing file leaves capture disabled."""
    if not path.exists() and not path.is_symlink():
        return None
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_nlink != 1:
            raise ValueError("owner-private audio capture configuration required")
        data = stream.read(16 * 1024 + 1)
    if len(data) > 16 * 1024:
        raise ValueError("audio capture configuration is too large")
    config = json.loads(data)
    if not isinstance(config, dict) or not isinstance(config.get("enabled", False), bool):
        raise ValueError("audio capture configuration must be an object with boolean enabled")
    if not config.get("enabled", False):
        return None
    return AudioCapture(config)
