#!/usr/bin/env python
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from llmops_kit.gguf_metadata import (
    TYPE_STRING,
    TYPE_UINT32,
    read_gguf_metadata,
    write_metadata_cache,
)


def _write_string(blob: bytearray, value: str) -> None:
    encoded = value.encode("utf-8")
    blob.extend(struct.pack("<Q", len(encoded)))
    blob.extend(encoded)


def _write_metadata_string(blob: bytearray, key: str, value: str) -> None:
    _write_string(blob, key)
    blob.extend(struct.pack("<I", TYPE_STRING))
    _write_string(blob, value)


def _write_metadata_u32(blob: bytearray, key: str, value: int) -> None:
    _write_string(blob, key)
    blob.extend(struct.pack("<I", TYPE_UINT32))
    blob.extend(struct.pack("<I", value))


def write_minimal_gguf(path: Path) -> None:
    blob = bytearray()
    blob.extend(b"GGUF")
    blob.extend(struct.pack("<I", 3))
    blob.extend(struct.pack("<Q", 0))
    blob.extend(struct.pack("<Q", 3))
    _write_metadata_string(blob, "general.architecture", "qwen2")
    _write_metadata_string(blob, "general.name", "Qwen3.6 Test")
    _write_metadata_u32(blob, "qwen2.context_length", 32768)
    path.write_bytes(bytes(blob))


class GgufMetadataTests(unittest.TestCase):
    def test_reads_metadata_and_profile_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "Qwen3.6-Test.gguf"
            write_minimal_gguf(model)
            result = read_gguf_metadata(model)
            self.assertEqual(result.version, 3)
            self.assertEqual(result.model_id, "Qwen3.6-Test.gguf")
            self.assertEqual(result.architecture, "qwen2")
            self.assertEqual(result.name, "Qwen3.6 Test")
            self.assertEqual(result.context_length, 32768)
            self.assertEqual(result.profile_defaults()["llama"]["ctx_size"], 32768)

    def test_writes_metadata_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "Qwen3.6-Test.gguf"
            cache = root / "cache"
            write_minimal_gguf(model)
            result = read_gguf_metadata(model)
            cache_path = write_metadata_cache(result, cache)
            self.assertTrue(cache_path.exists())
            self.assertIn("Qwen3.6 Test", cache_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
