#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMON_SH = REPO_ROOT / "scripts/lib/common.sh"
MODELCTL = REPO_ROOT / "scripts/modelctl"
GATEWAY = REPO_ROOT / "scripts/gateway"


class ShellRuntimeHelperTests(unittest.TestCase):
    def run_bash(self, script: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        merged = os.environ.copy()
        if env:
            merged.update(env)
        return subprocess.run(
            ["bash", "-lc", script],
            text=True,
            capture_output=True,
            env=merged,
            check=False,
        )

    def test_marktime_helper_writes_marker_and_cleans_up_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            log_path = Path(tmp) / "marktime.log"
            script = f"""
                . "{COMMON_SH}"
                export LLMOPS_RUN_DIR="{run_dir}"
                export LLMOPS_LOG_MARKTIME_INTERVAL_SECONDS=1
                mkdir -p "$LLMOPS_RUN_DIR"
                : > "{log_path}"
                start_log_marktime testsvc Qwen3.5 "{log_path}"
                sleep 2
                stop_log_marktime testsvc
                cat "{log_path}"
                test ! -f "$LLMOPS_RUN_DIR/testsvc-marktime.pid"
            """
            proc = self.run_bash(script)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("========== Qwen3.5 - MARKTIME", proc.stdout)
            self.assertIn("UTC", proc.stdout)

    def test_modelctl_seeds_env_override_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            llmops_home = home / ".llm-ops"
            config_dir = llmops_home / "config"
            config_dir.mkdir(parents=True)
            proc = self.run_bash(
                f'"{MODELCTL}" Qwen3.5 settings',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            seeded = config_dir / "Qwen3.5.env"
            self.assertTrue(seeded.exists(), proc.stderr + proc.stdout)
            self.assertIn("copied template config", proc.stderr)

    def test_modelctl_uses_legacy_sh_override_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            llmops_home = home / ".llm-ops"
            config_dir = llmops_home / "config"
            config_dir.mkdir(parents=True)
            legacy = config_dir / "Qwen3.5.sh"
            legacy.write_text("USE_CUSTOM_TEMPLATE=0\nTOP_K=77\n", encoding="utf-8")
            proc = self.run_bash(
                f'"{MODELCTL}" Qwen3.5 settings',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("legacy per-model override", proc.stderr)
            self.assertIn("prefer renaming it", proc.stderr)
            self.assertIn("TOP_K=77", proc.stdout)
            self.assertFalse((config_dir / "Qwen3.5.env").exists())

    def _write_fake_gateway_cmd(self, root: Path) -> Path:
        script = root / "fake-gateway"
        script.write_text(
            "#!/usr/bin/env bash\n"
            "trap 'exit 0' TERM INT\n"
            "echo \"$0 $*\" >> \"$FAKE_GATEWAY_INVOCATIONS\"\n"
            "while :; do sleep 1; done\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script

    def test_gateway_start_stop_openclaw_with_fake_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            hermes_home = home / ".hermes"
            invocations = root / "gateway-invocations.log"
            fake_cmd = self._write_fake_gateway_cmd(root)

            base_env = {
                "HOME": str(home),
                "LLMOPS_HOME": str(llmops_home),
                "HERMES_HOME": str(hermes_home),
                "LLMOPS_USE_SECKIT": "0",
                "OPENCLAW_GATEWAY_CMD": str(fake_cmd),
                "HERMES_GATEWAY_CMD": str(fake_cmd),
                "FAKE_GATEWAY_INVOCATIONS": str(invocations),
            }

            start = self.run_bash(f'"{GATEWAY}" start openclaw', env=base_env)
            self.assertEqual(start.returncode, 0, start.stderr)
            self.assertIn("gateway[openclaw]: started pid=", start.stdout)

            status = self.run_bash(f'"{GATEWAY}" status openclaw', env=base_env)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("gateway[openclaw]: running pid=", status.stdout)
            self.assertIn("gateway-openclaw.log", status.stdout)

            stop = self.run_bash(f'"{GATEWAY}" stop openclaw', env=base_env)
            self.assertEqual(stop.returncode, 0, stop.stderr)
            self.assertIn("gateway-openclaw: stopped pid", stop.stdout)

    def test_gateway_start_status_all_uses_separate_namespaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            hermes_home = home / ".hermes"
            invocations = root / "gateway-invocations.log"
            fake_cmd = self._write_fake_gateway_cmd(root)

            base_env = {
                "HOME": str(home),
                "LLMOPS_HOME": str(llmops_home),
                "HERMES_HOME": str(hermes_home),
                "LLMOPS_USE_SECKIT": "0",
                "OPENCLAW_GATEWAY_CMD": str(fake_cmd),
                "HERMES_GATEWAY_CMD": str(fake_cmd),
                "FAKE_GATEWAY_INVOCATIONS": str(invocations),
            }

            start = self.run_bash(f'"{GATEWAY}" start all', env=base_env)
            self.assertEqual(start.returncode, 0, start.stderr)
            self.assertIn("gateway[openclaw]: started pid=", start.stdout)
            self.assertIn("gateway[hermes]: started pid=", start.stdout)

            status = self.run_bash(f'"{GATEWAY}" status all', env=base_env)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("gateway[openclaw]: running pid=", status.stdout)
            self.assertIn("gateway[hermes]: running pid=", status.stdout)
            self.assertIn("gateway-openclaw.log", status.stdout)
            self.assertIn("gateway-hermes.log", status.stdout)

            pid_dir = llmops_home / "run"
            self.assertTrue((pid_dir / "gateway-openclaw.pid").exists())
            self.assertTrue((pid_dir / "gateway-hermes.pid").exists())

            stop = self.run_bash(f'"{GATEWAY}" stop all', env=base_env)
            self.assertEqual(stop.returncode, 0, stop.stderr)
            self.assertIn("gateway-openclaw: stopped pid", stop.stdout)
            self.assertIn("gateway-hermes: stopped pid", stop.stdout)


if __name__ == "__main__":
    unittest.main()
