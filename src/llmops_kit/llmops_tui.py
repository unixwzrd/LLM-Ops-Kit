"""On-demand Textual operations console for LLM-Ops-Kit."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Optional

from . import llmops_cli, llmops_update
from .llmops_config import update_display
from .llmops_drivers import ComponentRunner
from .llmops_executor import ExecutionError, Executor
from .llmops_topology import TopologyError
from .llmops_topology_view import project_topology
from .llmops_ui import UiPreferences, load_ui_preferences, resolve_ui_path, save_ui_preferences


CONDITION_STYLES = {
    "ok": "bold #43d17a",
    "attention": "bold #ffd166",
    "error": "bold #ff5c5c",
    "unobserved": "bold #55d8ff",
}


def equivalent_command(
    action: str,
    component: str,
    *,
    cascade: bool = False,
    force: bool = False,
) -> str:
    """Return the public CLI equivalent for a component mutation."""

    argv = ["llmops", "component", action, component]
    if cascade:
        argv.append("--cascade")
    if force:
        argv.append("--force")
    return shlex.join(argv)


def configure_command(component: str, changes: dict[str, Any]) -> str:
    """Render a reproducible component configuration command."""

    argv = ["llmops", "component", "configure", component]
    for key in ("host", "profile", "ownership"):
        if key in changes:
            argv.extend((f"--{key}", str(changes[key])))
    if "enabled" in changes:
        argv.append("--enable" if changes["enabled"] else "--disable")
    for dependency in changes.get("depends_on", []):
        argv.extend(("--depends-on", dependency))
    if "health_timeout" in changes:
        argv.extend(("--health-timeout", str(changes["health_timeout"])))
    argv.extend(("--apply", "--yes"))
    return shlex.join(argv)


def _textual_types() -> tuple[Any, ...]:
    try:
        from rich.text import Text
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical
        from textual.screen import ModalScreen
        from textual.widgets import Button, Checkbox, DataTable, Header, Input, Label, Select, Static, Tree
    except ImportError as exc:
        raise RuntimeError(
            "Textual is not installed; repair the normal installation or install the tui extra"
        ) from exc
    return (
        Text,
        App,
        ComposeResult,
        Horizontal,
        Vertical,
        ModalScreen,
        Button,
        Checkbox,
        DataTable,
        Header,
        Input,
        Label,
        Select,
        Static,
        Tree,
    )


def build_application(config_home: Optional[str], inventory: Optional[str]) -> Any:
    """Build the Textual application lazily so CLI-only installs remain dependency-free."""

    (
        Text,
        App,
        ComposeResult,
        Horizontal,
        Vertical,
        ModalScreen,
        Button,
        Checkbox,
        DataTable,
        Header,
        Input,
        Label,
        Select,
        Static,
        Tree,
    ) = _textual_types()

    class ConfirmOperation(ModalScreen[bool]):
        """Show a reproducible command and require explicit confirmation."""

        def __init__(self, command: str, plan: list[dict[str, str]]) -> None:
            super().__init__()
            self.command = command
            self.plan = plan

        def compose(self) -> ComposeResult:
            with Vertical(classes="dialog", id="confirm-dialog"):
                yield Label("Confirm operation", classes="dialog-title")
                yield Static(self.command, id="equivalent-command", classes="equivalent-command")
                yield Static(
                    "\n".join(f"{item['action']}  {item['component']}" for item in self.plan),
                    classes="dialog-body",
                )
                with Horizontal(classes="dialog-actions"):
                    yield Button("Cancel", id="cancel")
                    yield Button("Run", id="run", variant="error")

        def on_button_pressed(self, event: Any) -> None:
            self.dismiss(event.button.id == "run")

    class StopImpact(ModalScreen[str]):
        """Require an explicit policy when a stop has active dependents."""

        def __init__(self, component: str, dependents: list[str]) -> None:
            super().__init__()
            self.component = component
            self.dependents = dependents

        def compose(self) -> ComposeResult:
            with Vertical(classes="dialog", id="impact-dialog"):
                yield Label("Active dependents", classes="dialog-title")
                yield Static(
                    f"Stopping {self.component} may disrupt:\n\n"
                    + "\n".join(f"- {item}" for item in self.dependents),
                    classes="dialog-body",
                )
                with Horizontal(classes="dialog-actions"):
                    yield Button("Cancel", id="cancel")
                    yield Button("Cascade stop", id="cascade", variant="primary")
                    yield Button("Force target only", id="force", variant="error")

        def on_button_pressed(self, event: Any) -> None:
            self.dismiss(event.button.id)

    class EditComponent(ModalScreen[Optional[dict[str, Any]]]):
        """Guided editor for stable desired-state component fields."""

        def __init__(self, component: Any) -> None:
            super().__init__()
            self.component = component

        def compose(self) -> ComposeResult:
            with Vertical(classes="dialog", id="edit-dialog"):
                yield Label(f"Configure {self.component.qualified_id}", classes="dialog-title")
                yield Static(
                    "This changes desired state only; changing Host does not move files or services.",
                    classes="warning",
                )
                yield Label("Host")
                yield Input(value=self.component.host, id="edit-host")
                yield Label("Profile")
                yield Input(value=self.component.profile, id="edit-profile")
                yield Label("Ownership")
                yield Select(
                    (("Managed", "managed"), ("External", "external")),
                    value=self.component.ownership,
                    id="edit-ownership",
                )
                yield Checkbox("Enabled", value=self.component.enabled, id="edit-enabled")
                yield Label("Dependencies (comma-separated component IDs)")
                yield Input(value=", ".join(self.component.depends_on), id="edit-dependencies")
                yield Label("Health timeout seconds")
                yield Input(
                    value=str(self.component.health.timeout_seconds),
                    type="integer",
                    id="edit-timeout",
                )
                with Horizontal(classes="dialog-actions"):
                    yield Button("Cancel", id="cancel")
                    yield Button("Review", id="review", variant="primary")

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "cancel":
                self.dismiss(None)
                return
            dependencies = [
                item.strip()
                for item in self.query_one("#edit-dependencies", Input).value.split(",")
                if item.strip()
            ]
            self.dismiss(
                {
                    "host": self.query_one("#edit-host", Input).value.strip(),
                    "profile": self.query_one("#edit-profile", Input).value.strip(),
                    "ownership": self.query_one("#edit-ownership", Select).value,
                    "enabled": self.query_one("#edit-enabled", Checkbox).value,
                    "depends_on": dependencies,
                    "health_timeout": int(self.query_one("#edit-timeout", Input).value),
                }
            )

    class HelpScreen(ModalScreen[None]):
        """Display contextual operations and status help."""

        def compose(self) -> ComposeResult:
            with Vertical(classes="dialog", id="help-dialog"):
                yield Label("LLM-Ops-Kit Help", classes="dialog-title")
                yield Static(
                    "Navigation\n"
                    "  Up/Down or mouse  Select a component and update details\n"
                    "  v                 Toggle component and stack views\n"
                    "  t                 Open bounded topology view\n\n"
                    "Lifecycle\n"
                    "  s / x / b         Start, stop, or restart\n"
                    "  l                 Read recent component logs\n"
                    "  e                 Edit desired-state component fields\n\n"
                    "Operations\n"
                    "  r                 Refresh now\n"
                    "  ,                 Local TUI settings\n"
                    "  o                 Shared organization/site labels\n"
                    "  d                 Validate configuration\n"
                    "  u                 Check LLM-Ops-Kit updates\n\n"
                    "Conditions\n"
                    "  Green ok; amber attention; red error; cyan unobserved.\n"
                    "  Lifecycle, health, and observability are reported independently.\n"
                    "  authority-only means this host lacks an authorized observation route.\n\n"
                    "Every mutation displays its equivalent CLI command and ordered plan.",
                    classes="dialog-body",
                )
                yield Button("Close", id="close", variant="primary")

        def on_button_pressed(self, event: Any) -> None:
            self.dismiss(None)

    class SettingsScreen(ModalScreen[Optional[UiPreferences]]):
        """Edit host-local TUI preferences."""

        def __init__(self, preferences: UiPreferences) -> None:
            super().__init__()
            self.preferences = preferences

        def compose(self) -> ComposeResult:
            with Vertical(classes="dialog", id="settings-dialog"):
                yield Label("Local TUI Settings", classes="dialog-title")
                yield Checkbox(
                    "Automatic refresh",
                    value=self.preferences.auto_refresh,
                    id="settings-auto-refresh",
                )
                yield Label("Refresh interval seconds (minimum 2)")
                yield Input(
                    value=str(self.preferences.refresh_seconds),
                    type="integer",
                    id="settings-refresh-seconds",
                )
                yield Label("Theme")
                yield Select(
                    (("High contrast dark", "high-contrast-dark"),),
                    value=self.preferences.theme,
                    id="settings-theme",
                )
                with Horizontal(classes="dialog-actions"):
                    yield Button("Cancel", id="cancel")
                    yield Button("Save", id="save", variant="primary")

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "cancel":
                self.dismiss(None)
                return
            seconds = int(self.query_one("#settings-refresh-seconds", Input).value)
            if seconds < 2:
                self.query_one("#settings-refresh-seconds", Input).value = "2"
                return
            self.dismiss(
                UiPreferences(
                    auto_refresh=self.query_one("#settings-auto-refresh", Checkbox).value,
                    refresh_seconds=seconds,
                    theme=str(self.query_one("#settings-theme", Select).value),
                )
            )

    class BrandingScreen(ModalScreen[Optional[dict[str, str]]]):
        """Edit shared organization and site labels."""

        def __init__(self, display: dict[str, Any]) -> None:
            super().__init__()
            self.display = display

        def compose(self) -> ComposeResult:
            with Vertical(classes="dialog", id="branding-dialog"):
                yield Label("Shared Display Labels", classes="dialog-title")
                yield Label("Organization")
                yield Input(value=str(self.display.get("organization", "")), id="branding-organization")
                yield Label("Site")
                yield Input(value=str(self.display.get("site", "")), id="branding-site")
                with Horizontal(classes="dialog-actions"):
                    yield Button("Cancel", id="cancel")
                    yield Button("Review", id="review", variant="primary")

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "cancel":
                self.dismiss(None)
                return
            self.dismiss(
                {
                    "organization": self.query_one("#branding-organization", Input).value.strip(),
                    "site": self.query_one("#branding-site", Input).value.strip(),
                }
            )

    class TopologyScreen(ModalScreen[None]):
        """Show a bounded, filterable, host-grouped topology tree."""

        def __init__(self, topology: Any, status_by_id: dict[str, dict[str, Any]]) -> None:
            super().__init__()
            self.topology = topology
            self.status_by_id = status_by_id

        def compose(self) -> ComposeResult:
            with Vertical(id="topology-dialog"):
                yield Label("Service Topology", classes="dialog-title")
                with Horizontal(id="topology-filters"):
                    yield Input(placeholder="Host", id="topology-host")
                    yield Input(placeholder="Stack", id="topology-stack")
                    yield Input(placeholder="Driver", id="topology-driver")
                    yield Input(placeholder="Condition", id="topology-condition")
                    yield Button("Apply", id="apply", variant="primary")
                    yield Button("Close", id="close")
                yield Tree("Topology", id="topology-tree")
                yield Static("Select a component for relationships.", id="topology-detail")

        def on_mount(self) -> None:
            self.refresh_tree()

        def refresh_tree(self) -> None:
            host_filter = self.query_one("#topology-host", Input).value.strip()
            stack_filter = self.query_one("#topology-stack", Input).value.strip()
            driver_filter = self.query_one("#topology-driver", Input).value.strip()
            condition_filter = self.query_one("#topology-condition", Input).value.strip()
            projection = project_topology(
                self.topology,
                host=host_filter or None,
                stack=stack_filter or None,
                adapter=driver_filter or None,
            )
            tree = self.query_one("#topology-tree", Tree)
            tree.clear()
            by_host: dict[str, list[dict[str, Any]]] = {}
            for item in projection["components"]:
                state = self.status_by_id.get(item["id"], {})
                if condition_filter and state.get("condition") != condition_filter:
                    continue
                by_host.setdefault(item["host"], []).append(item)
            for host in sorted(by_host):
                host_node = tree.root.add(f"{host} ({len(by_host[host])})", expand=True)
                for item in sorted(by_host[host], key=lambda value: value["id"]):
                    state = self.status_by_id.get(item["id"], {})
                    condition = state.get("condition", "unobserved")
                    host_node.add_leaf(f"[{condition}] {item['id']}", data=item)
            tree.root.expand()

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "close":
                self.dismiss(None)
            elif event.button.id == "apply":
                self.refresh_tree()

        def on_tree_node_highlighted(self, event: Any) -> None:
            item = event.node.data
            if not isinstance(item, dict):
                return
            state = self.status_by_id.get(item["id"], {})
            self.query_one("#topology-detail", Static).update(
                f"{item['id']}\n"
                f"Host: {item['host']}  Driver: {item['driver']}\n"
                f"Condition: {state.get('condition', 'unobserved')}  "
                f"Lifecycle: {state.get('lifecycle', 'unknown')}  Health: {state.get('health', 'unknown')}\n"
                f"Dependencies: {', '.join(item['depends_on']) or 'none'}\n"
                f"Dependents: {', '.join(item['dependents']) or 'none'}"
            )

    class LlmOpsApp(App[None]):
        TITLE = "LLM-Ops-Kit"
        CSS = """
        Screen { background: #0b0f14; color: #f5f7fa; }
        Header { background: #14202b; color: #ffffff; text-style: bold; }
        #summary { height: 3; padding: 1 2; background: #111923; color: #f5f7fa; }
        #components { height: 1fr; background: #0b0f14; color: #f5f7fa; }
        #components > .datatable--header { background: #243444; color: #ffffff; text-style: bold; }
        #components > .datatable--cursor { background: #075e68; color: #ffffff; text-style: bold; }
        #detail { height: 10; border-top: solid #55d8ff; padding: 1 2; overflow-y: auto; background: #0f151d; color: #f5f7fa; }
        #action-bar { height: 3; padding: 1 2; background: #1b2733; color: #ffffff; text-style: bold; }
        .dialog { width: 78; height: auto; max-height: 92%; padding: 1 2; border: thick #55d8ff; background: #111923; color: #ffffff; }
        .dialog-title { text-style: bold; color: #55d8ff; margin-bottom: 1; }
        .dialog-body { color: #f5f7fa; overflow-y: auto; }
        .dialog-actions { height: 3; margin-top: 1; }
        .equivalent-command { margin: 1 0; color: #9fe870; background: #0b0f14; padding: 1; }
        .warning { color: #ffd166; margin-bottom: 1; }
        Button { margin-right: 1; }
        Input, Select { background: #18222d; color: #ffffff; border: tall #557086; }
        Checkbox { color: #ffffff; }
        #topology-dialog { width: 95%; height: 95%; padding: 1 2; border: thick #55d8ff; background: #0b0f14; }
        #topology-filters { height: 5; }
        #topology-filters Input { width: 1fr; margin-right: 1; }
        #topology-tree { height: 1fr; background: #0f151d; color: #f5f7fa; }
        #topology-detail { height: 8; border-top: solid #55d8ff; padding: 1; }
        """
        BINDINGS = [
            ("r", "refresh", "Refresh"),
            ("s", "start", "Start"),
            ("x", "stop", "Stop"),
            ("b", "restart", "Restart"),
            ("l", "logs", "Logs"),
            ("e", "edit", "Configure"),
            ("v", "toggle_view", "Components/Stacks"),
            ("t", "topology", "Topology"),
            ("comma", "settings", "Settings"),
            ("o", "branding", "Display labels"),
            ("?", "help", "Help"),
            ("u", "update_check", "Toolkit update check"),
            ("ctrl+u", "update_apply", "Apply toolkit update"),
            ("d", "doctor", "Doctor"),
            ("q", "quit", "Quit"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.topology = llmops_cli.build_topology(config_home=config_home, inventory=inventory)
            llmops_cli.CURRENT_TOPOLOGY = self.topology
            self.desired_topology = llmops_cli.desired_topology(config_home)
            self.rows: list[Any] = []
            self.view = "components"
            self.status_by_id: dict[str, dict[str, Any]] = {}
            self.ui_path = Path(config_home).expanduser() / "ui.json" if config_home else resolve_ui_path()
            self.preferences = load_ui_preferences(self.ui_path)
            self.refresh_timer: Any = None
            self.mutating = False
            self._apply_branding()

        def _apply_branding(self) -> None:
            display = self.desired_topology.config.data.get("display", {})
            labels = [str(display.get(key, "")).strip() for key in ("organization", "site")]
            self.sub_title = " | ".join(label for label in labels if label)

        def compose(self) -> ComposeResult:
            yield Header()
            yield Static("Loading topology...", id="summary")
            yield DataTable(id="components", cursor_type="row", zebra_stripes=False)
            yield Static("Select a component for details.", id="detail")
            yield Static(
                "[b]r[/b] Refresh  [b]s[/b] Start  [b]x[/b] Stop  [b]b[/b] Restart  "
                "[b]l[/b] Logs  [b]t[/b] Topology  [b]?[/b] Help  [b]q[/b] Quit",
                id="action-bar",
                markup=True,
            )

        def on_mount(self) -> None:
            table = self.query_one("#components", DataTable)
            table.add_columns(
                "Condition",
                "Lifecycle",
                "Health",
                "Component",
                "Host",
                "Driver",
                "Version",
                "Drift",
            )
            self._reset_refresh_timer()
            self.action_refresh()

        def _reset_refresh_timer(self) -> None:
            if self.refresh_timer is not None:
                self.refresh_timer.stop()
            self.refresh_timer = self.set_interval(
                self.preferences.refresh_seconds,
                self._automatic_refresh,
            )

        def _automatic_refresh(self) -> None:
            if self.preferences.auto_refresh and not self.mutating and len(self.screen_stack) == 1:
                self.action_refresh()

        def selected_component(self) -> Optional[Any]:
            table = self.query_one("#components", DataTable)
            if table.cursor_row < 0 or table.cursor_row >= len(self.rows):
                return None
            return self.rows[table.cursor_row]

        def _selected_id(self) -> str:
            selected = self.selected_component()
            if selected is None:
                return ""
            return selected.qualified_id if hasattr(selected, "qualified_id") else selected.name

        def _show_detail(self, item: Any) -> None:
            if hasattr(item, "component_id"):
                state = self.status_by_id.get(item.qualified_id, {})
                detail = (
                    f"{item.qualified_id}\n"
                    f"Host: {item.host}  Driver: {item.driver}  Profile: {item.profile}\n"
                    f"Condition: {state.get('condition', 'unobserved')}  "
                    f"Lifecycle: {state.get('lifecycle', 'unknown')}  "
                    f"Health: {state.get('health', 'unknown')}  "
                    f"Observability: {state.get('observability', 'unknown')}\n"
                    f"Component version: {state.get('component_version') or 'unknown'}  "
                    f"Toolkit version: {state.get('toolkit_version') or 'unknown'}  "
                    f"Drift: {state.get('drift', 'unknown')}\n"
                    f"Dependencies: {', '.join(item.depends_on) or 'none'}  Ownership: {item.ownership}"
                )
            else:
                detail = f"{item.name}\nComponents:\n" + "\n".join(
                    f"  {component.qualified_id}" for component in item.components.values()
                )
            self.query_one("#detail", Static).update(detail)

        async def inspect(self) -> None:
            selected_id = self._selected_id()
            args = argparse.Namespace(
                selector=None,
                all=True,
                verbose=False,
                workers=8,
                host_timeout=20,
                status_host=None,
                local=False,
            )
            payload = await asyncio.to_thread(llmops_cli._collect_status, args)
            self.status_by_id = {item["component"]: item for item in payload}
            self.rows = (
                self.topology.all_components()
                if self.view == "components"
                else [self.topology.stacks[name] for name in sorted(self.topology.stacks)]
            )
            table = self.query_one("#components", DataTable)
            table.clear()
            if self.view == "components":
                for component in self.rows:
                    item = self.status_by_id[component.qualified_id]
                    style = CONDITION_STYLES.get(item["condition"], "#f5f7fa")
                    values = (
                        item["condition"],
                        item["lifecycle"],
                        item["health"],
                        component.qualified_id,
                        component.host,
                        component.driver,
                        item.get("component_version", ""),
                        item.get("drift", ""),
                    )
                    table.add_row(*(Text(str(value), style=style) for value in values))
            else:
                for stack in self.rows:
                    states = [
                        self.status_by_id[item.qualified_id]["condition"]
                        for item in stack.components.values()
                    ]
                    condition = (
                        "error"
                        if "error" in states
                        else "attention"
                        if "attention" in states
                        else "unobserved"
                        if "unobserved" in states
                        else "ok"
                    )
                    style = CONDITION_STYLES[condition]
                    values = (
                        condition,
                        "group",
                        "mixed",
                        stack.name,
                        "multiple",
                        "stack",
                        "",
                        "",
                    )
                    table.add_row(*(Text(str(value), style=style) for value in values))
            if self.rows:
                index = next(
                    (
                        index
                        for index, row in enumerate(self.rows)
                        if (row.qualified_id if hasattr(row, "qualified_id") else row.name) == selected_id
                    ),
                    0,
                )
                table.move_cursor(row=index)
                self._show_detail(self.rows[index])
            counts: dict[str, int] = {}
            for item in payload:
                counts[item["condition"]] = counts.get(item["condition"], 0) + 1
            summary = "  ".join(f"{key}={counts[key]}" for key in sorted(counts))
            self.query_one("#summary", Static).update(
                f"Hosts {len(self.topology.hosts)}  Components {len(payload)}  {summary}"
            )

        def action_refresh(self) -> None:
            if not self.mutating:
                self.run_worker(self.inspect(), exclusive=True)

        async def run_mutation(self, action: str, target: Any) -> None:
            self.mutating = True
            try:
                if hasattr(target, "component_id"):
                    executor = Executor(self.topology)
                    cascade = False
                    force = False
                    prepared = await asyncio.to_thread(executor.prepare_component, target, action)
                    if prepared.requires_force:
                        choice = await self.push_screen_wait(
                            StopImpact(
                                target.qualified_id,
                                [item.qualified_id for item in prepared.active_dependents],
                            )
                        )
                        if choice == "cancel":
                            return
                        cascade = choice == "cascade"
                        force = choice == "force"
                        prepared = await asyncio.to_thread(
                            executor.prepare_component,
                            target,
                            action,
                            cascade=cascade,
                        )
                    operations = list(prepared.operations)
                    command = equivalent_command(
                        action,
                        target.qualified_id,
                        cascade=cascade,
                        force=force,
                    )
                else:
                    operations = llmops_cli.stack_plan(target, action)
                    command = f"llmops stack {action} {target.name}"
                    executor = Executor(self.topology)
                    cascade = False
                    force = False
                plan = llmops_cli.operation_payload(operations)
                approved = await self.push_screen_wait(ConfirmOperation(command, plan))
                if not approved:
                    return
                if hasattr(target, "component_id"):
                    results = await asyncio.to_thread(
                        executor.execute_component,
                        target,
                        action,
                        cascade=cascade,
                        force=force,
                    )
                else:
                    results = await asyncio.to_thread(executor.execute, operations)
                self.query_one("#detail", Static).update(
                    json.dumps([item.as_dict() for item in results], indent=2)
                )
            except (ExecutionError, TopologyError) as exc:
                self.query_one("#detail", Static).update(str(exc))
            finally:
                self.mutating = False
                await self.inspect()

        def _mutate(self, action: str) -> None:
            target = self.selected_component()
            if target is not None:
                self.run_worker(self.run_mutation(action, target), exclusive=True)

        def action_start(self) -> None:
            self._mutate("start")

        def action_stop(self) -> None:
            self._mutate("stop")

        def action_restart(self) -> None:
            self._mutate("restart")

        async def show_logs(self, component: Any) -> None:
            result = await asyncio.to_thread(ComponentRunner(self.topology).run, component, "logs")
            self.query_one("#detail", Static).update(result.stdout or result.stderr or "No log output")

        def action_logs(self) -> None:
            component = self.selected_component()
            if component is not None and hasattr(component, "component_id"):
                self.run_worker(self.show_logs(component), exclusive=True)

        async def edit_component(self, component: Any) -> None:
            changes = await self.push_screen_wait(EditComponent(component))
            if changes is None:
                return
            llmops_cli.configure_component(
                component,
                changes,
                apply=False,
                topology=self.desired_topology,
            )
            command = configure_command(component.qualified_id, changes)
            approved = await self.push_screen_wait(
                ConfirmOperation(command, [{"action": "configure", "component": component.qualified_id}])
            )
            if not approved:
                return
            result = await asyncio.to_thread(
                llmops_cli.configure_component,
                component,
                changes,
                apply=True,
                topology=self.desired_topology,
            )
            self.query_one("#detail", Static).update(json.dumps(result, indent=2, sort_keys=True))
            self.desired_topology = llmops_cli.desired_topology(config_home)
            await self.inspect()

        def action_edit(self) -> None:
            component = self.selected_component()
            if component is not None and hasattr(component, "component_id"):
                desired = self.desired_topology.resolve_component(component.qualified_id)
                self.run_worker(self.edit_component(desired), exclusive=True)

        def action_toggle_view(self) -> None:
            self.view = "stacks" if self.view == "components" else "components"
            self.action_refresh()

        def action_topology(self) -> None:
            self.push_screen(TopologyScreen(self.topology, self.status_by_id))

        def action_help(self) -> None:
            self.push_screen(HelpScreen())

        async def edit_settings(self) -> None:
            preferences = await self.push_screen_wait(SettingsScreen(self.preferences))
            if preferences is None:
                return
            save_ui_preferences(self.ui_path, preferences)
            self.preferences = preferences
            self._reset_refresh_timer()
            self.query_one("#detail", Static).update("Local TUI settings saved")

        def action_settings(self) -> None:
            self.run_worker(self.edit_settings(), exclusive=True)

        async def edit_branding(self) -> None:
            display = self.desired_topology.config.data.get("display", {})
            changes = await self.push_screen_wait(BrandingScreen(display))
            if changes is None:
                return
            argv = [
                "llmops",
                "config",
                "display",
                "--organization",
                changes["organization"],
                "--site",
                changes["site"],
                "--apply",
                "--yes",
            ]
            command = shlex.join(argv)
            approved = await self.push_screen_wait(
                ConfirmOperation(command, [{"action": "configure", "component": "shared display"}])
            )
            if not approved:
                return
            backup = update_display(self.desired_topology.paths.config_file, **changes)
            self.desired_topology = llmops_cli.desired_topology(config_home)
            self._apply_branding()
            self.query_one("#detail", Static).update(
                f"Shared display labels saved; backup={backup if backup.exists() else 'none'}"
            )

        def action_branding(self) -> None:
            self.run_worker(self.edit_branding(), exclusive=True)

        async def check_update(self) -> None:
            install_base = Path(sys.executable).absolute().parents[4]
            current = llmops_update.current_version(install_base)
            try:
                available = await asyncio.to_thread(
                    llmops_update.resolve_latest,
                    "unixwzrd/LLM-Ops-Kit",
                )
                detail = {
                    "scope": "LLM-Ops-Kit toolkit",
                    "current": current,
                    "available": available,
                    "update_available": current != available,
                }
            except llmops_update.UpdateError as exc:
                detail = {"scope": "LLM-Ops-Kit toolkit", "current": current, "error": str(exc)}
            self.query_one("#detail", Static).update(json.dumps(detail, indent=2, sort_keys=True))

        def action_update_check(self) -> None:
            self.run_worker(self.check_update(), exclusive=True)

        async def apply_update(self) -> None:
            approved = await self.push_screen_wait(
                ConfirmOperation(
                    "llmops update --apply",
                    [{"action": "update", "component": "LLM-Ops-Kit toolkit"}],
                )
            )
            if not approved:
                return
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                code = await asyncio.to_thread(llmops_update.main, ["--apply"])
            self.query_one("#detail", Static).update(f"exit={code}\n{output.getvalue()}")

        def action_update_apply(self) -> None:
            self.run_worker(self.apply_update(), exclusive=True)

        def action_doctor(self) -> None:
            errors = llmops_cli.validate_topology(self.topology)
            self.query_one("#detail", Static).update(
                "Configuration valid" if not errors else "\n".join(errors)
            )

        def on_data_table_row_highlighted(self, event: Any) -> None:
            if 0 <= event.cursor_row < len(self.rows):
                self._show_detail(self.rows[event.cursor_row])

        def on_data_table_row_selected(self, event: Any) -> None:
            if 0 <= event.cursor_row < len(self.rows):
                self._show_detail(self.rows[event.cursor_row])

    return LlmOpsApp()


def main(argv: Optional[list[str]] = None) -> int:
    """Run the on-demand terminal application."""

    parser = argparse.ArgumentParser(description="Open the LLM-Ops-Kit Textual console")
    parser.add_argument("--config-home")
    parser.add_argument("--inventory")
    args = parser.parse_args(argv)
    try:
        build_application(args.config_home, args.inventory).run()
    except RuntimeError as exc:
        print(f"llmops tui: {exc}")
        return 2
    return 0
