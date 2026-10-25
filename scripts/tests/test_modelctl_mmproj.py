#!/usr/bin/env python
"""Runtime regression coverage for llama.cpp vision-projector profiles."""

from __future__ import annotations

import json
import os
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
            "trap 'exit 0' TERM INT\n"
            "while :; do sleep 1; done\n",
            encoding="utf-8",
        )
        fake_server.chmod(0o755)

        env = dict(os.environ)
        env.update(
            {
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
