#!/usr/bin/env python
from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import tempfile
import time
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
    def _run_with_standard_streams(self, *, unrelated_stderr: bool, tail_follow: bool) -> None:
        """Only subprocess-owned file descriptors are changed by these rotation tests."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log_path, other_path = root / "service.log", root / "other.log"
            ready, proceed, result = root / "ready", root / "proceed", root / "result.json"
            child_code = '''
import fcntl, json, os, pathlib, sys, time
from log_rotation import RotatingLogWriter
log, ready, proceed, result = map(pathlib.Path, sys.argv[1:])
clock = [0.0]
writer = RotatingLogWriter(log, rotate_seconds=1, keep=3, fsync=False,
                           time_fn=lambda: clock[0], reopen_standard_streams=True)
os.set_inheritable(1, False)
os.set_inheritable(2, True)
before_inheritable = [os.get_inheritable(1), os.get_inheritable(2)]
before_err = (os.fstat(2).st_dev, os.fstat(2).st_ino)
writer.write("application-before\\n")
os.write(1, b"stdout-before\\n")
os.write(2, b"stderr-before\\n")
ready.touch()
limit = time.monotonic() + 15
while not proceed.exists() and time.monotonic() < limit:
    time.sleep(0.02)
if not proceed.exists():
    raise RuntimeError("fixture timed out before rotation")
clock[0] = 2.0
writer.write("application-after\\n")
after_err = (os.fstat(2).st_dev, os.fstat(2).st_ino)
active = (log.stat().st_dev, log.stat().st_ino)
state = {"stdout_current": (os.fstat(1).st_dev, os.fstat(1).st_ino) == active,
         "stderr_current": after_err == active,
         "stderr_unchanged": before_err == after_err,
         "inheritable_unchanged": before_inheritable == [os.get_inheritable(1), os.get_inheritable(2)],
         "stdout_append": bool(fcntl.fcntl(1, fcntl.F_GETFL) & os.O_APPEND),
         "stderr_append": bool(fcntl.fcntl(2, fcntl.F_GETFL) & os.O_APPEND)}
os.write(1, b"stdout-after\\n")
os.write(2, b"stderr-after\\n")
result.write_text(json.dumps(state), encoding="utf-8")
'''
            env = {"HOME": str(root), "PATH": os.environ.get("PATH", os.defpath),
                   "TMPDIR": str(root), "PYTHONPATH": str(SCRIPTS_DIR)}
            follower = None
            with log_path.open("ab", buffering=0) as log_file, other_path.open("ab", buffering=0) as other_file:
                child = subprocess.Popen([sys.executable, "-B", "-c", child_code,
                                          str(log_path), str(ready), str(proceed), str(result)],
                                         env=env, stdout=log_file,
                                         stderr=other_file if unrelated_stderr else log_file)
                try:
                    deadline = time.monotonic() + 5
                    while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.03)
                    self.assertTrue(ready.exists(), "child failed before rotation: " + other_path.read_text())
                    observed = b""
                    if tail_follow:
                        tail = shutil.which("tail")
                        if not tail:
                            self.skipTest("tail command is unavailable")
                        follower = subprocess.Popen([tail, "-n", "0", "-F", str(log_path)],
                                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        time.sleep(0.3)
                    marker = "MARKTIME " + ("concurrent-marker " * 32) + "\n"
                    with log_path.open("a", encoding="utf-8") as marker_stream:
                        marker_stream.write(marker)
                    if follower is not None:
                        deadline = time.monotonic() + 8
                        while b"MARKTIME" not in observed and time.monotonic() < deadline:
                            if select.select([follower.stdout], [], [], 0.2)[0]:
                                observed += os.read(follower.stdout.fileno(), 65536)
                        self.assertIn(b"MARKTIME", observed)
                    proceed.touch()
                    self.assertEqual(child.wait(timeout=10), 0, other_path.read_text())
                    state = json.loads(result.read_text(encoding="utf-8"))
                    self.assertTrue(state["stdout_current"])
                    self.assertTrue(state["stdout_append"])
                    self.assertTrue(state["inheritable_unchanged"])
                    self.assertEqual(state["stderr_current"], not unrelated_stderr)
                    self.assertEqual(state["stderr_unchanged"], unrelated_stderr)
                    self.assertTrue(state["stderr_append"])
                    archived = log_path.with_name(log_path.name + ".0.log").read_text(encoding="utf-8")
                    current = log_path.read_text(encoding="utf-8")
                    self.assertIn("application-before\nstdout-before\n", archived)
                    self.assertIn(marker, archived)
                    self.assertIn("application-after\nstdout-after\n", current)
                    if unrelated_stderr:
                        self.assertNotIn("stderr-before", archived)
                        self.assertNotIn("stderr-after", current)
                        self.assertEqual(other_path.read_text(), "stderr-before\nstderr-after\n")
                    else:
                        self.assertIn("stderr-before\n", archived)
                        self.assertIn("stderr-after\n", current)
                    if follower is not None:
                        deadline = time.monotonic() + 8
                        while b"stderr-after" not in observed and time.monotonic() < deadline:
                            if select.select([follower.stdout], [], [], 0.2)[0]:
                                observed += os.read(follower.stdout.fileno(), 65536)
                        self.assertIn(b"stdout-after", observed, "tail -F missed the new active log")
                        self.assertIn(b"stderr-after", observed)
                finally:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=5)
                    if follower is not None:
                        follower.terminate()
                        follower.communicate(timeout=5)

    def test_reopens_both_streams_and_tail_f_follows_rotation(self) -> None:
        self._run_with_standard_streams(unrelated_stderr=False, tail_follow=True)

    def test_does_not_redirect_an_unrelated_stderr_stream(self) -> None:
        self._run_with_standard_streams(unrelated_stderr=True, tail_follow=False)

    def test_default_rotation_does_not_reassign_matching_standard_stream(self) -> None:
        """Only explicit bridge opt-in may change process-wide file descriptors."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log_path, result = root / "default.log", root / "state.json"
            code = '''
import json, os, pathlib, sys
from log_rotation import RotatingLogWriter
path, result = map(pathlib.Path, sys.argv[1:])
clock = [0.0]
writer = RotatingLogWriter(path, rotate_seconds=1, keep=1, fsync=False, time_fn=lambda: clock[0])
writer.write("application-before\\n")
before = (os.fstat(1).st_dev, os.fstat(1).st_ino)
clock[0] = 2.0
writer.write("application-after\\n")
after = (os.fstat(1).st_dev, os.fstat(1).st_ino)
os.write(1, b"stdout-stays-on-original\\n")
result.write_text(json.dumps({"unchanged": before == after,
                              "different_from_current": after != (path.stat().st_dev, path.stat().st_ino)}))
'''
            with log_path.open("ab", buffering=0) as stream:
                completed = subprocess.run([sys.executable, "-B", "-c", code, str(log_path), str(result)],
                                           env={"HOME": str(root), "PATH": os.environ.get("PATH", os.defpath),
                                                "TMPDIR": str(root), "PYTHONPATH": str(SCRIPTS_DIR)}, stdout=stream,
                                           capture_output=False, timeout=10)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(result.read_text()), {"unchanged": True, "different_from_current": True})
            self.assertIn("stdout-stays-on-original", log_path.with_name(log_path.name + ".0.log").read_text())
            self.assertNotIn("stdout-stays-on-original", log_path.read_text())

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
