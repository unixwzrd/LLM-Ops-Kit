#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMON_SH = REPO_ROOT / "scripts/lib/common.sh"
MODELCTL = REPO_ROOT / "scripts/modelctl"
AGENTCTL = REPO_ROOT / "scripts/agentctl"
MODEL_PROXY = REPO_ROOT / "scripts/model-proxy"
TTS_BRIDGE = REPO_ROOT / "scripts/tts-bridge"
DEPLOY_RUNTIME_LINKS = REPO_ROOT / "scripts/deploy-runtime-links.sh"
INSTALL_RUNTIME = REPO_ROOT / "scripts/install-runtime.sh"
LLMOPS = REPO_ROOT / "scripts/llmops"
SETUP_DEPLOY = REPO_ROOT / "scripts/setup-deploy"
STAGE_RUNTIME = REPO_ROOT / "scripts/stage-runtime"
PUSH_RUNTIME = REPO_ROOT / "scripts/push-runtime"
DEPLOY_RUNTIME = REPO_ROOT / "scripts/deploy-runtime"


class ShellRuntimeHelperTests(unittest.TestCase):
    def run_bash(self, script: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        merged = os.environ.copy()
        if env:
            merged.update(env)
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-lc", script],
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

    def test_common_shell_defaults_use_platform_neutral_state_and_config_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            proc = self.run_bash(
                f"""
                . "{COMMON_SH}"
                printf 'config_home=%s\\n' "$LLMOPS_CONFIG_HOME"
                printf 'config_dir=%s\\n' "$LLMOPS_CONFIG_DIR"
                printf 'state_home=%s\\n' "$LLMOPS_STATE_HOME"
                printf 'run_dir=%s\\n' "$LLMOPS_RUN_DIR"
                printf 'log_dir=%s\\n' "$LLMOPS_LOG_DIR"
                printf 'backup_dir=%s\\n' "$LLMOPS_BACKUP_DIR"
                printf 'state_file=%s\\n' "$(state_file_path)"
                """,
                env={"HOME": str(home), "LLMOPS_HOME": str(home / ".llm-ops")},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            expected_config = home / ".config" / "llm-ops"
            expected_state = home / ".local" / "state" / "llm-ops"
            self.assertIn(f"config_home={expected_config}", proc.stdout)
            self.assertIn(f"config_dir={expected_config / 'config'}", proc.stdout)
            self.assertIn(f"state_home={expected_state}", proc.stdout)
            self.assertIn(f"run_dir={expected_state / 'run'}", proc.stdout)
            self.assertIn(f"log_dir={expected_state / 'logs'}", proc.stdout)
            self.assertIn(f"backup_dir={expected_state / 'backups'}", proc.stdout)
            self.assertIn(f"state_file={expected_state / 'runtime-state.env'}", proc.stdout)

    def test_retention_helpers_accept_empty_runtime_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_file = root / "logs" / "service.log"
            backup_dir = root / "backups"
            log_file.parent.mkdir()
            backup_dir.mkdir()
            log_file.touch()
            proc = self.run_bash(
                f"""
                set -u
                . "{COMMON_SH}"
                export LLMOPS_BACKUP_DIR="{backup_dir}"
                prune_rotated_logs "{log_file}"
                prune_runtime_backups
                """
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("unbound variable", proc.stderr)

    def test_load_shell_env_reads_xdg_config_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            config_home = home / ".config" / "llm-ops"
            config_home.mkdir(parents=True)
            (config_home / "config.env").write_text("LLMOPS_TEST_FROM_CONFIG=xdg\n", encoding="utf-8")
            proc = self.run_bash(
                f"""
                . "{COMMON_SH}"
                load_shell_env
                printf '%s\\n' "$LLMOPS_TEST_FROM_CONFIG"
                """,
                env={"HOME": str(home), "LLMOPS_HOME": str(home / ".llm-ops")},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.strip(), "xdg")

    def test_modelctl_seeds_env_override_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            llmops_home = home / ".llm-ops"
            config_dir = home / ".config" / "llm-ops" / "config"
            config_dir.mkdir(parents=True)
            template_dir = llmops_home / "current" / "scripts" / "templates"
            template_dir.mkdir(parents=True)
            (template_dir / "Qwen-3_5-optimized-template.jinja").write_text(
                "{{ messages }}\n",
                encoding="utf-8",
            )
            proc = self.run_bash(
                f'"{MODELCTL}" Qwen3.5 settings',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            seeded_candidates = sorted(config_dir.glob("*.env"))
            self.assertTrue(seeded_candidates, proc.stderr + proc.stdout)
            self.assertIn("copied template config", proc.stderr)

    def test_modelctl_rejects_legacy_sh_override_with_migration_hint(self) -> None:
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
                    "LLMOPS_CONFIG_DIR": str(config_dir),
                },
            )
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertIn("legacy per-model override is no longer loaded", proc.stderr)
            self.assertIn("migrate-config", proc.stderr)
            self.assertFalse((config_dir / "Qwen3.5.env").exists())

    def test_modelctl_template_style_env_override_beats_profile_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            llmops_home = home / ".llm-ops"
            config_dir = llmops_home / "config"
            config_dir.mkdir(parents=True)
            custom_template = Path(tmp) / "custom-template.jinja"
            custom_template.write_text("{{ messages }}\n", encoding="utf-8")
            (config_dir / "Qwen3.5.env").write_text(
                "\n".join(
                    [
                        'MODEL="${MODEL:-/tmp/override-model.gguf}"',
                        'CTX_SIZE="${CTX_SIZE:-12345}"',
                        f'CHAT_TEMPLATE="${{CHAT_TEMPLATE:-{custom_template}}}"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            proc = self.run_bash(
                f'"{MODELCTL}" Qwen3.5 settings',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "LLMOPS_CONFIG_DIR": str(config_dir),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("MODEL=/tmp/override-model.gguf", proc.stdout)
            self.assertIn("CTX_SIZE=12345", proc.stdout)
            self.assertIn(f"CHAT_TEMPLATE={custom_template}", proc.stdout)

    def test_modelctl_external_env_still_beats_template_style_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            llmops_home = home / ".llm-ops"
            config_dir = llmops_home / "config"
            config_dir.mkdir(parents=True)
            custom_template = Path(tmp) / "override-template.jinja"
            custom_template.write_text("{{ messages }}\n", encoding="utf-8")
            external_template = Path(tmp) / "external-template.jinja"
            external_template.write_text("{{ messages }}\n", encoding="utf-8")
            (config_dir / "Qwen3.5.env").write_text(
                "\n".join(
                    [
                        'MODEL="${MODEL:-/tmp/override-model.gguf}"',
                        'CTX_SIZE="${CTX_SIZE:-12345}"',
                        f'CHAT_TEMPLATE="${{CHAT_TEMPLATE:-{custom_template}}}"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            proc = self.run_bash(
                f'"{MODELCTL}" Qwen3.5 settings',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "LLMOPS_CONFIG_DIR": str(config_dir),
                    "MODEL": "/tmp/external-model.gguf",
                    "CTX_SIZE": "777",
                    "CHAT_TEMPLATE": str(external_template),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("MODEL=/tmp/external-model.gguf", proc.stdout)
            self.assertIn("CTX_SIZE=777", proc.stdout)
            self.assertIn(f"CHAT_TEMPLATE={external_template}", proc.stdout)

    def test_modelctl_settings_reports_llama_server_extension_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            llmops_home = home / ".llm-ops"
            config_dir = llmops_home / "config"
            config_dir.mkdir(parents=True)
            (config_dir / "Qwen3.5.env").write_text(
                "\n".join(
                    [
                        "CACHE_PROMPT=1",
                        "CACHE_REUSE=512",
                        f"SLOT_SAVE_PATH={llmops_home}/cache/slots",
                        "SPEC_TYPE=ngram-map",
                        "SPEC_NGRAM_SIZE_N=12",
                        "SPEC_NGRAM_SIZE_M=48",
                        "PERF=1",
                        "FLASH_ATTENTION=1",
                        "NO_CPU_MOE=1",
                        "NO_HOST=1",
                        "USE_CUSTOM_TEMPLATE=0",
                        'EXTRA_FLAGS="--custom-flag value"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            proc = self.run_bash(
                f'"{MODELCTL}" Qwen3.5 settings',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "LLMOPS_CONFIG_DIR": str(config_dir),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("CACHE_PROMPT=1", proc.stdout)
            self.assertIn("CACHE_REUSE=512", proc.stdout)
            self.assertIn(f"SLOT_SAVE_PATH={llmops_home}/cache/slots", proc.stdout)
            self.assertIn("SPEC_TYPE=ngram-map", proc.stdout)
            self.assertIn("SPEC_NGRAM_SIZE_N=12", proc.stdout)
            self.assertIn("SPEC_NGRAM_SIZE_M=48", proc.stdout)
            self.assertIn("PERF=1", proc.stdout)
            self.assertIn("FLASH_ATTENTION=1", proc.stdout)
            self.assertIn("NO_CPU_MOE=1", proc.stdout)
            self.assertIn("NO_HOST=1", proc.stdout)
            self.assertIn("EXTRA_FLAGS=--custom-flag value", proc.stdout)

    def test_modelctl_settings_can_load_json_model_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            config_home = home / ".config" / "llm-ops"
            models_dir = config_home / "models"
            models_dir.mkdir(parents=True)
            (models_dir / "Qwen3.6.json").write_text(
                """
{
  "schema_version": 1,
  "name": "Qwen3.6",
  "type": "llm",
  "model_path": "/models/qwen3.6.gguf",
  "runtime": {
    "host": "127.0.0.1",
    "port": 11999,
    "threads": "10",
    "threads_batch": "10"
  },
  "llama": {
    "ctx_size": 262144,
    "gpu_layers": "all",
    "batch_size": 1024,
    "ubatch_size": 1024,
    "use_mlock": false,
    "use_no_mmap": false,
    "direct_io": false
  },
  "sampling": {
    "temp": 0.7,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 1.5,
    "repeat_penalty": 1.0
  },
  "template": {
    "enabled": false,
    "path": null
  },
  "server": {
    "cache_prompt": true,
    "cache_reuse": 512,
    "slot_save_path": "/state/slots",
    "spec_type": "ngram-map",
    "spec_ngram_size_n": 12,
    "spec_ngram_size_m": 48,
    "perf": true,
    "flash_attention": true,
    "no_cpu_moe": true,
    "no_host": true,
    "extra_flags": []
  },
  "secrets": {
    "required": []
  }
}
""",
                encoding="utf-8",
            )
            proc = self.run_bash(
                f'"{MODELCTL}" Qwen3.6 settings',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(home / ".llm-ops"),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("MODEL_PROFILE=Qwen3.6", proc.stdout)
            self.assertIn("MODEL=/models/qwen3.6.gguf", proc.stdout)
            self.assertIn("HOST=127.0.0.1", proc.stdout)
            self.assertIn("PORT=11999", proc.stdout)
            self.assertIn("CTX_SIZE=262144", proc.stdout)
            self.assertIn("GPU_LAYERS=all", proc.stdout)
            self.assertIn("CACHE_PROMPT=1", proc.stdout)
            self.assertIn("SPEC_TYPE=ngram-map", proc.stdout)

    def test_deploy_runtime_links_heals_identical_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            bin_dir = home / "bin"
            runtime_dir = Path(tmp) / "runtime"
            scripts_dir = runtime_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            bin_dir.mkdir(parents=True)
            source = scripts_dir / "runtime-maintenance"
            source.write_text("#!/usr/bin/env bash\necho maintained\n", encoding="utf-8")
            source.chmod(0o755)
            manifest = runtime_dir / "runtime-links.manifest"
            manifest.write_text("runtime-maintenance|scripts/runtime-maintenance\n", encoding="utf-8")
            target = bin_dir / "runtime-maintenance"
            target.write_text("#!/usr/bin/env bash\necho maintained\n", encoding="utf-8")
            target.chmod(0o755)
            proc = self.run_bash(
                f'"{DEPLOY_RUNTIME_LINKS}"',
                env={
                    "HOME": str(home),
                    "BIN_DIR": str(bin_dir),
                    "RUNTIME_DIR": str(runtime_dir),
                    "MANIFEST_FILE": str(manifest),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("HEALED_REGULAR_FILE:", proc.stdout)
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.resolve(), source.resolve())

    def test_llmops_dispatcher_runs_known_command_from_managed_bin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            managed_bin = Path(tmp) / "managed-bin"
            log_path = Path(tmp) / "modelctl.log"
            managed_bin.mkdir()
            modelctl = managed_bin / "modelctl"
            modelctl.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s\\n' \"$*\" > \"{log_path}\"\n",
                encoding="utf-8",
            )
            modelctl.chmod(0o755)

            proc = self.run_bash(
                f'"{LLMOPS}" modelctl status',
                env={"LLMOPS_BIN_DIR": str(managed_bin)},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(log_path.read_text(encoding="utf-8").strip(), "status")

    def test_llmops_dispatcher_rejects_unknown_command(self) -> None:
        proc = self.run_bash(f'"{LLMOPS}" does-not-exist')
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unknown command: does-not-exist", proc.stderr)

    def test_llmops_dispatcher_help_lists_commands(self) -> None:
        proc = self.run_bash(f'"{LLMOPS}" --help')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Usage: llmops <command> [args...]", proc.stdout)
        self.assertIn("modelctl", proc.stdout)

    def test_install_runtime_writes_idempotent_public_path_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            home = Path(tmp) / "home"
            install_base = home / ".local" / "llm-ops"
            managed_bin = install_base / "bin"
            public_bin = home / ".local" / "bin"
            shell_profile = home / ".bash_profile"
            root.mkdir()
            proc = self.run_bash(
                f'rsync -a --exclude .git "{REPO_ROOT}/" "{root}/" && '
                f'"{root / "scripts" / "install-runtime.sh"}" '
                f'--source "{root}" '
                f'--prefix "{install_base}" '
                f'--bin-dir "{managed_bin}" '
                f'--public-bin-dir "{public_bin}" '
                f'--shell-profile "{shell_profile}"',
                env={"HOME": str(home)},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((public_bin / "llmops").is_symlink())
            self.assertTrue((managed_bin / "modelctl").is_symlink())
            profile_text = shell_profile.read_text(encoding="utf-8")
            self.assertEqual(profile_text.count("# >>> llm-ops path >>>"), 1)
            self.assertIn(f'export PATH="{public_bin}:$PATH"', profile_text)

            second = self.run_bash(
                f'"{root / "scripts" / "install-runtime.sh"}" '
                f'--source "{root}" '
                f'--prefix "{install_base}" '
                f'--bin-dir "{managed_bin}" '
                f'--public-bin-dir "{public_bin}" '
                f'--shell-profile "{shell_profile}"',
                env={"HOME": str(home)},
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            profile_text = shell_profile.read_text(encoding="utf-8")
            self.assertEqual(profile_text.count("# >>> llm-ops path >>>"), 1)

    def test_install_runtime_stores_upgrade_backup_under_state_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            home = Path(tmp) / "home"
            install_base = home / ".local" / "llm-ops"
            state_home = home / ".local" / "state" / "llm-ops"
            root.mkdir()
            copy = self.run_bash(f'rsync -a --exclude .git "{REPO_ROOT}/" "{root}/"')
            self.assertEqual(copy.returncode, 0, copy.stderr)

            command = (
                f'"{root / "scripts" / "install-runtime.sh"}" '
                f'--source "{root}" --prefix "{install_base}" --no-shell-profile'
            )
            env = {
                "HOME": str(home),
                "LLMOPS_STATE_HOME": str(state_home),
                "LLMOPS_RUNTIME_VENV_PACKAGES": "",
            }
            first = self.run_bash(command, env=env)
            self.assertEqual(first.returncode, 0, first.stderr)
            (install_base / "current" / "upgrade-marker").write_text("old\n", encoding="utf-8")

            second = self.run_bash(command, env=env)
            self.assertEqual(second.returncode, 0, second.stderr)
            backups = list((state_home / "backups").glob("*"))
            self.assertEqual(len(backups), 1)
            self.assertTrue((backups[0] / "upgrade-marker").exists())
            self.assertFalse((install_base / "backups").exists())

    def test_install_runtime_restores_previous_runtime_after_failed_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            home = Path(tmp) / "home"
            install_base = home / ".local" / "llm-ops"
            state_home = home / ".local" / "state" / "llm-ops"
            state_file = state_home / "runtime-state.env"
            root.mkdir()
            copy = self.run_bash(f'rsync -a --exclude .git "{REPO_ROOT}/" "{root}/"')
            self.assertEqual(copy.returncode, 0, copy.stderr)

            command = (
                f'"{root / "scripts" / "install-runtime.sh"}" '
                f'--source "{root}" --prefix "{install_base}" --no-shell-profile'
            )
            env = {
                "HOME": str(home),
                "LLMOPS_STATE_HOME": str(state_home),
                "LLMOPS_RUNTIME_VENV_PACKAGES": "",
            }
            first = self.run_bash(command, env=env)
            self.assertEqual(first.returncode, 0, first.stderr)
            marker = install_base / "current" / "upgrade-marker"
            marker.write_text("known-good\n", encoding="utf-8")
            previous_state = state_file.read_text(encoding="utf-8")

            deploy = root / "scripts" / "deploy-runtime-links.sh"
            deploy.write_text("#!/usr/bin/env bash\nexit 19\n", encoding="utf-8")
            deploy.chmod(0o755)

            failed = self.run_bash(command, env=env)
            self.assertEqual(failed.returncode, 19)
            self.assertTrue(marker.exists())
            self.assertEqual(marker.read_text(encoding="utf-8"), "known-good\n")
            self.assertEqual(state_file.read_text(encoding="utf-8"), previous_state)
            self.assertTrue((home / ".local" / "bin" / "llmops").is_symlink())

    def test_failed_fresh_install_removes_partial_runtime_and_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            home = Path(tmp) / "home"
            install_base = home / ".local" / "llm-ops"
            root.mkdir()
            copy = self.run_bash(f'rsync -a --exclude .git "{REPO_ROOT}/" "{root}/"')
            self.assertEqual(copy.returncode, 0, copy.stderr)
            verify = root / "scripts" / "verify-runtime-links.sh"
            verify.write_text("#!/usr/bin/env bash\nexit 23\n", encoding="utf-8")
            verify.chmod(0o755)

            failed = self.run_bash(
                f'"{root / "scripts" / "install-runtime.sh"}" '
                f'--source "{root}" --prefix "{install_base}" --no-shell-profile',
                env={"HOME": str(home), "LLMOPS_RUNTIME_VENV_PACKAGES": ""},
            )
            self.assertEqual(failed.returncode, 23)
            self.assertFalse((install_base / "current").exists())
            self.assertFalse((home / ".local" / "bin" / "llmops").exists())
            managed_bin = install_base / "bin"
            self.assertFalse(any(managed_bin.iterdir()))

    def test_uninstall_recovers_when_runtime_manifest_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            home = Path(tmp) / "home"
            install_base = home / ".local" / "llm-ops"
            state_home = home / ".local" / "state" / "llm-ops"
            root.mkdir()
            copy = self.run_bash(f'rsync -a --exclude .git "{REPO_ROOT}/" "{root}/"')
            self.assertEqual(copy.returncode, 0, copy.stderr)
            env = {
                "HOME": str(home),
                "LLMOPS_STATE_HOME": str(state_home),
                "LLMOPS_RUNTIME_VENV_PACKAGES": "",
            }
            installed = self.run_bash(
                f'"{root / "scripts" / "install-runtime.sh"}" '
                f'--source "{root}" --prefix "{install_base}" --no-shell-profile',
                env=env,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            (install_base / "current" / "scripts" / "runtime-links.manifest").unlink()

            removed = self.run_bash(
                f'"{root / "scripts" / "uninstall-runtime.sh"}" --prefix "{install_base}"',
                env=env,
            )
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertFalse((install_base / "current").exists())
            self.assertFalse((home / ".local" / "bin" / "llmops").exists())
            self.assertFalse((state_home / "runtime-state.env").exists())
            self.assertFalse(any((install_base / "bin").iterdir()))

    def test_setup_deploy_writes_named_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = Path(tmp) / "home"
            llmops_home = home / ".llm-ops"
            answers = "\n".join(
                [
                    "agent-user",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "y",
                    "git+https://github.com/unixwzrd/Secrets-Kit.git",
                    "",
                ]
            )
            proc = self.run_bash(
                f'printf "%s\n" "example-host\n\n{answers}" | "{SETUP_DEPLOY}" --config-name demo',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "LLMOPS_ROOT": str(root),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            config_path = root / "stage" / "deploy_config" / "demo.env"
            self.assertTrue(config_path.exists())
            config_text = config_path.read_text(encoding="utf-8")
            self.assertIn('LLMOPS_DEPLOY_CONFIG_NAME=demo', config_text)
            self.assertIn('LLMOPS_DEPLOY_HOSTS=example-host', config_text)
            self.assertIn('LLMOPS_DEPLOY_BASE_DIR=/Users/agent-user', config_text)
            self.assertIn('LLMOPS_DEPLOY_INSTALL_PREFIX=/Users/agent-user/.local/llm-ops', config_text)
            self.assertIn('LLMOPS_DEPLOY_BIN_DIR=/Users/agent-user/.local/llm-ops/bin', config_text)
            self.assertIn('LLMOPS_DEPLOY_PUBLIC_BIN_DIR=/Users/agent-user/.local/bin', config_text)
            self.assertIn('LLMOPS_DEPLOY_STATE_FILE=/Users/agent-user/.local/state/llm-ops/runtime-state.env', config_text)
            self.assertIn('LLMOPS_DEPLOY_INSTALL_SECRETS_KIT=1', config_text)

    def test_stage_runtime_builds_trimmed_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            stage_dir = Path(tmp) / "visible-stage"
            config_dir = root / "stage" / "deploy_config"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "demo.env"
            config_path.write_text(
                "\n".join(
                    [
                        'LLMOPS_DEPLOY_CONFIG_NAME="demo"',
                        'LLMOPS_DEPLOY_HOSTS="fake-host"',
                        'LLMOPS_DEPLOY_USER="agent-user"',
                        'LLMOPS_DEPLOY_BASE_DIR="~"',
                        'LLMOPS_DEPLOY_INSTALL_PREFIX="~/.local/llm-ops"',
                        'LLMOPS_DEPLOY_BIN_DIR="~/.local/llm-ops/bin"',
                        'LLMOPS_DEPLOY_PUBLIC_BIN_DIR="~/.local/bin"',
                        'LLMOPS_DEPLOY_STATE_FILE="~/.local/state/llm-ops/runtime-state.env"',
                        'LLMOPS_DEPLOY_VENV_PATH="~/.local/llm-ops/venv"',
                        'LLMOPS_DEPLOY_INSTALL_SECRETS_KIT="0"',
                        'LLMOPS_DEPLOY_SECRETS_KIT_SOURCE="git+https://github.com/unixwzrd/Secrets-Kit.git"',
                        'LLMOPS_DEPLOY_SSH_KEY_PATH=""',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            proc = self.run_bash(
                f'"{STAGE_RUNTIME}" --config-file "{config_path}" --stage-dir "{stage_dir}" --force',
                env={
                    "HOME": str(home),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            staged_install = stage_dir / Path(str(home).lstrip("/")) / ".local" / "llm-ops" / "current"
            staged_bin = stage_dir / Path(str(home).lstrip("/")) / ".local" / "llm-ops" / "bin"
            staged_public_bin = stage_dir / Path(str(home).lstrip("/")) / ".local" / "bin"
            self.assertTrue((staged_install / "scripts" / "agentctl").exists())
            self.assertTrue((staged_install / "scripts" / "runtime-links.manifest").exists())
            self.assertTrue(staged_bin.is_dir())
            self.assertTrue((staged_public_bin / "llmops").is_symlink())
            self.assertTrue((stage_dir / "metadata" / "build-info.json").exists())
            self.assertFalse((staged_install / "scripts" / "tests").exists())
            self.assertFalse((stage_dir / "docs").exists())

    def test_push_runtime_syncs_virtual_root_and_validates_remote_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            config_dir = root / "stage" / "deploy_config"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "demo.env"
            config_path.write_text(
                "\n".join(
                    [
                        'LLMOPS_DEPLOY_CONFIG_NAME="demo"',
                        'LLMOPS_DEPLOY_HOSTS="fake-host"',
                        'LLMOPS_DEPLOY_USER="agent-user"',
                        'LLMOPS_DEPLOY_BASE_DIR="~"',
                        'LLMOPS_DEPLOY_INSTALL_PREFIX="~/.local/llm-ops"',
                        'LLMOPS_DEPLOY_BIN_DIR="~/.local/llm-ops/bin"',
                        'LLMOPS_DEPLOY_PUBLIC_BIN_DIR="~/.local/bin"',
                        'LLMOPS_DEPLOY_STATE_FILE="~/.local/state/llm-ops/runtime-state.env"',
                        'LLMOPS_DEPLOY_VENV_PATH="~/.local/llm-ops/venv"',
                        'LLMOPS_DEPLOY_INSTALL_SECRETS_KIT="0"',
                        'LLMOPS_DEPLOY_SECRETS_KIT_SOURCE="git+https://github.com/unixwzrd/Secrets-Kit.git"',
                        'LLMOPS_DEPLOY_SSH_KEY_PATH=""',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            stage_dir = root / "stage" / "demo"

            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            remote_home = root / "remote-home"
            remote_home.mkdir()
            ssh_log = root / "ssh.log"
            rsync_log = root / "rsync.log"

            (fake_bin / "ssh").write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "log_file=\"${FAKE_SSH_LOG:?}\"\n"
                "remote_home=\"${FAKE_REMOTE_HOME:?}\"\n"
                "while [[ $# -gt 0 ]]; do\n"
                "  case \"$1\" in\n"
                "    -i|-o|-p) shift 2 ;;\n"
                "    -*) shift ;;\n"
                "    *@*) target=\"$1\"; shift; break ;;\n"
                "    *) break ;;\n"
                "  esac\n"
                "done\n"
                "printf '%s :: %s\\n' \"${target:-}\" \"$*\" >> \"$log_file\"\n"
                "HOME=\"$remote_home\" \"$@\"\n",
                encoding="utf-8",
            )
            (fake_bin / "ssh").chmod(0o755)

            (fake_bin / "rsync").write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "log_file=\"${FAKE_RSYNC_LOG:?}\"\n"
                "remote_home=\"${FAKE_REMOTE_HOME:?}\"\n"
                "delete_mode=0\n"
                "args=()\n"
                "while [[ $# -gt 0 ]]; do\n"
                "  case \"$1\" in\n"
                "    -e) shift 2 ;;\n"
                "    --delete) delete_mode=1; shift ;;\n"
                "    -*) shift ;;\n"
                "    *) args+=(\"$1\"); shift ;;\n"
                "  esac\n"
                "done\n"
                "src=\"${args[0]}\"\n"
                "dest=\"${args[1]}\"\n"
                "remote_path=\"${dest#*:}\"\n"
                "case \"$remote_path\" in\n"
                "  '~') remote_path=\"$remote_home\" ;;\n"
                "  '~/'*) remote_path=\"$remote_home/${remote_path#~/}\" ;;\n"
                "esac\n"
                "if [[ -f \"$src\" ]]; then\n"
                "  mkdir -p \"$(dirname \"$remote_path\")\"\n"
                "  cp \"$src\" \"$remote_path\"\n"
                "  printf '%s -> %s\\n' \"$src\" \"$remote_path\" >> \"$log_file\"\n"
                "  exit 0\n"
                "fi\n"
                "mkdir -p \"$remote_path\"\n"
                "if [[ \"$delete_mode\" == \"1\" && -d \"$remote_path\" ]]; then\n"
                "  find \"$remote_path\" -mindepth 1 -maxdepth 1 -exec rm -rf {} +\n"
                "fi\n"
                "cp -R \"$src\"/. \"$remote_path\"/\n"
                "printf '%s -> %s\\n' \"$src\" \"$remote_path\" >> \"$log_file\"\n",
                encoding="utf-8",
            )
            (fake_bin / "rsync").chmod(0o755)

            proc = self.run_bash(
                f'"{PUSH_RUNTIME}" --config-file "{config_path}" --stage-dir "{stage_dir}"',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "LLMOPS_ROOT": str(REPO_ROOT),
                    "LLMOPS_RUNTIME_VENV_PACKAGES": "",
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "FAKE_REMOTE_HOME": str(remote_home),
                    "FAKE_SSH_LOG": str(ssh_log),
                    "FAKE_RSYNC_LOG": str(rsync_log),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((remote_home / ".local" / "llm-ops" / "current" / "scripts" / "agentctl").exists())
            self.assertTrue((remote_home / ".local" / "state" / "llm-ops" / "runtime-state.env").exists())
            self.assertTrue((remote_home / ".local" / "llm-ops" / "venv" / "bin" / "python").exists())
            self.assertTrue((remote_home / ".local" / "llm-ops" / "bin" / "agentctl").is_symlink())
            self.assertTrue((remote_home / ".local" / "bin" / "llmops").is_symlink())
            self.assertIn(str(remote_home / ".local" / "bin"), (remote_home / ".bash_profile").read_text(encoding="utf-8"))
            self.assertTrue(ssh_log.exists())
            self.assertTrue(rsync_log.exists())

    def test_deploy_runtime_uses_named_config_and_confirmation_bypass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            config_dir = root / "stage" / "deploy_config"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "default.env"
            config_path.write_text(
                "\n".join(
                    [
                        'LLMOPS_DEPLOY_CONFIG_NAME="default"',
                        'LLMOPS_DEPLOY_HOSTS="fake-host"',
                        'LLMOPS_DEPLOY_USER="agent-user"',
                        'LLMOPS_DEPLOY_BASE_DIR="~"',
                        'LLMOPS_DEPLOY_INSTALL_PREFIX="~/.local/llm-ops"',
                        'LLMOPS_DEPLOY_BIN_DIR="~/.local/llm-ops/bin"',
                        'LLMOPS_DEPLOY_PUBLIC_BIN_DIR="~/.local/bin"',
                        'LLMOPS_DEPLOY_STATE_FILE="~/.local/state/llm-ops/runtime-state.env"',
                        'LLMOPS_DEPLOY_VENV_PATH="~/.local/llm-ops/venv"',
                        'LLMOPS_DEPLOY_INSTALL_SECRETS_KIT="0"',
                        'LLMOPS_DEPLOY_SECRETS_KIT_SOURCE="git+https://github.com/unixwzrd/Secrets-Kit.git"',
                        'LLMOPS_DEPLOY_SSH_KEY_PATH=""',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            stage_dir = root / "stage"

            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            remote_home = root / "remote-home"
            remote_home.mkdir()
            (fake_bin / "ssh").write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "remote_home=\"${FAKE_REMOTE_HOME:?}\"\n"
                "while [[ $# -gt 0 ]]; do\n"
                "  case \"$1\" in\n"
                "    -i|-o|-p) shift 2 ;;\n"
                "    -*) shift ;;\n"
                "    *@*) shift; break ;;\n"
                "    *) break ;;\n"
                "  esac\n"
                "done\n"
                "HOME=\"$remote_home\" \"$@\"\n",
                encoding="utf-8",
            )
            (fake_bin / "ssh").chmod(0o755)
            (fake_bin / "rsync").write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "remote_home=\"${FAKE_REMOTE_HOME:?}\"\n"
                "args=()\n"
                "while [[ $# -gt 0 ]]; do\n"
                "  case \"$1\" in\n"
                "    -e) shift 2 ;;\n"
                "    --delete) shift ;;\n"
                "    -*) shift ;;\n"
                "    *) args+=(\"$1\"); shift ;;\n"
                "  esac\n"
                "done\n"
                "src=\"${args[0]}\"\n"
                "dest=\"${args[1]}\"\n"
                "remote_path=\"${dest#*:}\"\n"
                "case \"$remote_path\" in\n"
                "  '~') remote_path=\"$remote_home\" ;;\n"
                "  '~/'*) remote_path=\"$remote_home/${remote_path#~/}\" ;;\n"
                "esac\n"
                "if [[ -f \"$src\" ]]; then\n"
                "  mkdir -p \"$(dirname \"$remote_path\")\"\n"
                "  cp \"$src\" \"$remote_path\"\n"
                "  exit 0\n"
                "fi\n"
                "mkdir -p \"$remote_path\"\n"
                "cp -R \"$src\"/. \"$remote_path\"/\n",
                encoding="utf-8",
            )
            (fake_bin / "rsync").chmod(0o755)

            proc = self.run_bash(
                f'"{DEPLOY_RUNTIME}" -y --dry-run --config-file "{config_path}" --stage-dir "{stage_dir}"',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "LLMOPS_ROOT": str(root),
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "FAKE_REMOTE_HOME": str(remote_home),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Deployment plan", proc.stdout)
            self.assertTrue(config_path.exists())
            self.assertTrue((stage_dir / "default" / "metadata" / "build-info.json").exists())

    def test_agentctl_launchd_run_openclaw_uses_seckit_run_parent_injection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            llmops_home = home / ".llm-ops"
            openclaw_home = home / ".openclaw"
            config_dir = home / ".config" / "llm-ops" / "config" / "agents"
            config_dir.mkdir(parents=True)
            openclaw_home.mkdir(parents=True)
            (openclaw_home / ".env").write_text("OPENAI_API_KEY=from-dotenv\n", encoding="utf-8")

            seckit_log = Path(tmp) / "seckit.log"
            seckit_env = Path(tmp) / "seckit.env"
            openclaw_log = Path(tmp) / "openclaw.log"
            openclaw_env = Path(tmp) / "openclaw.env"

            fake_openclaw = Path(tmp) / "fake-openclaw"
            fake_openclaw.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" > \"" + str(openclaw_log) + "\"\n"
                "printf 'OPENAI_API_KEY=%s\\n' \"${OPENAI_API_KEY:-}\" > \"" + str(openclaw_env) + "\"\n",
                encoding="utf-8",
            )
            fake_openclaw.chmod(0o755)

            fake_seckit = Path(tmp) / "fake-seckit"
            fake_seckit.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" > \"" + str(seckit_log) + "\"\n"
                "printf 'OPENAI_API_KEY=%s\\n' \"${OPENAI_API_KEY:-}\" > \"" + str(seckit_env) + "\"\n"
                "export OPENAI_API_KEY=from-seckit\n"
                "shift\n"
                "while [[ \"$1\" != \"--\" ]]; do shift; done\n"
                "shift\n"
                "exec \"$@\"\n",
                encoding="utf-8",
            )
            fake_seckit.chmod(0o755)

            proc = self.run_bash(
                f'"{AGENTCTL}" launchd-run openclaw',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "OPENCLAW_HOME": str(openclaw_home),
                    "OPENCLAW_GATEWAY_CMD": str(fake_openclaw),
                    "LLMOPS_USE_SECKIT": "1",
                    "LLMOPS_SECKIT_BIN": str(fake_seckit),
                    "LLMOPS_SECKIT_ACCOUNT": "miafour",
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(seckit_env.read_text(encoding="utf-8").strip(), "OPENAI_API_KEY=")
            self.assertEqual(openclaw_env.read_text(encoding="utf-8").strip(), "OPENAI_API_KEY=from-seckit")

            seckit_args = seckit_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                seckit_args[:7],
                [
                    "run",
                    "--service",
                    "openclaw",
                    "--account",
                    "miafour",
                    "--names",
                    "OPENCLAW_GATEWAY_TOKEN,TELEGRAM_BOT_TOKEN,OPENAI_API_KEY,HUGGINGFACE_API_KEY,LOCAL_EMBEDDING_API_KEY,BRAVE_SEARCH_API_KEY,ELEVENLABS_API_KEY,SAG_API_KEY",
                ],
            )
            self.assertEqual(seckit_args[7:], ["--", str(fake_openclaw), "gateway", "run", "--port", "18789"])
            self.assertEqual(openclaw_log.read_text(encoding="utf-8").splitlines(), ["gateway", "run", "--port", "18789"])

    def test_agentctl_launchd_run_openclaw_without_seckit_runs_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            llmops_home = home / ".llm-ops"
            openclaw_home = home / ".openclaw"
            openclaw_home.mkdir(parents=True)
            launch_log = Path(tmp) / "openclaw.log"

            fake_openclaw = Path(tmp) / "fake-openclaw"
            fake_openclaw.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" > \"" + str(launch_log) + "\"\n",
                encoding="utf-8",
            )
            fake_openclaw.chmod(0o755)

            proc = self.run_bash(
                f'"{AGENTCTL}" launchd-run openclaw',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "OPENCLAW_HOME": str(openclaw_home),
                    "OPENCLAW_GATEWAY_CMD": str(fake_openclaw),
                    "LLMOPS_USE_SECKIT": "0",
                    "LLMOPS_SECKIT_BIN": str(Path(tmp) / "missing-seckit"),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(launch_log.read_text(encoding="utf-8").splitlines(), ["gateway", "run", "--port", "18789"])

    def test_agentctl_exec_runs_backend_command_with_runtime_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            hermes_home = home / ".hermes"
            args_log = root / "args.log"
            token_log = root / "token.log"
            telegram_log = root / "telegram.log"
            fake_cmd = root / "fake-openclaw"
            fake_cmd.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s\\n' \"$*\" > \"{args_log}\"\n"
                f"printf '%s\\n' \"${{OPENCLAW_GATEWAY_TOKEN-}}\" > \"{token_log}\"\n"
                f"printf '%s\\n' \"${{TELEGRAM_BOT_TOKEN-}}\" > \"{telegram_log}\"\n",
                encoding="utf-8",
            )
            fake_cmd.chmod(0o755)
            proc = self.run_bash(
                f'"{AGENTCTL}" exec openclaw status --json',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "HERMES_HOME": str(hermes_home),
                    "OPENCLAW_GATEWAY_CMD": str(fake_cmd),
                    "OPENCLAW_GATEWAY_TOKEN": "env-openclaw",
                    "TELEGRAM_BOT_TOKEN": "env-telegram",
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(args_log.read_text(encoding="utf-8").strip(), "status --json")
            self.assertEqual(token_log.read_text(encoding="utf-8").strip(), "env-openclaw")
            self.assertEqual(telegram_log.read_text(encoding="utf-8").strip(), "env-telegram")

    def test_agentctl_exec_can_load_json_agent_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            config_home = home / ".config" / "llm-ops"
            agents_dir = config_home / "agents"
            agents_dir.mkdir(parents=True)
            fake_cmd = root / "fake-openclaw"
            args_log = root / "args.log"
            fake_cmd.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s\\n' \"$*\" > \"{args_log}\"\n"
                "printf 'ok\\n'\n",
                encoding="utf-8",
            )
            fake_cmd.chmod(0o755)
            (agents_dir / "openclaw.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "openclaw",
                        "env": {
                            "OPENCLAW_GATEWAY_CMD": str(fake_cmd),
                            "LLMOPS_GATEWAY_PORT": "18888",
                            "LLMOPS_AGENT_SECKIT_NAMES": "",
                        },
                    }
                ),
                encoding="utf-8",
            )
            proc = self.run_bash(
                f'"{AGENTCTL}" exec openclaw status',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "LLMOPS_CONFIG_HOME": str(config_home),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.strip(), "ok")
            self.assertEqual(args_log.read_text(encoding="utf-8").strip(), "status")

    def test_agentctl_rejects_legacy_sh_override_with_migration_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            agents_dir = llmops_home / "config" / "agents"
            agents_dir.mkdir(parents=True)
            (agents_dir / "openclaw.sh").write_text("LLMOPS_GATEWAY_PORT=19999\n", encoding="utf-8")
            proc = self.run_bash(
                f'"{AGENTCTL}" exec openclaw status',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "LLMOPS_CONFIG_DIR": str(llmops_home / "config"),
                },
            )
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertIn("legacy per-backend override is no longer loaded", proc.stderr)
            self.assertIn("migrate-config", proc.stderr)

    def test_model_proxy_status_can_load_json_service_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            config_home = home / ".config" / "llm-ops"
            services_dir = config_home / "services"
            services_dir.mkdir(parents=True)
            (services_dir / "model-proxy.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "model-proxy",
                        "runtime": {
                            "upstream_host": "10.0.0.5",
                            "upstream_port": 11434,
                            "listen_host": "127.0.0.1",
                            "listen_port": 11999,
                        },
                        "logging": {"rotate_seconds": 123, "rotate_keep": 4},
                    }
                ),
                encoding="utf-8",
            )
            proc = self.run_bash(
                f'"{MODEL_PROXY}" status',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "LLMOPS_CONFIG_HOME": str(config_home),
                },
            )
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertIn("log_rotate_seconds=123", proc.stdout)
            self.assertIn("log_rotate_keep=4", proc.stdout)

    def test_modelctl_preserves_profile_case_and_does_not_seed_json_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_home = root / "config"
            models_dir = config_home / "models"
            models_dir.mkdir(parents=True)
            model_path = root / "model.gguf"
            model_path.touch()
            (models_dir / "Qwen3.6.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "Qwen3.6",
                        "type": "llm",
                        "env": {
                            "MODEL_TYPE": "llm",
                            "MODEL_PROFILE": "Qwen3_6",
                            "MODEL": str(model_path),
                            "HOST": "127.0.0.1",
                            "PORT": "11434",
                            "THREADS": "8",
                            "THREADS_BATCH": "8",
                            "CTX_SIZE": "8192",
                            "GPU_LAYERS": "99",
                            "BATCH_SIZE": "512",
                            "UBATCH_SIZE": "512",
                            "USE_CUSTOM_TEMPLATE": "0",
                        },
                    }
                ),
                encoding="utf-8",
            )
            proc = self.run_bash(
                f'"{MODELCTL}" Qwen3.6 settings',
                env={
                    "HOME": str(root / "home"),
                    "LLMOPS_HOME": str(root / "llm-ops"),
                    "LLMOPS_CONFIG_HOME": str(config_home),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("modelctl settings (Qwen3.6)", proc.stdout)
            self.assertFalse((config_home / "config" / "Qwen3.6.env").exists())

            proc = self.run_bash(
                f'"{MODELCTL}" list',
                env={
                    "HOME": str(root / "home"),
                    "LLMOPS_HOME": str(root / "llm-ops"),
                    "LLMOPS_CONFIG_HOME": str(config_home),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Qwen3.6|llm", proc.stdout.splitlines())
            self.assertNotIn("No such file or directory", proc.stderr)

    def test_modelctl_start_handles_empty_optional_flags_and_rejects_early_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            config_home = root / "config"
            state_home = root / "state"
            models_dir = config_home / "models"
            models_dir.mkdir(parents=True)
            model_path = root / "model.gguf"
            model_path.touch()
            (models_dir / "Qwen3.6.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "Qwen3.6",
                        "type": "llm",
                        "env": {
                            "MODEL_TYPE": "llm",
                            "MODEL_PROFILE": "Qwen3_6",
                            "MODEL": str(model_path),
                            "HOST": "127.0.0.1",
                            "PORT": "11999",
                            "THREADS": "2",
                            "THREADS_BATCH": "2",
                            "CTX_SIZE": "512",
                            "GPU_LAYERS": "0",
                            "BATCH_SIZE": "32",
                            "UBATCH_SIZE": "32",
                            "USE_CUSTOM_TEMPLATE": "0",
                            "USE_NO_WEBUI": "0",
                        },
                    }
                ),
                encoding="utf-8",
            )
            fake_server = root / "fake-llama-server"
            fake_server.write_text(
                "#!/usr/bin/env bash\n"
                "while :; do sleep 1; done\n",
                encoding="utf-8",
            )
            fake_server.chmod(0o755)
            env = {
                "HOME": str(home),
                "LLMOPS_HOME": str(root / "llm-ops"),
                "LLMOPS_CONFIG_HOME": str(config_home),
                "LLMOPS_STATE_HOME": str(state_home),
                "LLAMA_SERVER_BIN": str(fake_server),
            }
            proc = self.run_bash(
                f'"{MODELCTL}" Qwen3.6 start; rc=$?; "{MODELCTL}" Qwen3.6 stop >/dev/null 2>&1 || true; exit "$rc"',
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Started llama-Qwen3_6", proc.stdout)
            self.assertNotIn("unbound variable", proc.stderr)

            fake_server.write_text("#!/usr/bin/env bash\nexit 17\n", encoding="utf-8")
            proc = self.run_bash(f'"{MODELCTL}" Qwen3.6 start', env=env)
            self.assertNotEqual(proc.returncode, 0)
            self.assertNotIn("Started llama-Qwen3_6", proc.stdout)
            self.assertIn("process exited during startup", proc.stderr)
            self.assertFalse((state_home / "run" / "llama-Qwen3_6.pid").exists())
            self.assertFalse((state_home / "run" / "llama-Qwen3_6.state").exists())

    def test_model_proxy_stop_accepts_no_optional_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            proc = self.run_bash(
                f'"{MODEL_PROXY}" stop',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(root / "llm-ops"),
                    "LLMOPS_CONFIG_HOME": str(root / "config"),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("unbound variable", proc.stderr)

    def test_model_proxy_start_accepts_json_config_without_cli_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            config_home = root / "config"
            services_dir = config_home / "services"
            services_dir.mkdir(parents=True)
            args_log = root / "tap-args.log"
            fake_tap = root / "fake-model-proxy-tap"
            fake_tap.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s\\n' \"$@\" > \"{args_log}\"\n"
                "while :; do sleep 1; done\n",
                encoding="utf-8",
            )
            fake_tap.chmod(0o755)
            (services_dir / "model-proxy.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "model-proxy",
                        "runtime": {
                            "upstream_host": "10.0.0.5",
                            "upstream_port": 11434,
                            "listen_host": "127.0.0.1",
                            "listen_port": 11999,
                        },
                    }
                ),
                encoding="utf-8",
            )
            proc = self.run_bash(
                f'"{MODEL_PROXY}" start; rc=$?; "{MODEL_PROXY}" stop --force; exit "$rc"',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(root / "llm-ops"),
                    "LLMOPS_CONFIG_HOME": str(config_home),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                    "MODEL_PROXY_TAP_BIN": str(fake_tap),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("unbound variable", proc.stderr)
            self.assertIn("--upstream", args_log.read_text(encoding="utf-8").splitlines())

    def test_tts_bridge_status_can_load_json_service_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            config_home = home / ".config" / "llm-ops"
            services_dir = config_home / "services"
            services_dir.mkdir(parents=True)
            (services_dir / "tts-bridge.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "tts-bridge",
                        "runtime": {
                            "host": "127.0.0.1",
                            "port": 11998,
                            "upstream_base": "http://10.0.0.5:11434/v1",
                        },
                        "paths": {
                            "model": "/models/tts",
                            "config_dir": "/config/tts",
                            "samples_dir": "/samples",
                        },
                        "logging": {"rotate_seconds": 456, "rotate_keep": 3},
                    }
                ),
                encoding="utf-8",
            )
            proc = self.run_bash(
                f'"{TTS_BRIDGE}" status',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "LLMOPS_CONFIG_HOME": str(config_home),
                },
            )
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertIn("listen=http://127.0.0.1:11998/health", proc.stdout)
            self.assertIn("upstream=http://10.0.0.5:11434/v1", proc.stdout)
            self.assertIn("log_rotate_seconds=456", proc.stdout)

    def test_tts_bridge_start_reports_bridge_pid_not_marktime_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args_log = root / "tts-bridge-args.log"
            fake_python = root / "fake-python"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" > \"$FAKE_TTS_BRIDGE_ARGS\"\n"
                "while :; do sleep 1; done\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            proc = self.run_bash(
                f"""
                output=$("{TTS_BRIDGE}" start)
                pid=$(cat "$LLMOPS_STATE_HOME/run/tts-bridge.pid")
                for _ in 1 2 3 4 5 6 7 8 9 10; do
                    [[ -f "$FAKE_TTS_BRIDGE_ARGS" ]] && break
                    sleep 0.1
                done
                "{TTS_BRIDGE}" stop >/dev/null
                printf '%s\\nexpected_pid=%s\\n' "$output" "$pid"
                """,
                env={
                    "HOME": str(root / "home"),
                    "LLMOPS_HOME": str(root / "llm-ops"),
                    "LLMOPS_CONFIG_HOME": str(root / "config"),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                    "TTS_BRIDGE_UPSTREAM_BASE": "http://127.0.0.1:65530/v1",
                    "TTS_BRIDGE_PORT": "65531",
                    "TTS_BRIDGE_PYTHON_BIN": str(fake_python),
                    "FAKE_TTS_BRIDGE_ARGS": str(args_log),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            lines = proc.stdout.splitlines()
            reported = next(line for line in lines if line.startswith("Started tts-bridge pid="))
            expected = next(line for line in lines if line.startswith("expected_pid="))
            self.assertIn(f"pid={expected.split('=', 1)[1]} ", reported)
            args = args_log.read_text(encoding="utf-8").splitlines()
            model_index = args.index("--model") + 1
            self.assertEqual(
                args[model_index],
                str(root / "home" / "LLM_Repository" / "TTS" / "Qwen3-TTS-12Hz-0.6B-Base-8bit"),
            )

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

    def _write_fake_launchctl(self, root: Path) -> tuple[Path, Path, Path]:
        script = root / "fake-launchctl"
        log_path = root / "launchctl.log"
        state_dir = root / "launchctl-state"
        script.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "log_file=\"${FAKE_LAUNCHCTL_LOG:?}\"\n"
            "state_dir=\"${FAKE_LAUNCHCTL_STATE_DIR:?}\"\n"
            "mkdir -p \"$state_dir\"\n"
            "printf '%s\\n' \"$*\" >> \"$log_file\"\n"
            "key_for() {\n"
            "  printf '%s' \"$1\" | tr '/' '_'\n"
            "}\n"
            "cmd=\"${1:-}\"\n"
            "case \"$cmd\" in\n"
            "  print)\n"
            "    key=\"$(key_for \"${2:-}\")\"\n"
            "    [[ -f \"$state_dir/$key.loaded\" ]]\n"
            "    if [[ -n \"${FAKE_LAUNCHCTL_PRINT_OUTPUT:-}\" ]]; then\n"
            "      printf '%b\\n' \"$FAKE_LAUNCHCTL_PRINT_OUTPUT\"\n"
            "    fi\n"
            "    ;;\n"
            "  bootstrap)\n"
            "    domain=\"${2:-}\"\n"
            "    plist=\"${3:-}\"\n"
            "    base=\"$(basename \"$plist\" .plist)\"\n"
            "    touch \"$state_dir/$(key_for \"$domain/$base\").loaded\"\n"
            "    ;;\n"
            "  kickstart)\n"
            "    label=\"${!#}\"\n"
            "    touch \"$state_dir/$(key_for \"$label\").loaded\"\n"
            "    ;;\n"
            "  bootout)\n"
            "    key=\"$(key_for \"${2:-}\")\"\n"
            "    rm -f \"$state_dir/$key.loaded\"\n"
            "    ;;\n"
            "  enable|disable)\n"
            "    ;;\n"
            "  *)\n"
            "    echo \"unexpected launchctl command: $*\" >&2\n"
            "    exit 1\n"
            "    ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script, log_path, state_dir

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
            seckit_env_log = root / "seckit-env.log"
            fake_seckit = root / "fake-seckit"
            fake_seckit.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s\\n' \"$*\" > \"{args_log}\"\n"
                f"printf 'OPENCLAW_GATEWAY_TOKEN=%s\\nTELEGRAM_BOT_TOKEN=%s\\n' \"${{OPENCLAW_GATEWAY_TOKEN:-}}\" \"${{TELEGRAM_BOT_TOKEN:-}}\" > \"{seckit_env_log}\"\n"
                "export OPENCLAW_GATEWAY_TOKEN=sec-gateway\n"
                "export TELEGRAM_BOT_TOKEN=sec-telegram\n"
                "shift\n"
                "while [[ \"$1\" != \"--\" ]]; do shift; done\n"
                "shift\n"
                "exec \"$@\"\n",
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
                    "LLMOPS_SECKIT_ACCOUNT": "miafour",
                    "OPENCLAW_GATEWAY_CMD": str(fake_cmd),
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("gateway run --port 18789|sec-gateway|sec-telegram", invocations.read_text(encoding="utf-8"))
            self.assertIn("run --service openclaw --account miafour --names OPENCLAW_GATEWAY_TOKEN,TELEGRAM_BOT_TOKEN,OPENAI_API_KEY,HUGGINGFACE_API_KEY,LOCAL_EMBEDDING_API_KEY,BRAVE_SEARCH_API_KEY,ELEVENLABS_API_KEY,SAG_API_KEY", args_log.read_text(encoding="utf-8"))
            self.assertEqual(seckit_env_log.read_text(encoding="utf-8").splitlines(), ["OPENCLAW_GATEWAY_TOKEN=", "TELEGRAM_BOT_TOKEN="])
            self.assertTrue((home / ".config" / "llm-ops" / "config" / "agents" / "openclaw.env").exists())

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
            self.assertIn("gateway run --replace", invocations.read_text(encoding="utf-8"))

            status = self.run_bash(f'"{AGENTCTL}" status all', env=base_env)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("agentctl[openclaw]: running pid=", status.stdout)
            self.assertIn("agentctl[hermes]: running pid=", status.stdout)
            self.assertIn("agentctl-openclaw.log", status.stdout)
            self.assertIn("agentctl-hermes.log", status.stdout)

            pid_dir = home / ".local" / "state" / "llm-ops" / "run"
            self.assertTrue((pid_dir / "agentctl-openclaw.pid").exists())
            self.assertTrue((pid_dir / "agentctl-hermes.pid").exists())

            stop = self.run_bash(f'"{AGENTCTL}" stop all', env=base_env)
            self.assertEqual(stop.returncode, 0, stop.stderr)
            self.assertIn("agentctl-openclaw: stopped pid", stop.stdout)
            self.assertIn("agentctl-hermes: stopped pid", stop.stdout)

    def test_gateway_start_hermes_sources_agent_shell_init(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            hermes_home = home / ".hermes"
            invocations = root / "gateway-invocations.log"
            fake_cmd = self._write_fake_gateway_cmd(root)
            bashrc = home / ".bashrc"
            bashrc.parent.mkdir(parents=True, exist_ok=True)
            bashrc.write_text("export HERMES_FROM_BASHRC=1\n", encoding="utf-8")
            fake_cmd.write_text(
                "#!/usr/bin/env bash\n"
                "trap 'exit 0' TERM INT\n"
                "echo \"$0 $*|${HERMES_FROM_BASHRC:-}\" >> \"$FAKE_GATEWAY_INVOCATIONS\"\n"
                "while :; do sleep 1; done\n",
                encoding="utf-8",
            )
            fake_cmd.chmod(0o755)

            base_env = {
                "HOME": str(home),
                "LLMOPS_HOME": str(llmops_home),
                "HERMES_HOME": str(hermes_home),
                "LLMOPS_USE_SECKIT": "0",
                "HERMES_GATEWAY_CMD": str(fake_cmd),
                "FAKE_GATEWAY_INVOCATIONS": str(invocations),
            }

            start = self.run_bash(f'"{AGENTCTL}" start hermes', env=base_env)
            self.assertEqual(start.returncode, 0, start.stderr)
            self.assertIn("agentctl[hermes]: started pid=", start.stdout)
            self.assertIn("gateway run --replace|1", invocations.read_text(encoding="utf-8"))

            stop = self.run_bash(f'"{AGENTCTL}" stop hermes', env=base_env)
            self.assertEqual(stop.returncode, 0, stop.stderr)

    def test_agentctl_launchd_install_start_stop_and_remove_openclaw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            hermes_home = home / ".hermes"
            openclaw_home = home / ".openclaw"
            openclaw_home.mkdir(parents=True)
            fake_launchctl, launchctl_log, launchctl_state = self._write_fake_launchctl(root)

            base_env = {
                "HOME": str(home),
                "LLMOPS_HOME": str(llmops_home),
                "HERMES_HOME": str(hermes_home),
                "OPENCLAW_HOME": str(openclaw_home),
                "LLMOPS_USE_SECKIT": "0",
                "LAUNCHCTL_BIN": str(fake_launchctl),
                "FAKE_LAUNCHCTL_LOG": str(launchctl_log),
                "FAKE_LAUNCHCTL_STATE_DIR": str(launchctl_state),
                "FAKE_LAUNCHCTL_PRINT_OUTPUT": "state = running\\npid = 4242",
            }

            install = self.run_bash(f'"{AGENTCTL}" launchd-install openclaw', env=base_env)
            self.assertEqual(install.returncode, 0, install.stderr)
            self.assertIn("agentctl[openclaw]: installed launchd plist", install.stdout)
            self.assertIn("agentctl[openclaw]: launchd started label=ai.openclaw.gateway", install.stdout)

            plist_path = home / "Library" / "LaunchAgents" / "ai.openclaw.gateway.plist"
            self.assertTrue(plist_path.exists())
            plist_text = plist_path.read_text(encoding="utf-8")
            self.assertIn("/scripts/agentctl", plist_text)
            self.assertIn("<string>launchd-run</string>", plist_text)
            self.assertIn("<string>openclaw</string>", plist_text)

            status = self.run_bash(f'"{AGENTCTL}" launchd-status openclaw', env=base_env)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("agentctl[openclaw]: launchd loaded label=ai.openclaw.gateway", status.stdout)
            self.assertIn("active (launchd pid=4242)", status.stdout)

            bootout = self.run_bash(f'"{AGENTCTL}" launchd-bootout openclaw', env=base_env)
            self.assertEqual(bootout.returncode, 0, bootout.stderr)
            self.assertIn("agentctl[openclaw]: launchd booted out label=ai.openclaw.gateway", bootout.stdout)

            stop = self.run_bash(f'"{AGENTCTL}" launchd-stop openclaw', env=base_env)
            self.assertEqual(stop.returncode, 0, stop.stderr)
            self.assertIn("agentctl[openclaw]: launchd stopped label=ai.openclaw.gateway", stop.stdout)

            disabled = self.run_bash(f'"{AGENTCTL}" launchd-disable openclaw', env=base_env)
            self.assertEqual(disabled.returncode, 0, disabled.stderr)
            self.assertIn("agentctl[openclaw]: launchd disabled label=ai.openclaw.gateway", disabled.stdout)

            removed = self.run_bash(f'"{AGENTCTL}" launchd-remove openclaw', env=base_env)
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertIn("agentctl[openclaw]: removed launchd plist", removed.stdout)
            self.assertFalse(plist_path.exists())

            launchctl_lines = launchctl_log.read_text(encoding="utf-8")
            self.assertIn("enable gui/", launchctl_lines)
            self.assertIn("bootstrap gui/", launchctl_lines)
            self.assertIn("kickstart -k gui/", launchctl_lines)
            self.assertIn("bootout gui/", launchctl_lines)

    def test_agentctl_launchd_remove_does_not_require_seckit_or_seed_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            llmops_home = home / ".llm-ops"
            hermes_home = home / ".hermes"
            openclaw_home = home / ".openclaw"
            openclaw_home.mkdir(parents=True)
            launch_agents = home / "Library" / "LaunchAgents"
            launch_agents.mkdir(parents=True)
            plist_path = launch_agents / "ai.openclaw.gateway.plist"
            plist_path.write_text("<plist></plist>\n", encoding="utf-8")

            fake_launchctl, launchctl_log, launchctl_state = self._write_fake_launchctl(root)
            fake_seckit = root / "fake-seckit"
            fake_seckit.write_text(
                "#!/usr/bin/env bash\n"
                "echo 'ERROR: fake seckit should not run' >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_seckit.chmod(0o755)

            proc = self.run_bash(
                f'"{AGENTCTL}" launchd-remove openclaw',
                env={
                    "HOME": str(home),
                    "LLMOPS_HOME": str(llmops_home),
                    "HERMES_HOME": str(hermes_home),
                    "OPENCLAW_HOME": str(openclaw_home),
                    "LAUNCHCTL_BIN": str(fake_launchctl),
                    "FAKE_LAUNCHCTL_LOG": str(launchctl_log),
                    "FAKE_LAUNCHCTL_STATE_DIR": str(launchctl_state),
                    "LLMOPS_USE_SECKIT": "1",
                    "LLMOPS_SECKIT_BIN": str(fake_seckit),
                    "BRAVE_SEARCH_API_KEY": "env-brave-key",
                },
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("fake seckit should not run", proc.stderr)
            self.assertNotIn("copied template config", proc.stderr)
            self.assertFalse(plist_path.exists())
            self.assertFalse((home / ".config" / "llm-ops" / "config" / "agents" / "openclaw.env").exists())


if __name__ == "__main__":
    unittest.main()
