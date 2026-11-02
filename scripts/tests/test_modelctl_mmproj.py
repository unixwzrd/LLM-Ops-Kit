#!/usr/bin/env python
"""Runtime regression coverage for llama.cpp vision-projector profiles."""

from __future__ import annotations

import json
import os
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELCTL = ROOT / "scripts" / "modelctl"


class ModelctlMmprojTests(unittest.TestCase):
    def _environment(self, root: Path, *, mmproj_path: Path) -> dict[str, str]:
        config = root / "config"
        (config / "models").mkdir(parents=True)
        model = root / "chat.gguf"
        model.touch()
        profile = {
            "schema_version": 2,
            "template_id": "llama-cpp",
            "name": "vision-chat",
            "type": "llm",
            "model_path": str(model),
            "mmproj_path": str(mmproj_path),
            "runtime": {"host": "127.0.0.1", "port": 19434, "threads": 1},
            "llama": {"ctx_size": 512, "gpu_layers": 0, "batch_size": 1, "ubatch_size": 1},
        }
        (config / "models" / "vision-chat.json").write_text(
            json.dumps(profile), encoding="utf-8"
        )

        fake_server = root / "fake-llama-server"
        fake_server.write_text(
            "#!/usr/bin/env bash\n"
            'if [[ "${1:-}" == "--help" ]]; then printf "%s\\n" "${FAKE_LLAMA_HELP:-}"; exit 0; fi\n'
            "printf '%s\\n' \"$@\" > \"$FAKE_LLAMA_ARGS\"\n"
            'if [[ -n "${FAKE_LLAMA_ERROR:-}" ]]; then echo "$FAKE_LLAMA_ERROR" >&2; exit 1; fi\n'
            'if [[ -n "${FAKE_LOG_SIGNAL:-}" ]]; then\n'
            '  printf "producer-before\\n"\n'
            '  while [[ ! -f "$FAKE_LOG_SIGNAL" ]]; do sleep 0.05; done\n'
            '  printf "producer-after-stdout\\n"\n'
            '  printf "producer-after-stderr\\n" >&2\n'
            'fi\n'
            'if [[ -n "${FAKE_LOG_SECOND_SIGNAL:-}" ]]; then\n'
            '  while [[ ! -f "$FAKE_LOG_SECOND_SIGNAL" ]]; do sleep 0.05; done\n'
            '  printf "producer-after-copytruncate\\n"\n'
            'fi\n'
            "trap 'exit 0' TERM INT\n"
            "while :; do sleep 1; done\n",
            encoding="utf-8",
        )
        fake_server.chmod(0o755)

        # Do not inherit a real user's model, port, logging or state overrides.
        env = {"HOME": str(root), "PATH": os.environ.get("PATH", os.defpath), "TMPDIR": str(root)}
        env.update(
            {
                "LLMOPS_ROOT": str(ROOT),
                "FAKE_LLAMA_ARGS": str(root / "argv.txt"),
                "LLAMA_SERVER_BIN": str(fake_server),
                "LLMOPS_CONFIG_HOME": str(config),
                "LLMOPS_DATA_HOME": str(root / "data"),
                "LLMOPS_STATE_HOME": str(root / "state"),
                "LLMOPS_CACHE_HOME": str(root / "cache"),
                "LLMOPS_PYTHON_BIN": sys.executable,
            }
        )
        return env

    def _start_with_loading(
        self, *, modern: bool, model_type: str = "llm", **settings: str
    ) -> list[str]:
        """Launch an isolated fake server and return its captured arguments."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mmproj = root / "mmproj.gguf"
            mmproj.touch()
            env = self._environment(root, mmproj_path=mmproj)
            profile_path = Path(env["LLMOPS_CONFIG_HOME"]) / "models" / "vision-chat.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["type"] = model_type
            if model_type == "embedding":
                profile["template_id"] = "embedding"
                profile.pop("mmproj_path")
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            env.update(
                USE_MLOCK="0", USE_NO_MMAP="0", DIRECT_IO="0",
                FAKE_LLAMA_HELP="--load-mode MODE" if modern else "--mmap --mlock --no-mmap --direct-io",
            )
            env.update(settings)
            try:
                result = subprocess.run(
                    [str(MODELCTL), "vision-chat", "start"],
                    capture_output=True, text=True, env=env, timeout=15, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return (root / "argv.txt").read_text(encoding="utf-8").splitlines()
            finally:
                subprocess.run(
                    [str(MODELCTL), "vision-chat", "stop"],
                    capture_output=True, text=True, env=env, timeout=15, check=False,
                )

    def test_modern_loading_preserves_memory_settings(self) -> None:
        for settings, mode in (
            ({}, "auto"),
            ({"USE_MLOCK": "1"}, "mmap+mlock"),
            ({"USE_NO_MMAP": "1"}, "none"),
            ({"USE_MLOCK": "1", "USE_NO_MMAP": "1"}, "mlock"),
            ({"DIRECT_IO": "1"}, "dio"),
        ):
            with self.subTest(settings=settings):
                argv = self._start_with_loading(modern=True, **settings)
                self.assertEqual(argv[argv.index("--load-mode") + 1], mode)
                for obsolete in ("--mlock", "--mmap", "--no-mmap", "--direct-io"):
                    self.assertNotIn(obsolete, argv)

    def test_modern_embedding_uses_mmap_loading_mode(self) -> None:
        argv = self._start_with_loading(modern=True, model_type="embedding")
        self.assertEqual(argv[argv.index("--load-mode") + 1], "mmap")
        self.assertNotIn("--mmap", argv)
        self.assertIn("--embedding", argv)

    def test_legacy_loading_switches_are_retained(self) -> None:
        argv = self._start_with_loading(modern=False, USE_MLOCK="1", USE_NO_MMAP="1", DIRECT_IO="1")
        for flag in ("--mlock", "--no-mmap", "--direct-io"):
            self.assertIn(flag, argv)
        self.assertNotIn("--load-mode", argv)
        argv = self._start_with_loading(modern=False, model_type="embedding")
        self.assertIn("--mmap", argv)

    def test_modern_direct_io_and_mlock_fail_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mmproj = root / "mmproj.gguf"
            mmproj.touch()
            env = self._environment(root, mmproj_path=mmproj)
            env.update(FAKE_LLAMA_HELP="--load-mode MODE", DIRECT_IO="1", USE_MLOCK="1")
            result = subprocess.run(
                [str(MODELCTL), "vision-chat", "start"],
                capture_output=True, text=True, env=env, timeout=10, check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("cannot be combined", result.stderr)
            self.assertFalse((root / "argv.txt").exists())

    def test_early_argument_error_is_captured_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mmproj = root / "mmproj.gguf"
            mmproj.touch()
            env = self._environment(root, mmproj_path=mmproj)
            error = "error: invalid argument: --unsupported-test-option"
            env.update(FAKE_LLAMA_ERROR=error)
            result = subprocess.run(
                [str(MODELCTL), "vision-chat", "start"],
                capture_output=True, text=True, env=env, timeout=10, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(error, result.stderr)
            logs = list(Path(env["LLMOPS_STATE_HOME"]).rglob("*.log"))
            self.assertTrue(any(error in p.read_text(encoding="utf-8") for p in logs))
            argv = (root / "argv.txt").read_text(encoding="utf-8").splitlines()
            self.assertNotIn("--log-file", argv)

    def test_model_output_appends_after_independent_marker_and_tail_f_observes_it(self) -> None:
        """A concurrent marker must never strand later producer writes before EOF."""
        tail = shutil.which("tail")
        if not tail:
            self.skipTest("tail command is unavailable")
        for model_type, tts_runtime_path in (("llm", None), ("embedding", None), ("tts", ""), ("tts", str(Path(sys.executable).parent))):
            with self.subTest(model_type=model_type, tts_runtime_path=tts_runtime_path):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    projector = root / "mmproj.gguf"
                    projector.touch()
                    env = self._environment(root, mmproj_path=projector)
                    config = Path(env["LLMOPS_CONFIG_HOME"]) / "models" / "vision-chat.json"
                    profile = json.loads(config.read_text(encoding="utf-8"))
                    profile["type"] = model_type
                    if model_type != "llm":
                        profile.pop("mmproj_path", None)
                        profile["template_id"] = "embedding" if model_type == "embedding" else "tts"
                    with socket.socket() as reservation:
                        reservation.bind((profile["runtime"]["host"], 0))
                        profile["runtime"]["port"] = reservation.getsockname()[1]
                    config.write_text(json.dumps(profile), encoding="utf-8")
                    signal = root / "go"
                    env.update(FAKE_LOG_SIGNAL=str(signal), LLMOPS_LOG_MARKTIME_ENABLED="0")
                    if model_type == "tts":
                        env.update(TTS_PYTHON_BIN=env["LLAMA_SERVER_BIN"], TTS_SERVER_MODULE="fixture_tts_module",
                                   TTS_RUNTIME_PATH=tts_runtime_path or "")
                    follower = None
                    try:
                        started = subprocess.run([str(MODELCTL), profile["name"], "start"],
                                                 capture_output=True, text=True, env=env, timeout=15)
                        self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
                        if model_type == "tts":
                            self.assertEqual((root / "argv.txt").read_text().splitlines()[0], "-u")
                        prefix = "tts-server-" if model_type == "tts" else "llama-server-"
                        log_path = Path(env["LLMOPS_STATE_HOME"]) / "logs" / (prefix + profile["name"] + ".log")
                        self.assertIn("producer-before", log_path.read_text(encoding="utf-8"))
                        follower = subprocess.Popen([tail, "-n", "0", "-F", str(log_path)],
                                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        # Give tail time to establish its initial offset before the marker.
                        time.sleep(0.3)
                        marker = "MARKTIME " + ("independent-marker " * 128) + "\n"
                        with log_path.open("a", encoding="utf-8") as stream:
                            stream.write(marker)
                        observed = b""
                        deadline = time.monotonic() + 8
                        while b"MARKTIME" not in observed and time.monotonic() < deadline:
                            if select.select([follower.stdout], [], [], 0.2)[0]:
                                observed += os.read(follower.stdout.fileno(), 65536)
                        self.assertIn(b"MARKTIME", observed, "tail did not observe the marker")
                        signal.touch()
                        deadline = time.monotonic() + 6
                        while time.monotonic() < deadline:
                            current = log_path.read_text(encoding="utf-8")
                            if "producer-after-stderr" in current:
                                break
                            time.sleep(0.05)
                        self.assertIn(marker, current, "producer overwrote the independent marker")
                        self.assertTrue(current.endswith("producer-after-stdout\nproducer-after-stderr\n"))
                        deadline = time.monotonic() + 8
                        while b"producer-after-stderr" not in observed and time.monotonic() < deadline:
                            if select.select([follower.stdout], [], [], 0.2)[0]:
                                observed += os.read(follower.stdout.fileno(), 65536)
                        self.assertIn(b"producer-after-stdout", observed)
                        self.assertIn(b"producer-after-stderr", observed)
                    finally:
                        if follower is not None:
                            follower.terminate()
                            follower.communicate(timeout=5)
                        subprocess.run([str(MODELCTL), profile["name"], "stop"],
                                       capture_output=True, text=True, env=env, timeout=15)

    def test_start_passes_configured_mmproj_as_one_argument_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mmproj = root / "mmproj.gguf"
            mmproj.touch()
            env = self._environment(root, mmproj_path=mmproj)
            try:
                started = subprocess.run(
                    [str(MODELCTL), "vision-chat", "start"],
                    check=False,
                    capture_output=True,
                    env=env,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(started.returncode, 0, started.stderr)
                argv_path = root / "argv.txt"
                deadline = time.monotonic() + 3
                while not argv_path.is_file() and time.monotonic() < deadline:
                    time.sleep(0.05)
                argv = argv_path.read_text(encoding="utf-8").splitlines()
                index = argv.index("--mmproj")
                self.assertEqual(argv[index + 1], str(mmproj))
            finally:
                subprocess.run(
                    [str(MODELCTL), "vision-chat", "stop"],
                    check=False,
                    capture_output=True,
                    env=env,
                    text=True,
                    timeout=10,
                )

    def test_model_output_and_tail_survive_copytruncate_maintenance(self) -> None:
        """The real model launcher keeps appending after the existing rotation helper truncates."""
        tail = shutil.which("tail")
        if not tail:
            self.skipTest("tail command is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projector = root / "mmproj.gguf"
            projector.touch()
            env = self._environment(root, mmproj_path=projector)
            config = Path(env["LLMOPS_CONFIG_HOME"]) / "models" / "vision-chat.json"
            profile = json.loads(config.read_text(encoding="utf-8"))
            with socket.socket() as reservation:
                reservation.bind((profile["runtime"]["host"], 0))
                profile["runtime"]["port"] = reservation.getsockname()[1]
            config.write_text(json.dumps(profile), encoding="utf-8")
            env.update(FAKE_LOG_SIGNAL=str(root / "first-go"), FAKE_LOG_SECOND_SIGNAL=str(root / "second-go"),
                       LLMOPS_LOG_MARKTIME_ENABLED="0")
            follower = None
            try:
                started = subprocess.run([str(MODELCTL), profile["name"], "start"], env=env,
                                         capture_output=True, text=True, timeout=15)
                self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
                log_path = Path(env["LLMOPS_STATE_HOME"]) / "logs" / ("llama-server-" + profile["name"] + ".log")
                follower = subprocess.Popen([tail, "-n", "0", "-F", str(log_path)],
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                time.sleep(0.3)
                marker_before = "MARKTIME " + ("pre-rotation " * 128) + "\n"
                with log_path.open("a", encoding="utf-8") as stream:
                    stream.write(marker_before)
                observed = b""
                deadline = time.monotonic() + 8
                while b"MARKTIME" not in observed and time.monotonic() < deadline:
                    if select.select([follower.stdout], [], [], 0.2)[0]:
                        observed += os.read(follower.stdout.fileno(), 65536)
                self.assertIn(b"MARKTIME", observed)
                (root / "first-go").touch()
                deadline = time.monotonic() + 5
                while "producer-after-stderr" not in log_path.read_text() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertIn("producer-after-stderr", log_path.read_text())
                archive = root / "prior.log"
                common = ROOT / "scripts" / "lib" / "common.sh"
                rotated = subprocess.run(["/bin/bash", "-c", '. "$1"; archive_and_truncate_log "$2" "$3"',
                                          "_", str(common), str(log_path), str(archive)],
                                         env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(rotated.returncode, 0, rotated.stdout + rotated.stderr)
                self.assertIn(marker_before, archive.read_text(encoding="utf-8"))
                marker_after = "post-rotation marker\n"
                with log_path.open("a", encoding="utf-8") as stream:
                    stream.write(marker_after)
                deadline = time.monotonic() + 8
                while marker_after.encode() not in observed and time.monotonic() < deadline:
                    if select.select([follower.stdout], [], [], 0.2)[0]:
                        observed += os.read(follower.stdout.fileno(), 65536)
                self.assertIn(marker_after.encode(), observed, "tail -F did not follow copytruncate")
                (root / "second-go").touch()
                deadline = time.monotonic() + 5
                while "producer-after-copytruncate" not in log_path.read_text() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertEqual(log_path.read_text(), marker_after + "producer-after-copytruncate\n")
                deadline = time.monotonic() + 8
                while b"producer-after-copytruncate" not in observed and time.monotonic() < deadline:
                    if select.select([follower.stdout], [], [], 0.2)[0]:
                        observed += os.read(follower.stdout.fileno(), 65536)
                self.assertIn(b"producer-after-copytruncate", observed)
            finally:
                if follower is not None:
                    follower.terminate()
                    follower.communicate(timeout=5)
                subprocess.run([str(MODELCTL), profile["name"], "stop"], env=env,
                               capture_output=True, text=True, timeout=15)

    def test_missing_mmproj_fails_before_server_start(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "missing-mmproj.gguf"
            env = self._environment(root, mmproj_path=missing)
            result = subprocess.run(
                [str(MODELCTL), "vision-chat", "start"],
                check=False,
                capture_output=True,
                env=env,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Configured MMPROJ does not exist", result.stderr)
            self.assertFalse((root / "argv.txt").exists())


if __name__ == "__main__":
    unittest.main()
