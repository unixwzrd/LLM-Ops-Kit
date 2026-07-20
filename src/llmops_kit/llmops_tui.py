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

from . import llmops_cli
from . import llmops_update
from .llmops_drivers import ComponentRunner
from .llmops_executor import ExecutionError, Executor, component_plan
from .llmops_topology import TopologyError


def equivalent_command(action: str, component: str) -> str:
    """Return the public CLI equivalent for a component mutation."""

    return f"llmops component {action} {component}"


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
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical
        from textual.screen import ModalScreen
        from textual.widgets import Button, Checkbox, DataTable, Footer, Header, Input, Label, Select, Static
    except ImportError as exc:
        raise RuntimeError("Textual is not installed; repair the normal installation or install the tui extra") from exc
    return App, ComposeResult, Horizontal, Vertical, ModalScreen, Button, Checkbox, DataTable, Footer, Header, Input, Label, Select, Static


def build_application(config_home: Optional[str], inventory: Optional[str]) -> Any:
    """Build the Textual application lazily so CLI-only installs remain dependency-free."""

    App, ComposeResult, Horizontal, Vertical, ModalScreen, Button, Checkbox, DataTable, Footer, Header, Input, Label, Select, Static = _textual_types()

    class ConfirmOperation(ModalScreen[bool]):
        """Show a reproducible command and require explicit confirmation."""

        def __init__(self, command: str, plan: list[dict[str, str]]) -> None:
            super().__init__()
            self.command = command
            self.plan = plan

        def compose(self) -> ComposeResult:
            with Vertical(id="confirm-dialog"):
                yield Label("Confirm operation")
                yield Static(self.command, id="equivalent-command")
                yield Static("\n".join(f"{item['action']}  {item['component']}" for item in self.plan))
                with Horizontal():
                    yield Button("Cancel", id="cancel")
                    yield Button("Run", id="run", variant="error")

        def on_button_pressed(self, event: Any) -> None:
            self.dismiss(event.button.id == "run")

    class EditComponent(ModalScreen[Optional[dict[str, Any]]]):
        """Guided editor for stable component fields."""

        def __init__(self, component: Any) -> None:
            super().__init__()
            self.component = component

        def compose(self) -> ComposeResult:
            with Vertical(id="edit-dialog"):
                yield Label(f"Configure {self.component.qualified_id}")
                yield Label("Host")
                yield Input(value=self.component.host, id="edit-host")
                yield Label("Profile")
                yield Input(value=self.component.profile, id="edit-profile")
                yield Label("Ownership")
                yield Select((("Managed", "managed"), ("External", "external")), value=self.component.ownership, id="edit-ownership")
                yield Checkbox("Enabled", value=self.component.enabled, id="edit-enabled")
                yield Label("Dependencies (comma-separated component IDs)")
                yield Input(value=", ".join(self.component.depends_on), id="edit-dependencies")
                yield Label("Health timeout seconds")
                yield Input(value=str(self.component.health.timeout_seconds), type="integer", id="edit-timeout")
                with Horizontal():
                    yield Button("Cancel", id="cancel")
                    yield Button("Review", id="review", variant="primary")

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "cancel":
                self.dismiss(None)
                return
            dependencies = [item.strip() for item in self.query_one("#edit-dependencies", Input).value.split(",") if item.strip()]
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

    class LlmOpsApp(App[None]):
        CSS = """
        #summary { height: 3; padding: 1 2; }
        #components { height: 1fr; }
        #detail { height: 10; border-top: solid $accent; padding: 1 2; overflow-y: auto; }
        #confirm-dialog, #edit-dialog { width: 76; height: auto; max-height: 90%; padding: 1 2; border: thick $accent; background: $surface; }
        #equivalent-command { margin: 1 0; color: $text-accent; }
        Button { margin-right: 1; }
        """
        BINDINGS = [
            ("r", "refresh", "Refresh"),
            ("s", "start", "Start"),
            ("x", "stop", "Stop"),
            ("b", "restart", "Restart"),
            ("l", "logs", "Logs"),
            ("e", "edit", "Configure"),
            ("v", "toggle_view", "Components/Stacks"),
            ("u", "update_check", "Update check"),
            ("ctrl+u", "update_apply", "Apply update"),
            ("d", "doctor", "Doctor"),
            ("q", "quit", "Quit"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.topology = llmops_cli.build_topology(config_home=config_home, inventory=inventory)
            llmops_cli.CURRENT_TOPOLOGY = self.topology
            self.rows: list[Any] = []
            self.view = "components"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Static("Loading topology...", id="summary")
            yield DataTable(id="components", cursor_type="row", zebra_stripes=True)
            yield Static("Select a component for details.", id="detail")
            yield Footer()

        def on_mount(self) -> None:
            table = self.query_one("#components", DataTable)
            table.add_columns("Status", "Component", "Host", "Driver", "Profile", "Version", "Drift")
            self.action_refresh()

        def selected_component(self) -> Optional[Any]:
            table = self.query_one("#components", DataTable)
            if table.cursor_row < 0 or table.cursor_row >= len(self.rows):
                return None
            return self.rows[table.cursor_row]

        async def inspect(self) -> None:
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
            by_id = {item["component"]: item for item in payload}
            components = self.topology.all_components()
            self.rows = components if self.view == "components" else [self.topology.stacks[name] for name in sorted(self.topology.stacks)]
            table = self.query_one("#components", DataTable)
            table.clear()
            if self.view == "components":
                for component in self.rows:
                    item = by_id[component.qualified_id]
                    table.add_row(item["status"], component.qualified_id, component.host, component.driver, component.profile, item.get("version", ""), item.get("drift", ""))
            else:
                for stack in self.rows:
                    states = [by_id[item.qualified_id]["status"] for item in stack.components.values()]
                    state = "running" if states and all(item == "running" for item in states) else "disabled" if states and all(item == "disabled" for item in states) else "mixed"
                    table.add_row(state, stack.name, "multiple", "stack", f"{len(stack.components)} components", "", "")
            counts: dict[str, int] = {}
            for item in payload:
                counts[item["status"]] = counts.get(item["status"], 0) + 1
            summary = "  ".join(f"{key}={counts[key]}" for key in sorted(counts))
            self.query_one("#summary", Static).update(f"Hosts {len(self.topology.hosts)}  Components {len(payload)}  {summary}")

        def action_refresh(self) -> None:
            self.run_worker(self.inspect(), exclusive=True)

        async def run_mutation(self, action: str, component: Any) -> None:
            try:
                if hasattr(component, "component_id"):
                    operations = component_plan(self.topology, component, action)
                    command = equivalent_command(action, component.qualified_id)
                else:
                    operations = llmops_cli.stack_plan(component, action)
                    command = f"llmops stack {action} {component.name}"
            except TopologyError as exc:
                self.query_one("#detail", Static).update(str(exc))
                return
            plan = llmops_cli.operation_payload(operations)
            approved = await self.push_screen_wait(ConfirmOperation(command, plan))
            if not approved:
                return
            executor = Executor(self.topology)
            try:
                results = await asyncio.to_thread(executor.execute, operations)
            except (ExecutionError, TopologyError) as exc:
                self.query_one("#detail", Static).update(str(exc))
                return
            self.query_one("#detail", Static).update(json.dumps([item.as_dict() for item in results], indent=2))
            await self.inspect()

        def _mutate(self, action: str) -> None:
            component = self.selected_component()
            if component is not None:
                self.run_worker(self.run_mutation(action, component), exclusive=True)

        def action_start(self) -> None:
            self._mutate("start")

        def action_stop(self) -> None:
            self._mutate("stop")

        def action_restart(self) -> None:
            self._mutate("restart")

        def action_logs(self) -> None:
            component = self.selected_component()
            if component is None or not hasattr(component, "component_id"):
                return
            result = ComponentRunner(self.topology).run(component, "logs")
            self.query_one("#detail", Static).update(result.stdout or result.stderr or "No log output")

        async def edit_component(self, component: Any) -> None:
            changes = await self.push_screen_wait(EditComponent(component))
            if changes is None:
                return
            plan = llmops_cli.configure_component(component, changes, apply=False)
            command = configure_command(component.qualified_id, changes)
            approved = await self.push_screen_wait(ConfirmOperation(command, [{"action": "configure", "component": component.qualified_id}]))
            if not approved:
                return
            result = await asyncio.to_thread(llmops_cli.configure_component, component, changes, apply=True)
            self.query_one("#detail", Static).update(json.dumps(result, indent=2, sort_keys=True))
            self.topology = llmops_cli.build_topology(config_home=config_home, inventory=inventory)
            llmops_cli.CURRENT_TOPOLOGY = self.topology
            await self.inspect()

        def action_edit(self) -> None:
            component = self.selected_component()
            if component is not None and hasattr(component, "component_id"):
                self.run_worker(self.edit_component(component), exclusive=True)

        def action_toggle_view(self) -> None:
            self.view = "stacks" if self.view == "components" else "components"
            self.action_refresh()

        async def check_update(self) -> None:
            install_base = Path(sys.executable).absolute().parents[4]
            current = llmops_update.current_version(install_base)
            try:
                available = await asyncio.to_thread(llmops_update.resolve_latest, "unixwzrd/LLM-Ops-Kit")
                detail = {"current": current, "available": available, "update_available": current != available}
            except llmops_update.UpdateError as exc:
                detail = {"current": current, "error": str(exc)}
            self.query_one("#detail", Static).update(json.dumps(detail, indent=2, sort_keys=True))

        def action_update_check(self) -> None:
            self.run_worker(self.check_update(), exclusive=True)

        async def apply_update(self) -> None:
            approved = await self.push_screen_wait(ConfirmOperation("llmops update --apply", [{"action": "update", "component": "local toolkit"}]))
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
            self.query_one("#detail", Static).update("Configuration valid" if not errors else "\n".join(errors))

        def on_data_table_row_selected(self, event: Any) -> None:
            component = self.rows[event.cursor_row]
            if hasattr(component, "component_id"):
                detail = f"{component.qualified_id}\nHost: {component.host}\nDriver: {component.driver}\nProfile: {component.profile}\nDependencies: {', '.join(component.depends_on) or 'none'}\nOwnership: {component.ownership}"
            else:
                detail = f"{component.name}\nComponents:\n" + "\n".join(f"  {item.qualified_id}" for item in component.components.values())
            self.query_one("#detail", Static).update(detail)

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
