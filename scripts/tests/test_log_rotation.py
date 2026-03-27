#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from log_rotation import RotatingLogWriter


class FakeClock:
    def __init__(self, initial: float = 0.0):
        self.current = float(initial)

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += float(seconds)


class LogRotationTests(unittest.TestCase):
    def test_rotates_into_numbered_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            log_path = Path(tmp) / "proxy.log"
            writer = RotatingLogWriter(
                log_path,
                rotate_seconds=10,
                keep=3,
                fsync=False,
                time_fn=clock,
            )
            writer.write("first\n")
            clock.advance(11)
            writer.write("second\n")
            clock.advance(11)
            writer.write("third\n")

            self.assertEqual(log_path.read_text(encoding="utf-8"), "third\n")
            self.assertEqual((Path(tmp) / "proxy.log.0.log").read_text(encoding="utf-8"), "second\n")
            self.assertEqual((Path(tmp) / "proxy.log.1.log").read_text(encoding="utf-8"), "first\n")

    def test_prunes_older_rotations_beyond_keep(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            log_path = Path(tmp) / "proxy.log"
            writer = RotatingLogWriter(
                log_path,
                rotate_seconds=5,
                keep=2,
                fsync=False,
                time_fn=clock,
            )
            writer.write("zero\n")
            for value in ("one\n", "two\n", "three\n"):
                clock.advance(6)
                writer.write(value)

            self.assertEqual(log_path.read_text(encoding="utf-8"), "three\n")
            self.assertEqual((Path(tmp) / "proxy.log.0.log").read_text(encoding="utf-8"), "two\n")
            self.assertEqual((Path(tmp) / "proxy.log.1.log").read_text(encoding="utf-8"), "one\n")
            self.assertFalse((Path(tmp) / "proxy.log.2.log").exists())

    def test_zero_rotation_seconds_disables_rollover(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            log_path = Path(tmp) / "proxy.log"
            writer = RotatingLogWriter(
                log_path,
                rotate_seconds=0,
                keep=5,
                fsync=False,
                time_fn=clock,
            )
            writer.write("first\n")
            clock.advance(999)
            writer.write("second\n")

            self.assertEqual(log_path.read_text(encoding="utf-8"), "first\nsecond\n")
            self.assertFalse((Path(tmp) / "proxy.log.0.log").exists())


if __name__ == "__main__":
    unittest.main()
