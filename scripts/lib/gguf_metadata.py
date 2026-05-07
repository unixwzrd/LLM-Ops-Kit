#!/usr/bin/env python3
"""Minimal GGUF metadata reader.

The reader parses only the GGUF header and metadata key/value table. It does
not read tensor payloads, so it is suitable for fast profile generation.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Any


GGUF_MAGIC = b"GGUF"

TYPE_UINT8 = 0
TYPE_INT8 = 1
TYPE_UINT16 = 2
TYPE_INT16 = 3
TYPE_UINT32 = 4
TYPE_INT32 = 5
TYPE_FLOAT32 = 6
TYPE_BOOL = 7
TYPE_STRING = 8
TYPE_ARRAY = 9
TYPE_UINT64 = 10
TYPE_INT64 = 11
TYPE_FLOAT64 = 12


class GgufError(ValueError):
    """Raised when a GGUF file cannot be read."""


@dataclass(frozen=True)
class GgufInspectResult:
    """GGUF inspection result."""

    path: Path
    version: int
    tensor_count: int
    metadata: dict[str, Any]

    @property
    def model_id(self) -> str:
        return self.path.name

    @property
    def architecture(self) -> str:
        return str(self.metadata.get("general.architecture", ""))

    @property
    def name(self) -> str:
        return str(self.metadata.get("general.name", self.path.stem))

    @property
    def context_length(self) -> int | None:
        for key in (
            f"{self.architecture}.context_length",
            "llama.context_length",
            "qwen2.context_length",
            "general.context_length",
        ):
            value = self.metadata.get(key)
            if isinstance(value, int):
                return value
        for key, value in self.metadata.items():
            if key.endswith(".context_length") and isinstance(value, int):
                return value
        return None

    def profile_defaults(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "name": self.path.stem,
            "type": "llm",
            "model_path": str(self.path),
            "model_id": self.model_id,
            "architecture": self.architecture,
            "display_name": self.name,
            "llama": {
                "ctx_size": self.context_length,
            },
            "source": {
                "format": "gguf",
                "metadata_keys": len(self.metadata),
            },
        }


def _read_exact(handle: BinaryIO, size: int) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise GgufError("unexpected end of GGUF file")
    return data


def _read_u32(handle: BinaryIO) -> int:
    return struct.unpack("<I", _read_exact(handle, 4))[0]


def _read_u64(handle: BinaryIO) -> int:
    return struct.unpack("<Q", _read_exact(handle, 8))[0]


def _read_string(handle: BinaryIO) -> str:
    size = _read_u64(handle)
    return _read_exact(handle, size).decode("utf-8")


def _read_scalar(handle: BinaryIO, value_type: int) -> Any:
    formats = {
        TYPE_UINT8: "<B",
        TYPE_INT8: "<b",
        TYPE_UINT16: "<H",
        TYPE_INT16: "<h",
        TYPE_UINT32: "<I",
        TYPE_INT32: "<i",
        TYPE_FLOAT32: "<f",
        TYPE_BOOL: "<?",
        TYPE_UINT64: "<Q",
        TYPE_INT64: "<q",
        TYPE_FLOAT64: "<d",
    }
    if value_type == TYPE_STRING:
        return _read_string(handle)
    fmt = formats.get(value_type)
    if fmt is None:
        raise GgufError(f"unsupported GGUF metadata value type: {value_type}")
    return struct.unpack(fmt, _read_exact(handle, struct.calcsize(fmt)))[0]


def _read_value(handle: BinaryIO, value_type: int) -> Any:
    if value_type != TYPE_ARRAY:
        return _read_scalar(handle, value_type)
    item_type = _read_u32(handle)
    item_count = _read_u64(handle)
    return [_read_scalar(handle, item_type) for _ in range(item_count)]


def read_gguf_metadata(path: Path) -> GgufInspectResult:
    """Read GGUF metadata from a local file."""

    model_path = path.expanduser()
    if not model_path.exists():
        raise GgufError(f"GGUF file not found: {model_path}")
    with model_path.open("rb") as handle:
        magic = _read_exact(handle, 4)
        if magic != GGUF_MAGIC:
            raise GgufError(f"not a GGUF file: {model_path}")
        version = _read_u32(handle)
        tensor_count = _read_u64(handle)
        metadata_count = _read_u64(handle)
        metadata: dict[str, Any] = {}
        for _ in range(metadata_count):
            key = _read_string(handle)
            value_type = _read_u32(handle)
            metadata[key] = _read_value(handle, value_type)
    return GgufInspectResult(path=model_path, version=version, tensor_count=tensor_count, metadata=metadata)


def cache_key(path: Path) -> str:
    stat = path.expanduser().stat()
    raw = f"{path.expanduser()}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def write_metadata_cache(result: GgufInspectResult, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key(result.path)}.json"
    payload = {
        "path": str(result.path),
        "version": result.version,
        "tensor_count": result.tensor_count,
        "metadata": result.metadata,
        "profile_defaults": result.profile_defaults(),
    }
    cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return cache_path
