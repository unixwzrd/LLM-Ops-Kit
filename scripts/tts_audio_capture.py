"""Opt-in, owner-private, bounded capture of generated TTS response audio."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


_EXTENSIONS = {"wav": "wav", "mp3": "mp3", "flac": "flac", "pcm": "pcm"}
_PAIR_NAME = re.compile(r"([0-9]{20})-([0-9]{8}T[0-9]{6}\.[0-9]{6}Z-[0-9a-f]{12})")


class AudioCapture:
    """Save responses and optionally target text, never headers or references.

    A filesystem lock and directory accounting enforce limits across threads,
    processes and restarts. Only the opt-in rolling mode retires old pairs.
    """

    def __init__(self, config: dict[str, object]) -> None:
        allowed = {"enabled", "directory", "max_responses", "max_bytes", "pcm_sample_rate", "voice", "include_text", "retention"}
        if set(config) - allowed or config.get("enabled") is not True:
            raise ValueError("invalid enabled audio capture configuration")
        self.retention = config.get("retention", "batch")
        if self.retention not in ("batch", "rolling"):
            raise ValueError("audio capture retention must be batch or rolling")
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
        self._oversize_skipped = 0
        # Validate old contents before accepting this destination on restart.
        with self._locked():
            if self.retention == "rolling":
                self._recover_rolling()
            self._usage()

    @staticmethod
    def _integer(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("capture limits and PCM sample rate must be positive integers")
        return value

    @staticmethod
    def _check_private(path: Path, *, directory: bool = False) -> os.stat_result:
        info = path.lstat()
        valid_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if not valid_type or info.st_uid != os.geteuid() or info.st_mode & 0o077 or (not directory and info.st_nlink != 1):
            raise ValueError("audio capture requires owner-private files and directory")
        return info

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self._mutex:
            self._check_private(self.directory, directory=True)
            fd = os.open(self.directory / "capture.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_nlink != 1:
                    raise ValueError("unsafe audio capture lock")
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                os.close(fd)

    def _usage(self) -> tuple[int, int]:
        if self.retention == "rolling":
            pairs = self._rolling_pairs()
            return len(pairs), sum(size for _, _, _, size in pairs)
        count, size = 0, 0
        for path in self.directory.iterdir():
            size += self._check_private(path).st_size
            if path.name != "capture.lock" and path.suffix != ".json":
                count += 1
        return count, size

    @staticmethod
    def _pair_files(pair: Path, capture_id: str, *, complete: bool) -> tuple[list[Path], int]:
        AudioCapture._check_private(pair, directory=True)
        files = list(pair.iterdir())
        names = {path.name for path in files}
        audio = names - {"receipt.json"}
        if len(audio) > 1 or not audio <= {f"{capture_id}.{ext}" for ext in _EXTENSIONS.values()}:
            raise ValueError("unexpected file in rolling capture pair")
        if complete and (not audio or "receipt.json" not in names):
            raise ValueError("incomplete rolling capture pair")
        return files, sum(AudioCapture._check_private(path).st_size for path in files)

    @classmethod
    def _discard_pair(cls, pair: Path, capture_id: str) -> None:
        files, _ = cls._pair_files(pair, capture_id, complete=False)
        for file in files:
            file.unlink()
        pair.rmdir()

    def _recover_rolling(self) -> None:
        # Only private, exact-format staging/tombstone directories from a
        # previous interrupted write may be discarded. Never sweep unknown files.
        for path in self.directory.iterdir():
            for prefix in (".pending-", ".expired-"):
                match = _PAIR_NAME.fullmatch(path.name.removeprefix(prefix))
                if path.name.startswith(prefix) and match:
                    self._discard_pair(path, match[2])
                    break

    def _rolling_pairs(self) -> list[tuple[int, Path, str, int]]:
        """Use only complete private pairs in an exclusive rolling directory."""
        pairs: list[tuple[int, Path, str, int]] = []
        for pair in self.directory.iterdir():
            if pair.name == "capture.lock":
                continue
            match = _PAIR_NAME.fullmatch(pair.name)
            if not match:
                raise ValueError("rolling capture requires a dedicated empty directory or complete rolling pairs")
            _, size = self._pair_files(pair, match[2], complete=True)
            pairs.append((int(match[1]), pair, match[2], size))
        return sorted(pairs)

    def _save_rolling(self, capture_id: str, filename: str, body: bytes, receipt: bytes) -> bool:
        """Publish two files together and evict only complete oldest pairs under the lock."""
        size = len(body) + len(receipt)
        if size > self.max_bytes:
            self._oversize_skipped += 1
            return False
        pairs = self._rolling_pairs()
        used = sum(item[3] for item in pairs)
        sequence = pairs[-1][0] + 1 if pairs else 1
        destination = self.directory / f"{sequence:020d}-{capture_id}"
        while len(pairs) >= self.max_responses or used + size > self.max_bytes:
            _, pair, old_id, old_size = pairs.pop(0)
            # Hide the pair atomically, so readers never see a partial pair.
            expired = pair.with_name(".expired-" + pair.name)
            pair.rename(expired)
            self._discard_pair(expired, old_id)
            used -= old_size
        stage = destination.with_name(".pending-" + destination.name)
        stage.mkdir(mode=0o700)
        try:
            self._write_new(stage / filename, body)
            self._write_new(stage / "receipt.json", receipt)
            stage.rename(destination)
        finally:
            if stage.exists():
                self._discard_pair(stage, capture_id)
        return True

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
            extension = _EXTENSIONS.get(audio_format)
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
                if self.retention == "rolling":
                    return capture_id if self._save_rolling(capture_id, filename, body, encoded) else None
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
        full_batch = self.retention == "batch" and (self._budget_exhausted or count >= self.max_responses or used >= self.max_bytes)
        return {"enabled": True, "include_text": self.include_text, "responses": count, "bytes": used,
                "retention": self.retention, "oversize_skipped": self._oversize_skipped,
                "max_responses": self.max_responses, "max_bytes": self.max_bytes,
                "stopped": bool(self._error or full_batch),
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
