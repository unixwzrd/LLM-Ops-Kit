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
AGENTCTL = REPO_ROOT / "scripts/agentctl"


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

    def test_seckit_export_failure_is_quiet_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_bin = Path(tmp) / "fake-seckit"
            fake_bin.write_text(
                "#!/usr/bin/env bash\n"
                "echo 'ERROR: export failed' >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_bin.chmod(0o755)
            script = f"""
                . \"{COMMON_SH}\"
                export LLMOPS_USE_SECKIT=1
                export LLMOPS_SECKIT_BIN=\"{fake_bin}\"
                maybe_load_seckit_env
                printf 'ok\\n'
            """
            proc = self.run_bash(script)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stderr, "")
            self.assertEqual(proc.stdout.strip(), "ok")

    def test_seckit_export_failure_can_be_verbose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_bin = Path(tmp) / "fake-seckit"
            fake_bin.write_text(
                "#!/usr/bin/env bash\n"
                "echo 'ERROR: export failed' >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_bin.chmod(0o755)
            script = f"""
                . \"{COMMON_SH}\"
                export LLMOPS_USE_SECKIT=1
                export LLMOPS_SECKIT_BIN=\"{fake_bin}\"
                export LLMOPS_SECKIT_QUIET_FAILURES=0
                maybe_load_seckit_env
            """
            proc = self.run_bash(script)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Secrets Kit export failed", proc.stderr)
            self.assertIn("ERROR: export failed", proc.stderr)

    def test_seckit_failed_with_env_secret_fallback_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_bin = Path(tmp) / "fake-seckit"
            fake_bin.write_text(
                "#!/usr/bin/env bash\n"
                "echo 'ERROR: export failed' >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_bin.chmod(0o755)
            script = f"""
                . \"{COMMON_SH}\"
                export LLMOPS_USE_SECKIT=1
                export LLMOPS_SECKIT_BIN=\"{fake_bin}\"
                export LLMOPS_REQUIRED_SECRETS=\"OPENAI_API_KEY TELEGRAM_BOT_TOKEN\"
                export OPENAI_API_KEY=sk-local
                maybe_load_seckit_env
                maybe_warn_env_secret_fallback
            """
            proc = self.run_bash(script)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Secrets Kit fallback in use", proc.stderr)
            self.assertIn("OPENAI_API_KEY", proc.stderr)

    def test_seckit_env_secret_fallback_warning_can_be_suppressed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_bin = Path(tmp) / "fake-seckit"
            fake_bin.write_text(
                "#!/usr/bin/env bash\n"
                "echo 'ERROR: export failed' >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_bin.chmod(0o755)
            script = f"""
                . \"{COMMON_SH}\"
                export LLMOPS_USE_SECKIT=1
                export LLMOPS_SECKIT_BIN=\"{fake_bin}\"
                export LLMOPS_REQUIRED_SECRETS=\"OPENAI_API_KEY\"
                export OPENAI_API_KEY=sk-local
                export LLMOPS_SECRET_FALLBACK_WARN=0
                maybe_load_seckit_env
                maybe_warn_env_secret_fallback
                printf 'ok\n'
            """
            proc = self.run_bash(script)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stderr, "")
            self.assertEqual(proc.stdout.strip(), "ok")

    def test_seckit_export_uses_selected_names_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_bin = Path(tmp) / "fake-seckit"
            args_log = Path(tmp) / "args.log"
            fake_bin.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s\\n' \"$*\" > \"{args_log}\"\n"
                "printf 'export TELEGRAM_BOT_TOKEN=sec-telegram\\n'\n"
                , encoding="utf-8",
            )
            fake_bin.chmod(0o755)
            script = f"""
                . \"{COMMON_SH}\"
                export LLMOPS_USE_SECKIT=1
                export LLMOPS_SECKIT_BIN=\"{fake_bin}\"
                export LLMOPS_SECKIT_NAMES=\"OPENCLAW_GATEWAY_TOKEN,TELEGRAM_BOT_TOKEN\"
                maybe_load_seckit_env
                printf '%s\n' \"$TELEGRAM_BOT_TOKEN\"
            """
            proc = self.run_bash(script)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.strip(), "sec-telegram")
            self.assertIn("--names OPENCLAW_GATEWAY_TOKEN,TELEGRAM_BOT_TOKEN", args_log.read_text(encoding="utf-8"))

    def test_gateway_warns_on_env_secret_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            hermes_home = home / ".hermes"
            invocations = root / "gateway-invocations.log"
            fake_cmd = self._write_fake_gateway_cmd(root)
            fake_seckit = root / "fake-seckit"
            fake_seckit.write_text(
                "#!/usr/bin/env bash\n"
                "echo 'ERROR: export failed' >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_seckit.chmod(0o755)

            proc = self.run_bash(
                f'"{AGENTCTL}" start openclaw',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "HERMES_HOME": str(hermes_home),
                    "LLMOPS_USE_SECKIT": "1",
                    "LLMOPS_SECKIT_BIN": str(fake_seckit),
                    "OPENCLAW_GATEWAY_CMD": str(fake_cmd),
                    "HERMES_GATEWAY_CMD": str(fake_cmd),
                    "FAKE_GATEWAY_INVOCATIONS": str(invocations),
                    "TELEGRAM_BOT_TOKEN": "env-telegram-token",
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Secrets Kit fallback in use", proc.stderr)
            self.assertIn("TELEGRAM_BOT_TOKEN", proc.stderr)
            stop = self.run_bash(f'"{AGENTCTL}" stop openclaw', env={
                "HOME": str(home),
                "LLMOPS_HOME": str(llmops_home),
                "HERMES_HOME": str(hermes_home),
                "LLMOPS_USE_SECKIT": "0",
            })
            self.assertEqual(stop.returncode, 0, stop.stderr)

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

    def test_gateway_launchd_run_openclaw_uses_backend_profile_and_selected_seckit_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            hermes_home = home / ".hermes"
            openclaw_home = home / ".openclaw"
            openclaw_home.mkdir(parents=True)
            (openclaw_home / ".env").write_text(
                "OPENCLAW_GATEWAY_TOKEN=${OPENCLAW_GATEWAY_TOKEN}\n"
                "TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}\n",
                encoding="utf-8",
            )
            args_log = root / "seckit-args.log"
            fake_seckit = root / "fake-seckit"
            fake_seckit.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s\\n' \"$*\" > \"{args_log}\"\n"
                "printf 'export OPENCLAW_GATEWAY_TOKEN=sec-gateway\\n'\n"
                "printf 'export TELEGRAM_BOT_TOKEN=sec-telegram\\n'\n",
                encoding="utf-8",
            )
            fake_seckit.chmod(0o755)
            invocations = root / "launchd-run.log"
            fake_cmd = root / "fake-openclaw"
            fake_cmd.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s|%s|%s\\n' \"$*\" \"${{OPENCLAW_GATEWAY_TOKEN:-}}\" \"${{TELEGRAM_BOT_TOKEN:-}}\" > \"{invocations}\"\n",
                encoding="utf-8",
            )
            fake_cmd.chmod(0o755)

            proc = self.run_bash(
                f'"{AGENTCTL}" launchd-run openclaw',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "HERMES_HOME": str(hermes_home),
                    "OPENCLAW_HOME": str(openclaw_home),
                    "LLMOPS_USE_SECKIT": "1",
                    "LLMOPS_SECKIT_BIN": str(fake_seckit),
                    "OPENCLAW_GATEWAY_CMD": str(fake_cmd),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("gateway run --port 18789|sec-gateway|sec-telegram", invocations.read_text(encoding="utf-8"))
            self.assertIn("--names OPENCLAW_GATEWAY_TOKEN,TELEGRAM_BOT_TOKEN", args_log.read_text(encoding="utf-8"))
            self.assertTrue((llmops_home / "config" / "agents" / "openclaw.env").exists())

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

            start = self.run_bash(f'"{AGENTCTL}" start openclaw', env=base_env)
            self.assertEqual(start.returncode, 0, start.stderr)
            self.assertIn("agentctl[openclaw]: started pid=", start.stdout)

            status = self.run_bash(f'"{AGENTCTL}" status openclaw', env=base_env)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("agentctl[openclaw]: running pid=", status.stdout)
            self.assertIn("agentctl-openclaw.log", status.stdout)

            stop = self.run_bash(f'"{AGENTCTL}" stop openclaw', env=base_env)
            self.assertEqual(stop.returncode, 0, stop.stderr)
            self.assertIn("agentctl-openclaw: stopped pid", stop.stdout)

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

            start = self.run_bash(f'"{AGENTCTL}" start all', env=base_env)
            self.assertEqual(start.returncode, 0, start.stderr)
            self.assertIn("agentctl[openclaw]: started pid=", start.stdout)
            self.assertIn("agentctl[hermes]: started pid=", start.stdout)

            status = self.run_bash(f'"{AGENTCTL}" status all', env=base_env)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("agentctl[openclaw]: running pid=", status.stdout)
            self.assertIn("agentctl[hermes]: running pid=", status.stdout)
            self.assertIn("agentctl-openclaw.log", status.stdout)
            self.assertIn("agentctl-hermes.log", status.stdout)

            pid_dir = llmops_home / "run"
            self.assertTrue((pid_dir / "agentctl-openclaw.pid").exists())
            self.assertTrue((pid_dir / "agentctl-hermes.pid").exists())

            stop = self.run_bash(f'"{AGENTCTL}" stop all', env=base_env)
            self.assertEqual(stop.returncode, 0, stop.stderr)
            self.assertIn("agentctl-openclaw: stopped pid", stop.stdout)
            self.assertIn("agentctl-hermes: stopped pid", stop.stdout)


if __name__ == "__main__":
    unittest.main()
