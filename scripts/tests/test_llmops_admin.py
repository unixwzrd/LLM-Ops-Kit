#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import importlib.machinery
import contextlib
import io
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from test_gguf_metadata import write_minimal_gguf


REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN_PATH = REPO_ROOT / "scripts" / "llmops-admin"


def load_admin():
    loader = importlib.machinery.SourceFileLoader("llmops_admin", str(ADMIN_PATH))
    spec = importlib.util.spec_from_loader("llmops_admin", loader)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["llmops_admin"] = module
    spec.loader.exec_module(module)
    return module


class LlmopsAdminTests(unittest.TestCase):
    def setUp(self) -> None:
        self.admin = load_admin()

    def write_inventory(self, root: Path) -> Path:
        inventory = root / "inventory.yml"
        inventory.write_text(
            "\n".join(
                [
                    "defaults:",
                    "  user: deploy",
                    "  port: 22",
                    "  install_root: ~/llmops",
                    "  ssh_key: ~/.ssh/llmops_test",
                    "  config_profile: default",
                    "hosts:",
                    "  - name: llm-a",
                    "    role: llm",
                    "    host: llm-a.local",
                    "    tags: [prod, model]",
                    "  - name: agent-a",
                    "    role: agent",
                    "    host: agent-a.local",
                    "    tags: [prod, agent]",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return inventory

    def test_inventory_parsing_and_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inventory = self.write_inventory(Path(tmp))
            hosts = self.admin.load_inventory(inventory)
            self.assertEqual([host.name for host in hosts], ["llm-a", "agent-a"])
            selected = self.admin.select_hosts(hosts, Namespace(role="llm", tag=None, host_name=None))
            self.assertEqual([host.name for host in selected], ["llm-a"])

    def test_config_precedence_reports_cli_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            host = self.admin.load_inventory(self.write_inventory(Path(tmp)))[0]
            config = self.admin.effective_config(host, model=None, cli_values={"PORT": "9999"})
            self.assertEqual(config["PORT"]["value"], "9999")
            self.assertEqual(config["PORT"]["source"], "CLI flags")

    def test_bootstrap_dry_run_plans_ssh_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(inventory=str(self.write_inventory(Path(tmp))), role="llm", tag=None, host_name=None, dry_run=True)
            self.assertEqual(self.admin.cmd_bootstrap_host(args), 0)

    def test_stage_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(
                inventory=str(self.write_inventory(Path(tmp))),
                role=None,
                tag=None,
                host_name=None,
                stage_root=str(Path(tmp) / "stage"),
                bundle_id="test-bundle",
                model=None,
                dry_run=True,
            )
            self.assertEqual(self.admin.cmd_stage(args), 0)

    def test_push_dry_run_aggregates_parallel_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory = self.write_inventory(root)
            stage = root / "stage" / "bundle"
            (stage / "package").mkdir(parents=True)
            (stage / "package" / "llm-ops-kit.tar.gz").write_text("package", encoding="utf-8")
            for name in ("llm-a", "agent-a"):
                host_dir = stage / "hosts" / name
                host_dir.mkdir(parents=True)
                (host_dir / "config.env").write_text("PORT=1\n", encoding="utf-8")
            args = Namespace(
                inventory=str(inventory),
                role=None,
                tag=None,
                host_name=None,
                stage_root=str(root / "stage"),
                stage=str(stage),
                workers=2,
                dry_run=True,
            )
            self.assertEqual(self.admin.cmd_push(args), 0)

    def test_migrate_config_dry_run_reports_sources_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy_home = root / ".llm-ops"
            legacy_home.mkdir()
            (legacy_home / "config.env").write_text("PORT=11434\n", encoding="utf-8")
            config_dir = legacy_home / "config"
            config_dir.mkdir()
            (config_dir / "Qwen3.6.env").write_text("CTX_SIZE=32768\n", encoding="utf-8")
            output = root / "new-config" / "config.json"
            args = Namespace(legacy_home=str(legacy_home), output=str(output), dry_run=True, force=False)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_migrate_config(args), 0)
            rendered = stdout.getvalue()
            self.assertIn("migration_mode=dry-run", rendered)
            self.assertIn(f"destination_config={output}", rendered)
            self.assertIn("source\tpresent\tlegacy global config", rendered)
            self.assertIn(f"destination\t{output.parent / 'models' / 'Qwen3.6.json'}", rendered)
            self.assertFalse(output.exists())

    def test_migrate_config_writes_structured_json_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy_home = root / ".llm-ops"
            config_dir = legacy_home / "config"
            agent_dir = config_dir / "agents"
            agent_dir.mkdir(parents=True)
            self.write_inventory(legacy_home)
            (legacy_home / "config.env").write_text("LLMOPS_UPSTREAM_PORT=11434\n", encoding="utf-8")
            (config_dir / "Qwen3.6.env").write_text(
                "\n".join(
                    [
                        'MODEL_TYPE="${MODEL_TYPE:-llm}"',
                        'MODEL="${MODEL:-/models/qwen3.6.gguf}"',
                        'PORT="${PORT:-11434}"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (agent_dir / "hermes.env").write_text("HERMES_GATEWAY_CMD=hermes\n", encoding="utf-8")
            output = root / "config" / "config.json"
            args = Namespace(legacy_home=str(legacy_home), output=str(output), dry_run=False, force=False)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_migrate_config(args), 0)
            self.assertTrue(output.exists())
            loaded = self.admin.load_config(output)
            self.assertTrue(loaded.exists)
            self.assertEqual(loaded.data["secrets"]["provider"], "env")
            self.assertEqual(loaded.data["runtime"]["env"]["LLMOPS_UPSTREAM_PORT"], "11434")
            inventory = json.loads((output.parent / "inventory.json").read_text(encoding="utf-8"))
            self.assertEqual([host["name"] for host in inventory["hosts"]], ["llm-a", "agent-a"])
            model = json.loads((output.parent / "models" / "Qwen3.6.json").read_text(encoding="utf-8"))
            self.assertEqual(model["type"], "llm")
            self.assertEqual(model["env"]["MODEL"], "/models/qwen3.6.gguf")
            agent = json.loads((output.parent / "agents" / "hermes.json").read_text(encoding="utf-8"))
            self.assertEqual(agent["env"]["HERMES_GATEWAY_CMD"], "hermes")

    def test_migrate_config_user_model_override_wins_over_repo_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy_home = root / ".llm-ops"
            config_dir = legacy_home / "config"
            config_dir.mkdir(parents=True)
            (config_dir / "qwen3.5.env").write_text("PORT=19999\n", encoding="utf-8")
            documents = self.admin.migration_documents(legacy_home)
            qwen_docs = [doc for path, doc in documents.items() if path.name == "Qwen3.5.json"]
            self.assertEqual(len(qwen_docs), 1)
            self.assertEqual(qwen_docs[0]["env"]["PORT"], "19999")
            self.assertEqual(len(qwen_docs[0]["sources"]), 2)

    def test_model_add_dry_run_renders_profile_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "Qwen3.6-Test.gguf"
            write_minimal_gguf(model)
            output_dir = root / "models"
            args = Namespace(
                name="qwen3.6",
                gguf=str(model),
                output=str(output_dir),
                host="127.0.0.1",
                port=11434,
                gpu_layers="auto",
                template="",
                dry_run=True,
                force=False,
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_model_add(args), 0)
            rendered = stdout.getvalue()
            self.assertIn("model_profile=qwen3.6", rendered)
            self.assertIn(f"destination={output_dir / 'qwen3.6.json'}", rendered)
            self.assertIn('"ctx_size": 32768', rendered)
            self.assertFalse((output_dir / "qwen3.6.json").exists())

    def test_model_add_writes_profile_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "Qwen3.6-Test.gguf"
            write_minimal_gguf(model)
            output = root / "qwen3.6.json"
            args = Namespace(
                name="qwen3.6",
                gguf=str(model),
                output=str(output),
                host="0.0.0.0",
                port=11999,
                gpu_layers="99",
                template="/templates/qwen.jinja",
                cache_prompt=True,
                cache_reuse=512,
                slot_save_path="/state/slots",
                spec_type="ngram-map",
                spec_ngram_size_n=12,
                spec_ngram_size_m=48,
                perf=True,
                flash_attention=True,
                no_cpu_moe=True,
                no_host=True,
                extra_flag=["--custom-flag", "value"],
                dry_run=False,
                force=False,
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_model_add(args), 0)
            profile = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(profile["name"], "qwen3.6")
            self.assertEqual(profile["model_id"], "Qwen3.6-Test.gguf")
            self.assertEqual(profile["runtime"]["port"], 11999)
            self.assertEqual(profile["llama"]["ctx_size"], 32768)
            self.assertEqual(profile["llama"]["gpu_layers"], "99")
            self.assertEqual(profile["template"]["path"], "/templates/qwen.jinja")
            self.assertEqual(profile["server"]["cache_reuse"], 512)
            self.assertEqual(profile["server"]["slot_save_path"], "/state/slots")
            self.assertEqual(profile["server"]["spec_type"], "ngram-map")
            self.assertEqual(profile["server"]["spec_ngram_size_n"], 12)
            self.assertTrue(profile["server"]["perf"])
            self.assertTrue(profile["server"]["flash_attention"])
            self.assertTrue(profile["server"]["no_cpu_moe"])
            self.assertTrue(profile["server"]["no_host"])
            self.assertEqual(profile["server"]["extra_flags"], ["--custom-flag", "value"])

    def test_model_render_env_outputs_structured_profile_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_path = root / "qwen3.6.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "qwen3.6",
                        "type": "llm",
                        "model_path": "/models/qwen3.6.gguf",
                        "runtime": {
                            "host": "127.0.0.1",
                            "port": 11999,
                            "threads": "auto",
                            "threads_batch": "auto",
                        },
                        "llama": {
                            "ctx_size": 32768,
                            "gpu_layers": "99",
                            "batch_size": 1024,
                            "ubatch_size": 512,
                            "use_mlock": True,
                            "use_no_mmap": True,
                            "direct_io": True,
                        },
                        "sampling": {
                            "temp": 0.9,
                            "top_p": 0.95,
                            "top_k": 20,
                            "min_p": 0.0,
                            "presence_penalty": 1.5,
                            "repeat_penalty": 1.0,
                        },
                        "template": {
                            "enabled": True,
                            "path": "/templates/qwen.jinja",
                        },
                        "server": {
                            "cache_prompt": True,
                            "cache_reuse": 512,
                            "slot_save_path": "/state/slots",
                            "spec_type": "ngram-map",
                            "spec_ngram_size_n": 12,
                            "spec_ngram_size_m": 48,
                            "perf": True,
                            "flash_attention": True,
                            "no_cpu_moe": True,
                            "no_host": True,
                            "extra_flags": ["--custom-flag", "value"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = Namespace(name="qwen3.6", profile_path=str(profile_path), json=False)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_model_render_env(args), 0)
            rendered = stdout.getvalue()
            self.assertIn("MODEL=/models/qwen3.6.gguf", rendered)
            self.assertIn("PORT=11999", rendered)
            self.assertIn("CTX_SIZE=32768", rendered)
            self.assertIn("USE_CUSTOM_TEMPLATE=1", rendered)
            self.assertIn("CACHE_PROMPT=1", rendered)
            self.assertIn("CACHE_REUSE=512", rendered)
            self.assertIn("SLOT_SAVE_PATH=/state/slots", rendered)
            self.assertIn("SPEC_TYPE=ngram-map", rendered)
            self.assertIn("SPEC_NGRAM_SIZE_N=12", rendered)
            self.assertIn("SPEC_NGRAM_SIZE_M=48", rendered)
            self.assertIn("PERF=1", rendered)
            self.assertIn("FLASH_ATTENTION=1", rendered)
            self.assertIn("NO_CPU_MOE=1", rendered)
            self.assertIn("NO_HOST=1", rendered)
            self.assertIn("EXTRA_FLAGS='--custom-flag value'", rendered)

    def test_model_render_env_preserves_migrated_env_profiles(self) -> None:
        profile = {
            "schema_version": 1,
            "name": "Qwen3.5",
            "env": {
                "MODEL": "/models/qwen3.5.gguf",
                "PORT": "11434",
            },
        }
        self.assertEqual(
            self.admin.render_model_env(profile),
            {
                "MODEL": "/models/qwen3.5.gguf",
                "PORT": "11434",
            },
        )

    def write_structured_profile(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "qwen3.6",
                    "type": "llm",
                    "model_path": "/models/qwen3.6.gguf",
                    "runtime": {
                        "host": "127.0.0.1",
                        "port": 11999,
                        "threads": "auto",
                        "threads_batch": "auto",
                    },
                    "llama": {
                        "ctx_size": 32768,
                        "gpu_layers": "99",
                        "batch_size": 1024,
                        "ubatch_size": 512,
                        "use_mlock": True,
                        "use_no_mmap": True,
                        "direct_io": True,
                    },
                    "sampling": {},
                    "template": {},
                    "server": {
                        "cache_prompt": True,
                        "cache_reuse": 512,
                        "slot_save_path": "/state/slots",
                        "spec_type": "ngram-map",
                        "spec_ngram_size_n": 12,
                        "spec_ngram_size_m": 48,
                        "perf": True,
                        "flash_attention": True,
                        "no_cpu_moe": True,
                        "no_host": True,
                        "extra_flags": [],
                    },
                    "secrets": {
                        "required": [],
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_model_simulate_start_prints_launch_plan_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "qwen3.6.json"
            self.write_structured_profile(profile_path)
            args = Namespace(name="qwen3.6", profile_path=str(profile_path), action="start")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_model_simulate(args), 0)
            rendered = stdout.getvalue()
            self.assertIn("simulation=model", rendered)
            self.assertIn("status=ok", rendered)
            self.assertIn("would_launch=llama-server", rendered)
            self.assertIn("--ctx-size 32768", rendered)
            self.assertIn("--cache-prompt", rendered)
            self.assertIn("--cache-reuse 512", rendered)
            self.assertIn("--slot-save-path /state/slots", rendered)
            self.assertIn("--spec-type ngram-map", rendered)
            self.assertIn("--spec-ngram-size-n 12", rendered)
            self.assertIn("--spec-ngram-size-m 48", rendered)
            self.assertIn("--perf", rendered)
            self.assertIn("--fa", rendered)
            self.assertIn("--no-cpu-moe", rendered)
            self.assertIn("--no-host", rendered)

    def test_model_simulate_reports_missing_required_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "broken.json"
            profile_path.write_text(json.dumps({"schema_version": 1, "name": "broken"}), encoding="utf-8")
            args = Namespace(name="broken", profile_path=str(profile_path), action="start")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_model_simulate(args), 2)
            rendered = stdout.getvalue()
            self.assertIn("status=invalid", rendered)
            self.assertIn("MODEL", rendered)

    def test_model_profile_doctor_flags_missing_new_structured_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "old.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "old",
                        "type": "llm",
                        "model_path": "/models/old.gguf",
                        "runtime": {
                            "host": "127.0.0.1",
                            "port": 11434,
                        },
                        "llama": {
                            "ctx_size": 32768,
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = Namespace(name="old", profile_path=str(profile_path), remote=True)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_model_profile_doctor(args), 1)
            rendered = stdout.getvalue()
            self.assertIn("status=missing-parameters", rendered)
            self.assertIn("location=remote", rendered)
            self.assertIn("missing=server", rendered)
            self.assertIn("missing=runtime.threads", rendered)

    def test_model_profile_doctor_accepts_complete_structured_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "qwen3.6.json"
            self.write_structured_profile(profile_path)
            args = Namespace(name="qwen3.6", profile_path=str(profile_path), remote=False)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_model_profile_doctor(args), 0)
            self.assertIn("status=ok", stdout.getvalue())

    def test_agent_simulate_openclaw_uses_profile_env_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "openclaw.env"
            profile_path.write_text(
                "\n".join(
                    [
                        "OPENCLAW_GATEWAY_CMD=/bin/openclaw",
                        "LLMOPS_GATEWAY_PORT=18888",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            args = Namespace(name="openclaw", profile_path=str(profile_path), action="start")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_agent_simulate(args), 0)
            rendered = stdout.getvalue()
            self.assertIn("simulation=agent", rendered)
            self.assertIn("backend=openclaw", rendered)
            self.assertIn("would_launch=/bin/openclaw gateway run --port 18888", rendered)

    def test_agent_simulate_hermes_uses_json_profile_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "hermes.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "hermes",
                        "env": {
                            "HERMES_GATEWAY_CMD": "/bin/hermes",
                            "HERMES_GATEWAY_ARGS": "--replace --debug",
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = Namespace(name="hermes", profile_path=str(profile_path), action="start")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_agent_simulate(args), 0)
            rendered = stdout.getvalue()
            self.assertIn("simulation=agent", rendered)
            self.assertIn("backend=hermes", rendered)
            self.assertIn("would_launch=/bin/hermes gateway --replace --debug", rendered)

    def test_deploy_plan_dry_run_reports_hosts_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory = self.write_inventory(root)
            stage_root = root / "stage"
            args = Namespace(
                inventory=str(inventory),
                role=None,
                tag=None,
                host_name=None,
                stage_root=str(stage_root),
                bundle_id="smoke",
                dry_run=True,
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_deploy_plan(args), 0)
            rendered = stdout.getvalue()
            self.assertIn("simulation=deploy", rendered)
            self.assertIn("selected_hosts=2", rendered)
            self.assertIn("host\tname=llm-a", rendered)
            self.assertIn("host\tname=agent-a", rendered)
            self.assertIn("dry-run: no package built, no files written, no SSH attempted", rendered)
            self.assertFalse(stage_root.exists())


if __name__ == "__main__":
    unittest.main()
