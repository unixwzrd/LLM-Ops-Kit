#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import importlib.machinery
import contextlib
import io
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


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
            output = root / "new-config" / "config.json"
            args = Namespace(legacy_home=str(legacy_home), output=str(output), dry_run=True, force=False)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_migrate_config(args), 0)
            rendered = stdout.getvalue()
            self.assertIn("migration_mode=dry-run", rendered)
            self.assertIn(f"destination_config={output}", rendered)
            self.assertIn("source\tpresent\tlegacy global config", rendered)
            self.assertFalse(output.exists())

    def test_migrate_config_writes_minimum_json_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy_home = root / ".llm-ops"
            legacy_home.mkdir()
            output = root / "config" / "config.json"
            args = Namespace(legacy_home=str(legacy_home), output=str(output), dry_run=False, force=False)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(self.admin.cmd_migrate_config(args), 0)
            self.assertTrue(output.exists())
            loaded = self.admin.load_config(output)
            self.assertTrue(loaded.exists)
            self.assertEqual(loaded.data["secrets"]["provider"], "env")


if __name__ == "__main__":
    unittest.main()
