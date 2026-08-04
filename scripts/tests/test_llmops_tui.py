#!/usr/bin/env python
"""TUI contract tests that do not require a terminal."""

from __future__ import annotations

import argparse
import unittest
import tempfile
import json
from pathlib import Path
from unittest import mock

from llmops_kit import llmops_cli
from llmops_kit.llmops_init import initialize
from llmops_kit.llmops_executor import MutationPlan, Operation
from llmops_kit.llmops_paths import resolve_paths
from llmops_kit.llmops_tui import (
    CONDITION_STYLES,
    build_application,
    equivalent_command,
    schema_configure_command,
)
from llmops_kit.llmops_templates import load_template_registry
from llmops_kit.llmops_ui import (
    UiPreferences,
    load_ui_preferences,
    save_ui_preferences,
    status_cell_style,
)


class TuiContractTests(unittest.TestCase):
    def test_mutation_has_equivalent_cli(self) -> None:
        self.assertEqual(
            equivalent_command("restart", "example:model"),
            "llmops component restart example:model",
        )

    def test_schema_commands_distinguish_save_from_save_and_restart(self) -> None:
        saved = schema_configure_command(
            "example:model",
            ["profile.runtime.port=11434"],
            [],
            expected_hash="abc123",
        )
        restarted = schema_configure_command(
            "example:model",
            ["profile.runtime.port=11434"],
            [],
            expected_hash="abc123",
            restart_affected=True,
        )
        self.assertIn("--expected-hash abc123", saved)
        self.assertNotIn("--restart-affected", saved)
        self.assertIn("--restart-affected", restarted)

    def test_shared_status_preserves_authority_only_semantics(self) -> None:
        catalog = {
            "schema_version": 2,
            "trusted_control_hosts": ["control-host"],
            "hosts": [
                {"name": "desktop-host", "user": "operator", "peer_observable": False}
            ],
            "components": [
                {
                    "id": "example:desktop-tunnel",
                    "component_id": "desktop-tunnel",
                    "host": "desktop-host",
                    "driver": "ssh-tunnel",
                    "profile": "desktop-tunnel",
                    "enabled": True,
                    "tags": ["tunnel"],
                }
            ],
        }
        args = argparse.Namespace(
            selector=None,
            all=False,
            verbose=False,
            workers=8,
            host_timeout=20,
            status_host=None,
            local=False,
        )
        with (
            mock.patch.object(llmops_cli, "_load_observer_catalog", return_value=catalog),
            mock.patch.object(llmops_cli, "_current_snapshot_host", return_value="control-host"),
        ):
            payload = llmops_cli._collect_status(args)
        self.assertEqual(payload[0]["observability"], "authority-only")
        self.assertEqual(payload[0]["condition"], "unobserved")
        self.assertEqual(payload[0]["lifecycle"], "unknown")
        self.assertEqual(payload[0]["execution_user"], "operator")

    def test_condition_styles_are_distinct_and_textual(self) -> None:
        self.assertEqual(
            set(CONDITION_STYLES),
            {"ok", "down", "attention", "error", "unobserved"},
        )
        self.assertEqual(len(set(CONDITION_STYLES.values())), 5)

    def test_status_cells_preserve_independent_semantics(self) -> None:
        record = {
            "condition": "attention",
            "lifecycle": "running",
            "health": "healthy",
            "component": "sample:embedding",
            "component_version": "0.9.0b15",
            "drift": "stale-runtime",
        }
        self.assertEqual(status_cell_style("condition", record), CONDITION_STYLES["attention"])
        self.assertEqual(status_cell_style("lifecycle", record), CONDITION_STYLES["ok"])
        self.assertEqual(status_cell_style("health", record), CONDITION_STYLES["ok"])
        self.assertEqual(status_cell_style("component", record), CONDITION_STYLES["attention"])
        self.assertEqual(status_cell_style("component_version", record), CONDITION_STYLES["attention"])
        self.assertEqual(status_cell_style("drift", record), CONDITION_STYLES["attention"])

    def test_local_preferences_do_not_require_canonical_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ui.json"
            expected = UiPreferences(auto_refresh=False, refresh_seconds=30)
            save_ui_preferences(path, expected)
            self.assertEqual(load_ui_preferences(path), expected)


class TuiApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_editor_warns_about_shared_profile_consumers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = resolve_paths(
                {
                    "HOME": str(root),
                    "LLMOPS_CONFIG_HOME": str(root / "config"),
                    "LLMOPS_DATA_HOME": str(root / "data"),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                    "LLMOPS_CACHE_HOME": str(root / "cache"),
                }
            )
            initialize(paths, preset="single-host", user="operator")
            stack_path = paths.stacks_dir / "starter.json"
            stack = json.loads(stack_path.read_text(encoding="utf-8"))
            shared = dict(stack["components"][0])
            shared["id"] = "chat-shadow"
            stack["components"].append(shared)
            stack_path.write_text(json.dumps(stack, indent=2) + "\n", encoding="utf-8")

            app = build_application(str(paths.config_home), None)
            async with app.run_test(size=(140, 44)) as pilot:
                await pilot.pause(1)
                await pilot.click("#action-configure")
                await pilot.pause()
                warning = str(app.screen.query_one("#shared-profile-warning").render())
                self.assertIn("starter:chat-shadow", warning)

    async def test_schema_editor_saves_persistently_and_optionally_restarts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = resolve_paths(
                {
                    "HOME": str(root),
                    "LLMOPS_CONFIG_HOME": str(root / "config"),
                    "LLMOPS_DATA_HOME": str(root / "data"),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                    "LLMOPS_CACHE_HOME": str(root / "cache"),
                }
            )
            initialize(paths, preset="single-host", user="operator")
            app = build_application(str(paths.config_home), None)
            queued = {"operation_id": "20260730T120000Z-abcdef123456", "state": "queued"}
            with mock.patch("llmops_kit.llmops_tui.dispatch", return_value=queued) as detached:
                async with app.run_test(size=(140, 44)) as pilot:
                    await pilot.pause(1)
                    await pilot.click("#action-configure")
                    await pilot.pause()
                    editor = app.screen
                    self.assertIn("persistent", str(editor.query_one(".warning").render()).lower())
                    self.assertTrue(editor.query(".field-group"))
                    self.assertIsNotNone(editor.query_one("#save"))
                    self.assertIsNotNone(editor.query_one("#save-restart"))
                    advanced = list(editor.query(".advanced-field"))
                    self.assertTrue(advanced)
                    self.assertTrue(all(not field.display for field in advanced))
                    await pilot.click("#toggle-advanced")
                    await pilot.pause()
                    self.assertTrue(all(field.display for field in advanced))
                    enabled_index = next(
                        index
                        for index, row in enumerate(editor.rows)
                        if row["path"] == "component.enabled"
                    )
                    editor.query_one(f"#schema-field-{enabled_index}").value = not bool(
                        editor.initial_values[enabled_index]
                    )
                    await pilot.click("#revert-all")
                    await pilot.pause()
                    self.assertEqual(
                        editor.query_one(f"#schema-field-{enabled_index}").value,
                        bool(editor.initial_values[enabled_index]),
                    )
                    editor.query_one(f"#schema-field-{enabled_index}").value = not bool(
                        editor.initial_values[enabled_index]
                    )
                    await pilot.click("#save")
                    await pilot.pause()
                    command = str(app.screen.query_one("#equivalent-command").render())
                    self.assertNotIn("--restart-affected", command)
                    self.assertIn("--expected-hash", command)
                    await pilot.click("#cancel")
                    await pilot.pause()

                    await pilot.click("#action-configure")
                    await pilot.pause()
                    editor = app.screen
                    enabled_index = next(
                        index
                        for index, row in enumerate(editor.rows)
                        if row["path"] == "component.enabled"
                    )
                    editor.query_one(f"#schema-field-{enabled_index}").value = not bool(
                        editor.initial_values[enabled_index]
                    )
                    editor.query_one("#save-restart").press()
                    await pilot.pause()
                    command = str(app.screen.query_one("#equivalent-command").render())
                    self.assertIn("--restart-affected", command)
                    self.assertEqual(str(app.screen.query_one("#run").label), "Save & Restart")
                    await pilot.click("#run")
                    await pilot.pause()
                    self.assertTrue(detached.called)
                    self.assertIn("--restart-affected", detached.call_args.kwargs["argv"])

    async def test_headless_views_and_mutation_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = resolve_paths(
                {
                    "HOME": str(root),
                    "LLMOPS_CONFIG_HOME": str(root / "config"),
                    "LLMOPS_DATA_HOME": str(root / "data"),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                    "LLMOPS_CACHE_HOME": str(root / "cache"),
                }
            )
            initialize(paths, preset="single-host", user="operator")
            stack_path = paths.stacks_dir / "starter.json"
            stack = json.loads(stack_path.read_text(encoding="utf-8"))
            stack["components"][0]["enabled"] = True
            stack_path.write_text(json.dumps(stack, indent=2) + "\n", encoding="utf-8")
            original = (paths.stacks_dir / "starter.json").read_bytes()
            app = build_application(str(paths.config_home), None)
            self.assertEqual(app.desired_topology.paths.config_home, paths.config_home)
            with mock.patch.object(llmops_cli, "_collect_status", wraps=llmops_cli._collect_status) as collect:
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause(1)
                    table = app.query_one("#components")
                    action_bar = app.query_one("#action-bar")
                    self.assertLess(action_bar.region.y, table.region.y)
                    self.assertEqual(table.row_count, 3)
                    await pilot.press("down")
                    await pilot.pause()
                    self.assertIn(app.rows[1].qualified_id, str(app.query_one("#detail").render()))
                    await pilot.press("v")
                    await pilot.pause()
                    self.assertEqual(table.row_count, 1)
                    await pilot.press("v")
                    await pilot.pause()
                    await pilot.press("s")
                    await pilot.pause()
                    self.assertIn(
                        "llmops component start starter:chat",
                        str(app.screen.query_one("#equivalent-command").render()),
                    )
                    await pilot.click("#cancel")
                    await pilot.pause()
                    await pilot.press("t")
                    await pilot.pause()
                    tree = app.screen.query_one("#topology-tree")
                    self.assertIsNotNone(tree)
                    host_filter = app.screen.query_one("#topology-host")
                    host_filter.value = "local"
                    await pilot.pause()
                    self.assertEqual(len(tree.root.children), 1)
                    await pilot.click("#reset")
                    await pilot.pause()
                    self.assertEqual(host_filter.value, "")
                    await pilot.click("#close")
                    await pilot.pause()
                    await pilot.click("#action-settings")
                    await pilot.pause()
                    self.assertIsNotNone(app.screen.query_one("#settings-dialog"))
                    self.assertEqual(
                        app.screen.query_one("#settings-auto-refresh").styles.background.hex,
                        "#18222D",
                    )
                    self.assertEqual(
                        app.screen.query_one("#save").styles.background.hex,
                        "#496F91",
                    )
                    await pilot.press("escape")
                    await pilot.pause()
                    await pilot.click("#action-help")
                    await pilot.pause()
                    self.assertIsNotNone(app.screen.query_one("#help-dialog"))
                    await pilot.press("escape")
                    await pilot.pause()
                    await pilot.click("#action-details")
                    await pilot.pause()
                    self.assertIsNotNone(app.screen.query_one("#details-dialog"))
                    self.assertIn("effective_configuration", str(app.screen.query_one(".details-body").render()))
                    await pilot.press("escape")
                    await pilot.pause()
                    await pilot.click("#action-configure")
                    await pilot.pause()
                    self.assertIsNotNone(app.screen.query_one("#schema-edit-dialog"))
                    self.assertIsNotNone(app.screen.query_one("#schema-fields"))
                    app.on_data_table_row_highlighted(
                        type(
                            "RowEvent",
                            (),
                            {"cursor_row": 1, "data_table": table},
                        )()
                    )
                    self.assertIsNotNone(app.screen.query_one("#schema-edit-dialog"))
                    await pilot.press("escape")
                    await pilot.pause()
                    await pilot.click("#action-catalog")
                    await pilot.pause()
                    self.assertIsNotNone(app.screen.query_one("#catalog-dialog"))
                    await pilot.click("#add")
                    await pilot.pause()
                    self.assertIsNotNone(app.screen.query_one("#add-component-dialog"))
                    await pilot.press("escape")
                    await pilot.pause()
                    with mock.patch.object(app, "exit") as exit_app:
                        await pilot.click("#action-quit")
                        await pilot.pause()
                        exit_app.assert_called_once()
                collect.assert_called()
            self.assertEqual((paths.stacks_dir / "starter.json").read_bytes(), original)

    async def test_service_catalog_provisions_without_manual_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = resolve_paths(
                {
                    "HOME": str(root),
                    "LLMOPS_CONFIG_HOME": str(root / "config"),
                    "LLMOPS_DATA_HOME": str(root / "data"),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                    "LLMOPS_CACHE_HOME": str(root / "cache"),
                }
            )
            initialize(paths, preset="single-host", user="operator")
            app = build_application(str(paths.config_home), None)
            async with app.run_test(size=(140, 44)) as pilot:
                await pilot.pause(1)
                await pilot.click("#action-catalog")
                await pilot.pause()
                catalog = app.screen.query_one("#catalog-table")
                catalog.move_cursor(row=app.screen.template_ids.index("standalone"))
                await pilot.pause()
                await pilot.click("#add")
                await pilot.pause()
                app.screen.query_one("#next-placement").press()
                await pilot.pause()
                self.assertIn("Component ID is required", str(app.screen.query_one("#add-error").render()))
                app.screen.query_one("#add-id").value = "worker"
                app.screen.query_one("#add-profile-name").value = "worker-profile"
                await pilot.pause()
                self.assertIn("Step 1 of 4", str(app.screen.query_one("#add-progress").render()))
                app.screen.query_one("#next-placement").press()
                await pilot.pause()
                self.assertIn("Step 2 of 4", str(app.screen.query_one("#add-progress").render()))
                app.screen.query_one("#next-settings").press()
                await pilot.pause()
                self.assertIn("Step 3 of 4", str(app.screen.query_one("#add-progress").render()))
                app.screen.query_one("#next-connections").press()
                await pilot.pause()
                self.assertIn("Step 4 of 4", str(app.screen.query_one("#add-progress").render()))
                self.assertIn("Initial lifecycle: disabled", str(app.screen.query_one("#add-review").render()))
                await pilot.click("#review")
                await pilot.pause()
                self.assertIn(
                    "llmops component add worker --template standalone",
                    str(app.screen.query_one("#equivalent-command").render()),
                )
                review = str(app.screen.query_one(".dialog-body").render())
                self.assertIn("worker-profile.json", review)
                self.assertIn("authority hash", review)
                self.assertIn("created disabled", review)
                await pilot.click("#run")
                await pilot.pause(1)
            topology = llmops_cli.build_topology(
                config_home=str(paths.config_home),
                inventory=str(paths.inventory_file),
            )
            component = topology.resolve_component("worker")
            self.assertEqual(component.template_id, "standalone")
            self.assertFalse(component.enabled)
            profile_path = paths.services_dir / "worker-profile.json"
            self.assertTrue(profile_path.is_file())
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(profile["actions"]["restart"], ["/usr/bin/true"])

    async def test_service_catalog_imports_reviewed_local_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = resolve_paths(
                {
                    "HOME": str(root),
                    "LLMOPS_CONFIG_HOME": str(root / "config"),
                    "LLMOPS_DATA_HOME": str(root / "data"),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                    "LLMOPS_CACHE_HOME": str(root / "cache"),
                }
            )
            initialize(paths, preset="single-host", user="operator")
            document = load_template_registry(paths)["standalone"].as_dict()
            document.pop("source", None)
            document["id"] = "local-worker"
            document["defaults"]["template_id"] = "local-worker"
            document["profile_schema"]["properties"]["template_id"]["const"] = "local-worker"
            document["profile_schema"]["properties"]["template_id"]["default"] = "local-worker"
            source = root / "local-worker.json"
            source.write_text(json.dumps(document), encoding="utf-8")
            app = build_application(str(paths.config_home), None)
            async with app.run_test(size=(140, 44)) as pilot:
                await pilot.pause(1)
                await pilot.click("#action-catalog")
                await pilot.pause()
                await pilot.click("#import")
                await pilot.pause()
                app.screen.query_one("#template-import-path").value = str(source)
                await pilot.click("#review")
                await pilot.pause()
                self.assertIn(
                    "llmops template import",
                    str(app.screen.query_one("#equivalent-command").render()),
                )
                review = str(app.screen.query_one(".dialog-body").render())
                self.assertIn("local-worker.json", review)
                self.assertIn("authority hash", review)
                await pilot.click("#run")
                await pilot.pause(1)
            self.assertTrue((paths.templates_dir / "local-worker.json").is_file())

    async def test_confirmed_lifecycle_action_dispatches_without_blocking_tui(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = resolve_paths(
                {
                    "HOME": str(root),
                    "LLMOPS_CONFIG_HOME": str(root / "config"),
                    "LLMOPS_DATA_HOME": str(root / "data"),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                    "LLMOPS_CACHE_HOME": str(root / "cache"),
                }
            )
            initialize(paths, preset="single-host", user="operator")
            stack_path = paths.stacks_dir / "starter.json"
            stack = json.loads(stack_path.read_text(encoding="utf-8"))
            stack["components"][0]["enabled"] = True
            stack_path.write_text(json.dumps(stack, indent=2) + "\n", encoding="utf-8")
            app = build_application(str(paths.config_home), None)
            queued = {
                "operation_id": "20260721T120000Z-abcdef123456",
                "state": "queued",
            }
            with mock.patch("llmops_kit.llmops_tui.dispatch", return_value=queued) as detached:
                async with app.run_test(size=(140, 42)) as pilot:
                    await pilot.pause(1)
                    await pilot.click("#action-start")
                    await pilot.pause()
                    await pilot.click("#run")
                    await pilot.pause()
                    self.assertTrue(detached.called)
                    self.assertEqual(detached.call_args.kwargs["target"], "starter:chat")

    async def test_stop_requires_explicit_dependent_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = resolve_paths(
                {
                    "HOME": str(root),
                    "LLMOPS_CONFIG_HOME": str(root / "config"),
                    "LLMOPS_DATA_HOME": str(root / "data"),
                    "LLMOPS_STATE_HOME": str(root / "state"),
                    "LLMOPS_CACHE_HOME": str(root / "cache"),
                }
            )
            initialize(paths, preset="single-host", user="operator")
            stack_path = paths.stacks_dir / "starter.json"
            stack = json.loads(stack_path.read_text(encoding="utf-8"))
            for item in stack["components"]:
                item["enabled"] = True
            stack_path.write_text(json.dumps(stack, indent=2) + "\n", encoding="utf-8")
            app = build_application(str(paths.config_home), None)
            target = app.topology.resolve_component("chat")
            dependent = app.topology.resolve_component("model-proxy")
            prepared = MutationPlan((Operation(target, "stop"),), (dependent,))
            with mock.patch("llmops_kit.llmops_tui.Executor.prepare_component", return_value=prepared):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause(1)
                    await pilot.press("x")
                    await pilot.pause()
                    self.assertIsNotNone(app.screen.query_one("#impact-dialog"))
                    await pilot.click("#cancel")
                    await pilot.pause()


if __name__ == "__main__":
    unittest.main()
