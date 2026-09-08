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
            "printf '%s\\n' \"$@\" > \"$FAKE_LLAMA_ARGS\"\n"
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
