"""On-demand Textual operations console for LLM-Ops-Kit."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Optional

from . import llmops_cli, llmops_update
from .llmops_config import update_display
from .llmops_config_ops import (
    ConfigOperationError,
    clone_component,
    component_field_records,
    configure_component_schema,
    field_records,
    import_template,
    provision_component,
    retire_component,
)
from .llmops_drivers import ComponentRunner
from .llmops_executor import ExecutionError, Executor
from .llmops_operations import ACTIVE_STATES, dispatch, list_records
from .llmops_topology import TopologyError
from .llmops_topology_view import project_topology
from .llmops_templates import (
    TemplateError,
    load_template_registry,
    parse_schema_value,
    schema_node,
    set_dotted,
)
from .llmops_ui import (
    CONDITION_STYLES,
    UiPreferences,
    load_ui_preferences,
    resolve_ui_path,
    save_ui_preferences,
    status_cell_style,
)


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


def schema_configure_command(
    component: str,
    assignments: list[str],
    unsets: list[str],
    *,
    expected_hash: str = "",
    restart_affected: bool = False,
) -> str:
    """Render one schema-aware component mutation for review and automation."""

    argv = ["llmops", "component", "configure", component]
    for assignment in assignments:
        argv.extend(("--set", assignment))
    for path in unsets:
        argv.extend(("--unset", path))
    if expected_hash:
        argv.extend(("--expected-hash", expected_hash))
    if restart_affected:
        argv.append("--restart-affected")
    argv.extend(("--apply", "--yes"))
    return shlex.join(argv)


def _flatten_values(value: dict[str, Any], prefix: str = "profile") -> list[str]:
    assignments: list[str] = []
    for key, child in sorted(value.items()):
        path = f"{prefix}.{key}"
        if isinstance(child, dict):
            assignments.extend(_flatten_values(child, path))
        else:
            encoded = json.dumps(child, separators=(",", ":")) if isinstance(child, (list, dict)) else str(child).lower() if isinstance(child, bool) else str(child)
            assignments.append(f"{path}={encoded}")
    return assignments


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

    def field_title(row: dict[str, Any]) -> str:
        """Return a human label while retaining the dotted path as secondary help."""

        return str(
            row.get("label")
            or row["path"].rsplit(".", 1)[-1].replace("_", " ").title()
        )

    def display_schema_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        return str(value)

    def display_widget_value(row: dict[str, Any], value: Any) -> str:
        """Render structured values in an operator-oriented form."""

        if row.get("widget") == "argv" and isinstance(value, list):
            return shlex.join(str(item) for item in value)
        if row.get("type") == "object" and isinstance(value, dict):
            tokens = []
            for key, child in sorted(value.items()):
                rendered = child if isinstance(child, str) else json.dumps(child, separators=(",", ":"))
                tokens.append(f"{key}={rendered}")
            return shlex.join(tokens)
        return display_schema_value(value)

    def parse_widget_value(row: dict[str, Any], node: dict[str, Any], raw: str) -> Any:
        """Parse Textual form syntax before shared JSON Schema validation."""

        if row.get("widget") == "argv":
            return parse_schema_value(node, json.dumps(shlex.split(raw)))
        if row.get("type") == "object":
            mapping: dict[str, Any] = {}
            for token in shlex.split(raw):
                key, separator, value = token.partition("=")
                if not separator or not key:
                    raise TemplateError("Expected space-separated KEY=value entries")
                try:
                    mapping[key] = json.loads(value)
                except json.JSONDecodeError:
                    mapping[key] = value
            return parse_schema_value(node, json.dumps(mapping, separators=(",", ":")))
        return parse_schema_value(node, raw)

    def schema_widget(row: dict[str, Any], value: Any, widget_id: str) -> Any:
        """Build the supported Textual control declared by one schema field."""

        if row.get("type") == "boolean" or row.get("widget") == "checkbox":
            return Checkbox("Enabled", value=bool(value), id=widget_id)
        if row.get("allowed"):
            options = tuple((str(item), item) for item in row["allowed"])
            selected = value if value in row["allowed"] else row["allowed"][0]
            return Select(options, value=selected, id=widget_id)
        input_type = "integer" if row.get("type") == "integer" else "number" if row.get("type") == "number" else "text"
        return Input(
            value=display_widget_value(row, value),
            type=input_type,
            placeholder=str(
                row.get("placeholder")
                or ("/path/to/program --flag value" if row.get("widget") == "argv" else "")
                or ("KEY=value OTHER='value with spaces'" if row.get("type") == "object" else "")
            ),
            id=widget_id,
        )

    def widget_raw(screen: Any, row: dict[str, Any], widget_id: str) -> str:
        if row.get("type") == "boolean" or row.get("widget") == "checkbox":
            return "true" if screen.query_one(f"#{widget_id}", Checkbox).value else "false"
        if row.get("allowed"):
            return str(screen.query_one(f"#{widget_id}", Select).value)
        return screen.query_one(f"#{widget_id}", Input).value.strip()

    def set_widget_value(screen: Any, row: dict[str, Any], widget_id: str, value: Any) -> None:
        if row.get("type") == "boolean" or row.get("widget") == "checkbox":
            screen.query_one(f"#{widget_id}", Checkbox).value = bool(value)
        elif row.get("allowed"):
            allowed = row["allowed"]
            screen.query_one(f"#{widget_id}", Select).value = value if value in allowed else allowed[0]
        else:
            screen.query_one(f"#{widget_id}", Input).value = display_widget_value(row, value)

    class ConfirmOperation(ModalScreen[bool]):
        """Show a reproducible command and require explicit confirmation."""

        BINDINGS = [("escape", "cancel", "Cancel")]

        def __init__(
            self,
            command: str,
            plan: list[dict[str, Any]],
            *,
            title: str = "Confirm operation",
            confirm_label: str = "Run",
            confirm_variant: str = "error",
        ) -> None:
            super().__init__()
            self.command = command
            self.plan = plan
            self.dialog_title = title
            self.confirm_label = confirm_label
            self.confirm_variant = confirm_variant

        def compose(self) -> ComposeResult:
            lines: list[str] = []
            for item in self.plan:
                lines.append(f"{item['action']}  {item['component']}")
                for key, value in item.items():
                    if key in {"action", "component"}:
                        continue
                    rendered = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
                    lines.append(f"  {key.replace('_', ' ')}: {rendered}")
            with Vertical(classes="dialog", id="confirm-dialog"):
                yield Label(self.dialog_title, classes="dialog-title")
                yield Static(self.command, id="equivalent-command", classes="equivalent-command")
                yield Static(
                    "\n".join(lines),
                    classes="dialog-body",
                )
                with Horizontal(classes="dialog-actions"):
                    yield Button("Cancel", id="cancel")
                    yield Button(self.confirm_label, id="run", variant=self.confirm_variant)

        def on_button_pressed(self, event: Any) -> None:
            self.dismiss(event.button.id == "run")

        def action_cancel(self) -> None:
            self.dismiss(False)

    class StopImpact(ModalScreen[str]):
        """Require an explicit policy when a stop has active dependents."""

        BINDINGS = [("escape", "cancel", "Cancel")]

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

        def action_cancel(self) -> None:
            self.dismiss("cancel")

    class SchemaEditComponent(ModalScreen[Optional[dict[str, Any]]]):
        """Edit one component through grouped, schema-derived controls."""

        BINDINGS = [("escape", "cancel", "Cancel")]

        def __init__(self, topology: Any, component: Any) -> None:
            super().__init__()
            self.topology = topology
            self.component = component
            self.rows = [
                row
                for row in component_field_records(topology, component.qualified_id)
                if not row.get("read_only")
            ]
            registry = load_template_registry(topology.paths)
            template = registry[component.template_id]
            profile_root = {
                "model": topology.paths.models_dir,
                "agent": topology.paths.agents_dir,
            }.get(template.profile_kind, topology.paths.services_dir)
            compatible_profiles = []
            for path in sorted(profile_root.glob("*.json")) if profile_root.is_dir() else []:
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if document.get("template_id") == component.template_id:
                    compatible_profiles.append(path.stem)
            components = [item.qualified_id for item in topology.all_components()]
            for row in self.rows:
                if row["path"] == "component.host":
                    row["allowed"] = sorted(topology.hosts)
                elif row["path"] == "component.profile":
                    row["allowed"] = compatible_profiles
                elif row["path"].startswith("connections.") and row["path"].endswith(".component"):
                    row["allowed"] = components
                elif row["path"].startswith("connections.") and row["path"].endswith(".endpoint"):
                    connection_name = row["path"].split(".")[1]
                    target_ref = component.connections.get(connection_name, {}).get("component", "")
                    try:
                        provider = topology.resolve_component(target_ref)
                    except TopologyError:
                        continue
                    provider_template = registry.get(provider.template_id)
                    if provider_template is not None:
                        row["allowed"] = sorted(provider_template.endpoints.get("provides", {}))
            self.initial_values = [self._initial_value(row) for row in self.rows]
            self.groups = list(dict.fromkeys(str(row.get("group") or "General") for row in self.rows))
            self.advanced_visible = False
            self.shared_components = sorted(
                item.qualified_id
                for item in topology.all_components()
                if item.profile == component.profile and item.qualified_id != component.qualified_id
            )

        @staticmethod
        def _initial_value(row: dict[str, Any]) -> Any:
            value = row.get("current")
            if value is None:
                value = row.get("default")
            allowed = row.get("allowed")
            if allowed and value not in allowed:
                return allowed[0]
            return value

        def compose(self) -> ComposeResult:
            with Vertical(classes="dialog schema-dialog", id="schema-edit-dialog"):
                yield Label(f"Configure {self.component.qualified_id}", classes="dialog-title")
                yield Static(
                    "Saved changes are persistent and remain active after future restarts. "
                    "Host changes update desired state only; they do not relocate executables, models, or data.",
                    classes="warning",
                )
                if self.shared_components:
                    yield Static(
                        "Shared profile. Saving profile fields also affects: "
                        + ", ".join(self.shared_components),
                        id="shared-profile-warning",
                        classes="warning",
                    )
                with Horizontal(id="schema-tools"):
                    yield Select(
                        tuple((group, group) for group in self.groups),
                        value=self.groups[0],
                        id="schema-group",
                    )
                    yield Button("Reset section", id="reset-section")
                    yield Button("Revert all", id="revert-all")
                    yield Button("Show advanced", id="toggle-advanced")
                yield Static("", id="schema-error-summary", classes="validation-error")
                with Vertical(id="schema-fields"):
                    previous_group = ""
                    for index, row in enumerate(self.rows):
                        group = str(row.get("group") or "General")
                        if group != previous_group:
                            yield Static(group, classes="field-group")
                            previous_group = group
                        classes = "schema-field advanced-field" if row.get("advanced") else "schema-field"
                        with Vertical(id=f"schema-row-{index}", classes=classes):
                            suffix = f" ({row['unit']})" if row.get("unit") else ""
                            label = field_title(row) + suffix + (" *" if row.get("required") else "")
                            yield Label(label, classes="field-label")
                            yield Static(
                                f"{row['path']}  |  source: {row.get('source', 'unknown')}  |  "
                                f"default: {display_schema_value(row.get('default')) or 'none'}",
                                classes="field-path",
                            )
                            help_text = row.get("help") or row.get("description")
                            if help_text:
                                yield Static(str(help_text), classes="field-help")
                            yield schema_widget(row, self.initial_values[index], f"schema-field-{index}")
                            yield Static("", id=f"schema-error-{index}", classes="validation-error")
                            if row.get("exclusions"):
                                yield Static(
                                    "This field participates in a mutually exclusive constraint.",
                                    classes="constraint-help",
                                )
                with Horizontal(classes="dialog-actions"):
                    yield Button("Cancel", id="cancel")
                    yield Button("Save", id="save")
                    yield Button("Save & Restart", id="save-restart", variant="primary")

        def on_mount(self) -> None:
            self._show_advanced(False)

        def _show_advanced(self, visible: bool) -> None:
            self.advanced_visible = visible
            for index, row in enumerate(self.rows):
                if row.get("advanced"):
                    self.query_one(f"#schema-row-{index}").display = visible
            self.query_one("#toggle-advanced", Button).label = (
                "Hide advanced" if visible else "Show advanced"
            )

        def _parse_row(self, index: int) -> Any:
            row = self.rows[index]
            raw = widget_raw(self, row, f"schema-field-{index}")
            if not raw:
                if row.get("required"):
                    raise TemplateError("This field is required")
                return None
            if row["path"].startswith("connections."):
                return parse_schema_value({"type": "string", "minLength": 1}, raw)
            node_schema = (
                llmops_cli.COMPONENT_SCHEMA
                if row["path"].startswith("component.")
                else load_template_registry(self.topology.paths)[self.component.template_id].profile_schema
            )
            relative = row["path"].split(".", 1)[1]
            return parse_widget_value(row, schema_node(node_schema, relative), raw)

        def _validate_row(self, index: int) -> bool:
            error = self.query_one(f"#schema-error-{index}", Static)
            try:
                self._parse_row(index)
            except TemplateError as exc:
                error.update(str(exc))
                return False
            error.update("")
            return True

        def on_input_changed(self, event: Any) -> None:
            identifier = str(event.input.id)
            if not identifier.startswith("schema-field-"):
                return
            self._validate_row(int(identifier.removeprefix("schema-field-")))

        def on_select_changed(self, event: Any) -> None:
            if event.select.id == "schema-group":
                return
            try:
                index = int(str(event.select.id).removeprefix("schema-field-"))
            except ValueError:
                return
            if not 0 <= index < len(self.rows):
                return
            self._validate_row(index)
            if self.rows[index]["path"] != "profile.server.spec_type":
                return
            disabled_by_mode = {
                "ngram": {"profile.server.draft_model", "profile.server.mtp_model"},
                "mtp": {
                    "profile.server.draft_model",
                    "profile.server.spec_ngram_size_n",
                    "profile.server.spec_ngram_size_m",
                },
                "draft-model": {
                    "profile.server.mtp_model",
                    "profile.server.spec_ngram_size_n",
                    "profile.server.spec_ngram_size_m",
                },
                "none": set(),
            }
            disabled = disabled_by_mode.get(str(event.value), set())
            managed = set().union(*disabled_by_mode.values())
            for row_index, row in enumerate(self.rows):
                if row["path"] not in managed:
                    continue
                widget = self.query_one(f"#schema-field-{row_index}")
                widget.disabled = row["path"] in disabled
                if widget.disabled and isinstance(widget, Input):
                    widget.value = ""

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "cancel":
                self.dismiss(None)
                return
            if event.button.id == "toggle-advanced":
                self._show_advanced(not self.advanced_visible)
                return
            if event.button.id in {"reset-section", "revert-all"}:
                selected_group = str(self.query_one("#schema-group", Select).value)
                for index, row in enumerate(self.rows):
                    if event.button.id == "revert-all" or row.get("group") == selected_group:
                        set_widget_value(
                            self,
                            row,
                            f"schema-field-{index}",
                            self.initial_values[index],
                        )
                        self.query_one(f"#schema-error-{index}", Static).update("")
                self.query_one("#schema-error-summary", Static).update("")
                return
            if event.button.id not in {"save", "save-restart"}:
                return
            assignments: list[str] = []
            unsets: list[str] = []
            valid = True
            for index, row in enumerate(self.rows):
                raw = widget_raw(self, row, f"schema-field-{index}")
                current = row.get("current")
                initial = self.initial_values[index]
                if not raw and current is not None and not row.get("required"):
                    unsets.append(row["path"])
                    continue
                if not raw:
                    if row.get("required"):
                        self.query_one(f"#schema-error-{index}", Static).update("This field is required")
                        valid = False
                    continue
                try:
                    parsed = self._parse_row(index)
                except TemplateError as exc:
                    self.query_one(f"#schema-error-{index}", Static).update(str(exc))
                    valid = False
                    continue
                if parsed != initial:
                    encoded = json.dumps(parsed, separators=(",", ":")) if isinstance(parsed, (dict, list)) else str(parsed).lower() if isinstance(parsed, bool) else str(parsed)
                    assignments.append(f"{row['path']}={encoded}")
            if not valid:
                self.query_one("#schema-error-summary", Static).update(
                    "Correct the highlighted fields before saving."
                )
                return
            self.dismiss(
                {
                    "assignments": assignments,
                    "unsets": unsets,
                    "restart_affected": event.button.id == "save-restart",
                }
            )

        def action_cancel(self) -> None:
            self.dismiss(None)

    class DetailsScreen(ModalScreen[Optional[str]]):
        """Show complete status, effective configuration, and schema sources."""

        BINDINGS = [("escape", "close", "Close")]

        def __init__(self, topology: Any, component: Any, status: dict[str, Any]) -> None:
            super().__init__()
            self.topology = topology
            self.component = component
            self.status = status
            self.template = load_template_registry(topology.paths).get(component.template_id)

        def compose(self) -> ComposeResult:
            effective = llmops_cli._effective_component(self.component, topology=self.topology)
            fields = component_field_records(self.topology, self.component.qualified_id)
            field_text = "\n".join(
                f"{row['path']} = {json.dumps(row.get('current'), sort_keys=True)} "
                f"[{row.get('source', 'unknown')}]"
                for row in fields
            )
            with Vertical(classes="dialog details-dialog", id="details-dialog"):
                yield Label(f"Details: {self.component.qualified_id}", classes="dialog-title")
                yield Static(
                    json.dumps(
                        {
                            "status": self.status,
                            "effective_configuration": effective,
                            "template": self.component.template_id,
                            "connections": self.component.connections,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n\nFields and value sources\n"
                    + field_text,
                    classes="dialog-body details-body",
                )
                with Horizontal(classes="dialog-actions"):
                    yield Button("Close", id="close")
                    if self.template is not None:
                        for action in sorted(self.template.actions):
                            yield Button(action.replace("-", " ").title(), id=f"tool-action-{action}")

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "close":
                self.dismiss(None)
            elif str(event.button.id).startswith("tool-action-"):
                self.dismiss(str(event.button.id).removeprefix("tool-action-"))

        def action_close(self) -> None:
            self.dismiss(None)

    class StackDetailsScreen(ModalScreen[Optional[str]]):
        """Show complete stack membership and dependency relationships."""

        BINDINGS = [("escape", "close", "Close")]

        def __init__(self, stack: Any) -> None:
            super().__init__()
            self.stack = stack
            self.component_ids = sorted(stack.components)

        def compose(self) -> ComposeResult:
            with Vertical(classes="dialog details-dialog", id="stack-details-dialog"):
                yield Label(f"Stack: {self.stack.name}", classes="dialog-title")
                yield Static(
                    "Stacks are lifecycle groups. Membership is changed through Add, Clone, Retire, and Restore; dependencies are edited on the selected component.",
                    classes="field-help",
                )
                yield DataTable(id="stack-members", cursor_type="row")
                yield Static("Select a member to inspect dependencies.", id="stack-member-detail")
                with Horizontal(classes="dialog-actions"):
                    yield Button("Close", id="close")
                    yield Button("Configure member", id="configure", variant="primary")

        def on_mount(self) -> None:
            table = self.query_one("#stack-members", DataTable)
            table.add_columns("Component", "Host", "Template", "Enabled", "Dependencies")
            for component_id in self.component_ids:
                component = self.stack.components[component_id]
                table.add_row(
                    component.qualified_id,
                    component.host,
                    component.template_id,
                    str(component.enabled),
                    ", ".join(component.depends_on) or "none",
                )
            if self.component_ids:
                table.move_cursor(row=0)
                self._show(0)

        def _show(self, row: int) -> None:
            if not 0 <= row < len(self.component_ids):
                return
            component = self.stack.components[self.component_ids[row]]
            self.query_one("#stack-member-detail", Static).update(
                f"{component.qualified_id}\n"
                f"Depends on: {', '.join(component.depends_on) or 'none'}\n"
                f"Connections: {json.dumps(component.connections, sort_keys=True)}"
            )

        def on_data_table_row_highlighted(self, event: Any) -> None:
            self._show(event.cursor_row)

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "close":
                self.dismiss(None)
                return
            row = self.query_one("#stack-members", DataTable).cursor_row
            if 0 <= row < len(self.component_ids):
                self.dismiss(self.stack.components[self.component_ids[row]].qualified_id)

        def action_close(self) -> None:
            self.dismiss(None)

    class ServiceCatalogScreen(ModalScreen[Optional[tuple[str, str]]]):
        """List audited templates and initiate schema-driven component creation."""

        BINDINGS = [("escape", "close", "Close")]

        def __init__(self, topology: Any, component: Optional[Any] = None) -> None:
            super().__init__()
            self.registry = load_template_registry(topology.paths)
            self.template_ids = sorted(self.registry)
            self.component = component

        def compose(self) -> ComposeResult:
            with Vertical(classes="dialog catalog-dialog", id="catalog-dialog"):
                yield Label("Service Catalog", classes="dialog-title")
                yield DataTable(id="catalog-table", cursor_type="row")
                yield Static("Select a template to inspect or add.", id="catalog-detail")
                with Horizontal(classes="dialog-actions"):
                    yield Button("Close", id="close")
                    yield Button("Import local", id="import")
                    yield Button("Edit selected", id="edit", disabled=self.component is None)
                    yield Button("Clone selected", id="clone", disabled=self.component is None)
                    yield Button(
                        "Restore selected" if self.component is not None and self.component.retired else "Retire selected",
                        id="restore" if self.component is not None and self.component.retired else "retire",
                        disabled=self.component is None,
                    )
                    yield Button("Add component", id="add", variant="primary")

        def on_mount(self) -> None:
            table = self.query_one("#catalog-table", DataTable)
            table.add_columns("Template", "Kind", "Lifecycle", "Adapter", "Platforms")
            for template_id in self.template_ids:
                item = self.registry[template_id]
                table.add_row(template_id, item.component_kind, item.lifecycle, item.adapter, ", ".join(item.platforms))
            if self.template_ids:
                table.move_cursor(row=0)
                self._show(0)

        def _show(self, row: int) -> None:
            if not 0 <= row < len(self.template_ids):
                return
            item = self.registry[self.template_ids[row]]
            self.query_one("#catalog-detail", Static).update(
                f"{item.template_id} {item.version}\n"
                f"Source: {item.source}\n"
                f"Provides: {', '.join(item.endpoints.get('provides', {})) or 'none'}  "
                f"Requires: {', '.join(item.endpoints.get('requires', {})) or 'none'}\n"
                f"Actions: {', '.join(item.actions) or 'standard lifecycle'}"
            )

        def on_data_table_row_highlighted(self, event: Any) -> None:
            self._show(event.cursor_row)

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "close":
                self.dismiss(None)
                return
            if event.button.id == "import":
                self.dismiss(("import", ""))
                return
            if event.button.id in {"edit", "clone", "retire", "restore"}:
                self.dismiss((str(event.button.id), self.component.qualified_id))
                return
            row = self.query_one("#catalog-table", DataTable).cursor_row
            if 0 <= row < len(self.template_ids):
                self.dismiss(("add", self.template_ids[row]))

        def action_close(self) -> None:
            self.dismiss(None)

    class TemplateImportScreen(ModalScreen[Optional[str]]):
        """Collect one operator-reviewed local template path."""

        BINDINGS = [("escape", "cancel", "Cancel")]

        def compose(self) -> ComposeResult:
            with Vertical(classes="dialog", id="template-import-dialog"):
                yield Label("Import reviewed local template", classes="dialog-title")
                yield Static(
                    "The JSON file must use a registered adapter and cannot contain shell strings "
                    "or executable callbacks.",
                    classes="field-help",
                )
                yield Label("Template JSON path", classes="field-label")
                yield Input(id="template-import-path", placeholder="~/templates/my-service.json")
                yield Static("", id="template-import-error", classes="validation-error")
                with Horizontal(classes="dialog-actions"):
                    yield Button("Cancel", id="cancel")
                    yield Button("Review import", id="review", variant="primary")

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "cancel":
                self.dismiss(None)
                return
            path = self.query_one("#template-import-path", Input).value.strip()
            if not path:
                self.query_one("#template-import-error", Static).update("A local JSON path is required.")
                return
            self.dismiss(path)

        def action_cancel(self) -> None:
            self.dismiss(None)

    class CloneComponentScreen(ModalScreen[Optional[dict[str, Any]]]):
        """Collect the stable identity and profile policy for a component clone."""

        BINDINGS = [("escape", "cancel", "Cancel")]

        def __init__(self, component: Any) -> None:
            super().__init__()
            self.component = component

        def compose(self) -> ComposeResult:
            with Vertical(classes="dialog", id="clone-component-dialog"):
                yield Label(f"Clone {self.component.qualified_id}", classes="dialog-title")
                yield Label("New component ID")
                yield Input(id="clone-id")
                yield Checkbox("Share existing reusable profile", value=True, id="clone-share-profile")
                with Horizontal(classes="dialog-actions"):
                    yield Button("Cancel", id="cancel")
                    yield Button("Review", id="review", variant="primary")

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "cancel":
                self.dismiss(None)
                return
            self.dismiss(
                {
                    "new_id": self.query_one("#clone-id", Input).value.strip(),
                    "share_profile": self.query_one("#clone-share-profile", Checkbox).value,
                }
            )

        def action_cancel(self) -> None:
            self.dismiss(None)

    class AddComponentScreen(ModalScreen[Optional[dict[str, Any]]]):
        """Guide creation through placement, settings, connections, and review."""

        BINDINGS = [("escape", "cancel", "Cancel")]

        def __init__(self, topology: Any, template: Any) -> None:
            super().__init__()
            self.topology = topology
            self.template = template
            directory = {
                "model": topology.paths.models_dir,
                "agent": topology.paths.agents_dir,
            }.get(template.profile_kind, topology.paths.services_dir)
            self.profiles = []
            for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if document.get("template_id") == template.template_id:
                    self.profiles.append(path.stem)
            self.rows = [
                row
                for row in field_records(template, current=template.defaults)
                if not row.get("read_only")
                and not row.get("advanced")
                and row["path"] != "profile.name"
            ]
            self.step = 0
            self.step_names = ("Placement", "Settings", "Connections", "Review")
            registry = load_template_registry(topology.paths)
            self.connection_options: dict[str, tuple[tuple[str, str], ...]] = {}
            for name, requirement in template.endpoints.get("requires", {}).items():
                protocol = str(requirement.get("protocol", ""))
                options: list[tuple[str, str]] = []
                for component in topology.all_components():
                    provider = registry.get(component.template_id)
                    if provider is None:
                        continue
                    for endpoint in provider.endpoints.get("provides", {}):
                        if not protocol or endpoint == protocol:
                            value = f"{component.qualified_id}@{endpoint}"
                            options.append((value, value))
                self.connection_options[str(name)] = tuple(options)

        def compose(self) -> ComposeResult:
            profile_options = (("Create new profile", "__new__"),) + tuple((name, name) for name in self.profiles)
            with Vertical(classes="dialog schema-dialog", id="add-component-dialog"):
                yield Label(f"Add {self.template.template_id}", classes="dialog-title")
                yield Static("", id="add-progress", classes="wizard-progress")
                yield Static("", id="add-error", classes="validation-error")
                with Vertical(id="add-step-placement", classes="wizard-step"):
                    yield Static("Identity and placement", classes="field-group")
                    yield Static(
                        f"Template lifecycle: {self.template.lifecycle}",
                        classes="field-help",
                    )
                    yield Label("Component ID *", classes="field-label")
                    yield Static("Stable ID within the selected stack.", classes="field-help")
                    yield Input(id="add-id", placeholder="model-proxy")
                    yield Label("Stack", classes="field-label")
                    yield Select(tuple((name, name) for name in sorted(self.topology.stacks)), value=sorted(self.topology.stacks)[0], id="add-stack")
                    yield Label("Host alias", classes="field-label")
                    yield Static("A catalog alias, not necessarily a DNS hostname.", classes="field-help")
                    yield Select(tuple((name, name) for name in sorted(self.topology.hosts)), value=sorted(self.topology.hosts)[0], id="add-host")
                    yield Label("Execution user", classes="field-label")
                    yield Static("Leave blank to use the inventory user for the selected host.", classes="field-help")
                    yield Input(id="add-user")
                    yield Label("Reusable profile", classes="field-label")
                    yield Select(profile_options, value="__new__", id="add-profile-mode")
                    yield Label("New profile name", classes="field-label", id="add-profile-name-label")
                    yield Input(id="add-profile-name")
                with Vertical(id="add-step-settings", classes="wizard-step"):
                    yield Static("Essential service settings", classes="field-group")
                    yield Static(
                        "Advanced settings remain available from Configure after creation.",
                        classes="field-help",
                    )
                    with Vertical(id="add-profile-fields"):
                        previous_group = ""
                        for index, row in enumerate(self.rows):
                            group = str(row.get("group") or "General")
                            if group != previous_group:
                                yield Static(group, classes="field-group")
                                previous_group = group
                            suffix = f" ({row['unit']})" if row.get("unit") else ""
                            yield Label(
                                field_title(row) + suffix + (" *" if row.get("required") else ""),
                                classes="field-label",
                            )
                            yield Static(row["path"], classes="field-path")
                            help_text = row.get("help") or row.get("description")
                            if help_text:
                                yield Static(str(help_text), classes="field-help")
                            yield schema_widget(row, row.get("current"), f"add-field-{index}")
                            yield Static("", id=f"add-field-error-{index}", classes="validation-error")
                with Vertical(id="add-step-connections", classes="wizard-step"):
                    yield Static("Connections and inferred dependencies", classes="field-group")
                    if not self.connection_options:
                        yield Static("This template has no required endpoint connections.", classes="field-help")
                    for name, options in self.connection_options.items():
                        yield Label(f"Required endpoint: {name}", classes="field-label")
                        if options:
                            yield Select(options, value=options[0][1], id=f"add-connection-{name}")
                        else:
                            yield Static(
                                "No compatible provider is currently configured. Add the provider first.",
                                id=f"add-connection-error-{name}",
                                classes="validation-error",
                            )
                with Vertical(id="add-step-review", classes="wizard-step"):
                    yield Static("Review", classes="field-group")
                    yield Static("", id="add-review", classes="dialog-body")
                with Horizontal(classes="dialog-actions"):
                    yield Button("Cancel", id="cancel")
                    yield Button("Back", id="back")
                    yield Button("Next", id="next-placement", variant="primary")
                    yield Button("Next", id="next-settings", variant="primary")
                    yield Button("Next", id="next-connections", variant="primary")
                    yield Button("Review", id="review", variant="primary")

        def on_mount(self) -> None:
            self._show_step(0)

        def _show_step(self, step: int) -> None:
            self.step = max(0, min(step, len(self.step_names) - 1))
            for index, name in enumerate(("placement", "settings", "connections", "review")):
                self.query_one(f"#add-step-{name}").display = index == self.step
            self.query_one("#add-progress", Static).update(
                f"Step {self.step + 1} of {len(self.step_names)}: {self.step_names[self.step]}"
            )
            self.query_one("#back", Button).disabled = self.step == 0
            for index, name in enumerate(("placement", "settings", "connections")):
                self.query_one(f"#next-{name}", Button).display = self.step == index
            self.query_one("#review", Button).display = self.step == len(self.step_names) - 1
            self.query_one("#add-error", Static).update("")
            if self.step == 3:
                self._update_review()

        def _using_new_profile(self) -> bool:
            return str(self.query_one("#add-profile-mode", Select).value) == "__new__"

        def _validate_step(self) -> bool:
            if self.step == 0:
                if not self.query_one("#add-id", Input).value.strip():
                    self.query_one("#add-error", Static).update("Component ID is required.")
                    return False
                if self._using_new_profile() and not self.query_one("#add-profile-name", Input).value.strip():
                    self.query_one("#add-error", Static).update("A new profile name is required.")
                    return False
            if self.step == 1 and self._using_new_profile():
                valid = True
                for index, row in enumerate(self.rows):
                    raw = widget_raw(self, row, f"add-field-{index}")
                    try:
                        if not raw and row.get("required"):
                            raise TemplateError("This field is required")
                        if raw:
                            node = schema_node(
                                self.template.profile_schema,
                                row["path"].removeprefix("profile."),
                            )
                            parse_widget_value(row, node, raw)
                    except TemplateError as exc:
                        self.query_one(f"#add-field-error-{index}", Static).update(str(exc))
                        valid = False
                    else:
                        self.query_one(f"#add-field-error-{index}", Static).update("")
                if not valid:
                    self.query_one("#add-error", Static).update("Correct the highlighted settings.")
                    return False
            if self.step == 2 and any(not options for options in self.connection_options.values()):
                self.query_one("#add-error", Static).update(
                    "Every required endpoint needs a compatible configured provider."
                )
                return False
            return True

        def _update_review(self) -> None:
            mode = str(self.query_one("#add-profile-mode", Select).value)
            connections = self._connections()
            dependencies = sorted({item["component"] for item in connections.values()})
            self.query_one("#add-review", Static).update(
                f"Component: {self.query_one('#add-id', Input).value.strip()}\n"
                f"Template: {self.template.template_id}\n"
                f"Stack: {self.query_one('#add-stack', Select).value}\n"
                f"Host: {self.query_one('#add-host', Select).value}\n"
                f"Execution user: {self.query_one('#add-user', Input).value.strip() or 'inventory default'}\n"
                f"Profile: {self.query_one('#add-profile-name', Input).value.strip() if mode == '__new__' else mode} "
                f"({'create' if mode == '__new__' else 'reuse'})\n"
                f"Connections: {json.dumps(connections, sort_keys=True) if connections else 'none'}\n"
                f"Inferred dependencies: {', '.join(dependencies) or 'none'}\n"
                "Initial lifecycle: disabled"
            )

        def _connections(self) -> dict[str, dict[str, str]]:
            connections: dict[str, dict[str, str]] = {}
            for name, options in self.connection_options.items():
                if not options:
                    continue
                selected = str(self.query_one(f"#add-connection-{name}", Select).value)
                component_ref, _, endpoint = selected.rpartition("@")
                connections[name] = {"component": component_ref, "endpoint": endpoint}
            return connections

        def on_select_changed(self, event: Any) -> None:
            if event.select.id == "add-profile-mode":
                creating = event.value == "__new__"
                self.query_one("#add-profile-name", Input).disabled = not creating
                if not creating:
                    self.query_one("#add-profile-name", Input).value = str(event.value)
                self.query_one("#add-profile-fields").display = creating

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "cancel":
                self.dismiss(None)
                return
            if event.button.id == "back":
                self._show_step(self.step - 1)
                return
            if str(event.button.id).startswith("next-"):
                if self._validate_step():
                    self._show_step(self.step + 1)
                return
            if event.button.id != "review" or not self._validate_step():
                return
            mode = str(self.query_one("#add-profile-mode", Select).value)
            values: dict[str, Any] = {}
            if mode == "__new__":
                for index, row in enumerate(self.rows):
                    node = schema_node(self.template.profile_schema, row["path"].removeprefix("profile."))
                    raw = widget_raw(self, row, f"add-field-{index}")
                    if raw:
                        set_dotted(
                            values,
                            row["path"].removeprefix("profile."),
                            parse_widget_value(row, node, raw),
                        )
            profile_name = self.query_one("#add-profile-name", Input).value.strip()
            connections = self._connections()
            self.dismiss(
                {
                    "component_id": self.query_one("#add-id", Input).value.strip(),
                    "stack_name": str(self.query_one("#add-stack", Select).value),
                    "host": str(self.query_one("#add-host", Select).value),
                    "execution_user": self.query_one("#add-user", Input).value.strip(),
                    "profile_name": profile_name if mode == "__new__" else mode,
                    "profile_values": values,
                    "create_new_profile": mode == "__new__",
                    "connections": connections,
                    "dependencies": (),
                }
            )

        def action_cancel(self) -> None:
            self.dismiss(None)

    class HelpScreen(ModalScreen[None]):
        """Display contextual operations and status help."""

        BINDINGS = [("escape", "close", "Close"), ("h", "close", "Close")]

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

        def action_close(self) -> None:
            self.dismiss(None)

    class SettingsScreen(ModalScreen[Optional[UiPreferences]]):
        """Edit host-local TUI preferences."""

        BINDINGS = [("escape", "cancel", "Cancel")]

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

        def action_cancel(self) -> None:
            self.dismiss(None)

    class BrandingScreen(ModalScreen[Optional[dict[str, str]]]):
        """Edit shared organization and site labels."""

        BINDINGS = [("escape", "cancel", "Cancel")]

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

        def action_cancel(self) -> None:
            self.dismiss(None)

    class LogChannelScreen(ModalScreen[Optional[str]]):
        """Select a supported component log channel."""

        BINDINGS = [("escape", "cancel", "Cancel")]

        def __init__(self, channels: tuple[str, ...]) -> None:
            super().__init__()
            self.channels = channels

        def compose(self) -> ComposeResult:
            with Vertical(classes="dialog", id="log-channel-dialog"):
                yield Label("Select log channel", classes="dialog-title")
                yield Select(tuple((item.replace("-", " ").title(), item) for item in self.channels), value=self.channels[0], id="log-channel")
                with Horizontal(classes="dialog-actions"):
                    yield Button("Cancel", id="cancel")
                    yield Button("Open", id="open", variant="primary")

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "cancel":
                self.dismiss(None)
            else:
                self.dismiss(str(self.query_one("#log-channel", Select).value))

        def action_cancel(self) -> None:
            self.dismiss(None)

    class TopologyScreen(ModalScreen[None]):
        """Show a bounded, filterable, host-grouped topology tree."""

        BINDINGS = [("escape", "close", "Close")]

        def __init__(self, topology: Any, status_by_id: dict[str, dict[str, Any]]) -> None:
            super().__init__()
            self.topology = topology
            self.status_by_id = status_by_id
            self.resetting_filters = False

        def compose(self) -> ComposeResult:
            hosts = (("All hosts", ""),) + tuple((name, name) for name in sorted(self.topology.hosts))
            stacks = (("All stacks", ""),) + tuple((name, name) for name in sorted(self.topology.stacks))
            drivers = (("All drivers", ""),) + tuple(
                (name, name) for name in sorted({item.driver for item in self.topology.all_components()})
            )
            conditions = (("All conditions", ""),) + tuple(
                (name.title(), name) for name in ("ok", "down", "attention", "error", "unobserved")
            )
            with Vertical(id="topology-dialog"):
                yield Label("Service Topology", classes="dialog-title")
                with Horizontal(id="topology-filters"):
                    yield Select(hosts, value="", id="topology-host")
                    yield Select(stacks, value="", id="topology-stack")
                    yield Select(drivers, value="", id="topology-driver")
                    yield Select(conditions, value="", id="topology-condition")
                    yield Button("Reset", id="reset")
                    yield Button("Close", id="close")
                yield Tree("Topology", id="topology-tree")
                yield Static("Select a component for relationships.", id="topology-detail")

        def on_mount(self) -> None:
            self.refresh_tree()

        def refresh_tree(self) -> None:
            host_filter = str(self.query_one("#topology-host", Select).value or "")
            stack_filter = str(self.query_one("#topology-stack", Select).value or "")
            driver_filter = str(self.query_one("#topology-driver", Select).value or "")
            condition_filter = str(self.query_one("#topology-condition", Select).value or "")
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
                conditions = [
                    str(self.status_by_id.get(item["id"], {}).get("condition", "unobserved"))
                    for item in by_host[host]
                ]
                severity = {"error": 4, "attention": 3, "down": 2, "unobserved": 1, "ok": 0}
                host_condition = max(conditions, key=lambda value: severity.get(value, 1))
                host_label = Text(
                    f"{host} ({len(by_host[host])})",
                    style=CONDITION_STYLES.get(host_condition, "#f5f7fa"),
                )
                host_node = tree.root.add(host_label, expand=True)
                for item in sorted(by_host[host], key=lambda value: value["id"]):
                    state = self.status_by_id.get(item["id"], {})
                    condition = state.get("condition", "unobserved")
                    label = Text(
                        f"[{condition}] {item['id']}",
                        style=CONDITION_STYLES.get(condition, "#f5f7fa"),
                    )
                    host_node.add_leaf(label, data=item)
            tree.root.expand()

        def on_select_changed(self, event: Any) -> None:
            if event.select.id not in {
                "topology-host",
                "topology-stack",
                "topology-driver",
                "topology-condition",
            }:
                return
            if not self.resetting_filters:
                self.refresh_tree()

        def on_button_pressed(self, event: Any) -> None:
            if event.button.id == "close":
                self.dismiss(None)
            elif event.button.id == "reset":
                self.resetting_filters = True
                for selector in (
                    "#topology-host",
                    "#topology-stack",
                    "#topology-driver",
                    "#topology-condition",
                ):
                    self.query_one(selector, Select).value = ""
                self.resetting_filters = False
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

        def action_close(self) -> None:
            self.dismiss(None)

    class LlmOpsApp(App[None]):
        TITLE = "LLM-Ops-Kit"
        CSS = """
        Screen {
            background: #0b0f14;
            color: #f5f7fa;
            scrollbar-color: #49637c;
            scrollbar-color-hover: #5b7893;
            scrollbar-color-active: #6f8ea3;
            scrollbar-background: #111923;
        }
        Header { background: #14202b; color: #ffffff; text-style: bold; }
        #summary { height: 3; padding: 1 2; background: #111923; color: #f5f7fa; }
        #components { height: 1fr; background: #0b0f14; color: #f5f7fa; }
        #components > .datatable--header { background: #243444; color: #ffffff; text-style: bold; }
        #components > .datatable--cursor { background: #29445c; color: #ffffff; text-style: bold; }
        #detail { height: 11; border-top: solid #6f8ea3; padding: 1 2; overflow-y: auto; background: #0f151d; color: #f5f7fa; }
        #action-bar { height: 3; padding: 0 1; background: #1b2733; color: #ffffff; text-style: bold; }
        #action-bar Button { min-width: 9; height: 3; margin: 0 1 0 0; border: none; background: #33485d; color: #ffffff; }
        #action-bar Button:hover, #action-bar Button:focus { background: #49637c; color: #ffffff; }
        .dialog { width: 78; height: auto; max-height: 92%; padding: 1 2; border: thick #6f8ea3; background: #111923; color: #ffffff; }
        .dialog-title { text-style: bold; color: #b8d4e8; margin-bottom: 1; }
        .dialog-body { color: #f5f7fa; overflow-y: auto; }
        .dialog-actions { height: 3; margin-top: 1; }
        .equivalent-command { margin: 1 0; color: #9fe870; background: #0b0f14; padding: 1; }
        .warning { color: #ffd166; margin-bottom: 1; }
        Button { margin-right: 1; background: #33485d; color: #ffffff; border: none; }
        Button:hover, Button:focus { background: #49637c; color: #ffffff; background-tint: transparent; }
        Button.-primary { background: #496f91; color: #ffffff; }
        Button.-primary:hover, Button.-primary:focus { background: #5b7893; color: #ffffff; }
        Button.-error { background: #9f3d46; color: #ffffff; }
        Button.-error:hover, Button.-error:focus { background: #b64b55; color: #ffffff; }
        Input, Select { background: #18222d; color: #ffffff; border: tall #557086; }
        Input:focus { background: #18222d; color: #ffffff; border: tall #8aa6ba; background-tint: transparent; }
        Input > .input--cursor { background: #dce8f1; color: #0b0f14; }
        Input > .input--selection { background: #29445c; }
        Select > SelectCurrent { background: #18222d; color: #ffffff; border: tall #557086; }
        Select:focus > SelectCurrent { background: #18222d; color: #ffffff; border: tall #8aa6ba; background-tint: transparent; }
        Select > SelectOverlay { background: #111923; color: #ffffff; border: tall #557086; }
        Select > SelectOverlay:focus { background: #111923; border: tall #8aa6ba; background-tint: transparent; }
        Select > SelectOverlay > .option-list--option-highlighted { background: #29445c; color: #ffffff; }
        Select > SelectOverlay > .option-list--option-hover { background: #243444; color: #ffffff; }
        Checkbox { background: #18222d; color: #ffffff; border: tall #557086; }
        Checkbox > .toggle--button { background: #243444; color: #8aa6ba; }
        Checkbox.-on > .toggle--button { background: #243444; color: #43d17a; }
        Checkbox:focus { background: #18222d; border: tall #8aa6ba; background-tint: transparent; }
        Checkbox:focus > .toggle--label { background: #29445c; color: #ffffff; text-style: bold; }
        #topology-dialog { width: 95%; height: 95%; padding: 1 2; border: thick #6f8ea3; background: #0b0f14; }
        #topology-filters { height: 5; }
        #topology-filters Select { width: 1fr; margin-right: 1; }
        #topology-tree { height: 1fr; background: #0f151d; color: #f5f7fa; }
        #topology-detail { height: 8; border-top: solid #6f8ea3; padding: 1; }
        .schema-dialog, .details-dialog, .catalog-dialog { width: 95%; height: 95%; max-height: 95%; }
        #schema-fields, #add-profile-fields, .details-body { height: 1fr; overflow-y: auto; padding-right: 1; }
        #schema-tools { height: 3; margin-bottom: 1; }
        #schema-tools Select { width: 1fr; margin-right: 1; }
        #schema-tools Button { min-width: 16; }
        .schema-field { height: auto; }
        .wizard-progress { height: 2; color: #b8d4e8; text-style: bold; }
        .wizard-step { height: 1fr; overflow-y: auto; padding-right: 1; }
        #catalog-table { height: 1fr; }
        #catalog-detail { height: 7; border-top: solid #6f8ea3; padding: 1; }
        .field-help { color: #b8c5d1; }
        .field-group { margin: 1 0 0 0; padding: 0 1; background: #243444; color: #ffffff; text-style: bold; }
        .field-label { margin-top: 1; color: #f5f7fa; text-style: bold; }
        .field-path { color: #8aa6ba; }
        .constraint-help { color: #ffd166; margin-bottom: 1; }
        .validation-error { color: #ff6b75; min-height: 1; }
        """
        BINDINGS = [
            ("r", "refresh", "Refresh"),
            ("s", "start", "Start"),
            ("x", "stop", "Stop"),
            ("b", "restart", "Restart"),
            ("l", "logs", "Logs"),
            ("e", "edit", "Configure"),
            ("i", "details", "Details"),
            ("a", "catalog", "Catalog"),
            ("v", "toggle_view", "Components/Stacks"),
            ("t", "topology", "Topology"),
            ("comma", "settings", "Settings"),
            ("o", "branding", "Display labels"),
            ("?", "help", "Help"),
            ("h", "help", "Help"),
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
            with Horizontal(id="action-bar"):
                yield Button("Refresh", id="action-refresh")
                yield Button("Start", id="action-start")
                yield Button("Stop", id="action-stop")
                yield Button("Restart", id="action-restart")
                yield Button("Logs", id="action-logs")
                yield Button("Details", id="action-details")
                yield Button("Configure", id="action-configure")
                yield Button("Catalog", id="action-catalog")
                yield Button("Topology", id="action-topology")
                yield Button("Settings", id="action-settings")
                yield Button("Help", id="action-help")
                yield Button("Quit", id="action-quit")
            yield DataTable(id="components", cursor_type="row", zebra_stripes=False)
            yield Static("Select a component for details.", id="detail")

        def on_mount(self) -> None:
            from .llmops_ui import STATUS_COLUMNS

            table = self.query_one("#components", DataTable)
            table.add_columns(*(header.title() for _, header in STATUS_COLUMNS))
            table.focus()
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
                    f"Host: {item.host}  Run as: {state.get('execution_user') or 'unknown'}  "
                    f"Driver: {item.driver}  Profile: {item.profile}\n"
                    f"Condition: {state.get('condition', 'unobserved')}  "
                    f"Lifecycle: {state.get('lifecycle', 'unknown')}  "
                    f"Desired: {state.get('desired_lifecycle', 'unknown')}  "
                    f"Health: {state.get('health', 'unknown')}  "
                    f"Observability: {state.get('observability', 'unknown')}\n"
                    f"Component version: {state.get('component_version') or 'unknown'}  "
                    f"Product: {state.get('product_id') or 'unknown'}  "
                    f"Latest: {state.get('latest_version') or 'unknown'}  "
                    f"Update: {state.get('update_state') or 'unknown'}\n"
                    f"Toolkit version: {state.get('toolkit_version') or 'unknown'}  "
                    f"Drift: {state.get('drift', 'unknown')}\n"
                    f"Desired runtime: {state.get('desired_runtime') or 'unknown'}  "
                    f"Observed runtime: {state.get('observed_runtime') or 'unknown'}  "
                    f"Operation: {state.get('operation_id') or 'none'}\n"
                    f"Dependencies: {', '.join(item.depends_on) or 'none'}  Ownership: {item.ownership}"
                )
            else:
                detail = f"{item.name}\nComponents:\n" + "\n".join(
                    f"  {component.qualified_id}" for component in item.components.values()
                )
            self.query_one("#detail", Static).update(detail)

        async def inspect(self) -> None:
            selected_id = self._selected_id()
            self.topology = llmops_cli.build_topology(config_home=config_home, inventory=inventory)
            llmops_cli.CURRENT_TOPOLOGY = self.topology
            self.desired_topology = llmops_cli.desired_topology(config_home)
            self._apply_branding()
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
            active_operations = {
                str(record.get("target", "")): record
                for record in list_records(self.topology.paths)
                if record.get("state") in ACTIVE_STATES
            }
            transient = {
                "start": "starting",
                "stop": "stopping",
                "restart": "restarting",
                "update": "updating",
                "reconcile": "reconciling",
                "configure": "reconciling",
            }
            for item in payload:
                operation = active_operations.get(str(item.get("component", "")))
                if operation is not None:
                    item["lifecycle"] = transient.get(str(operation.get("action", "")), "running")
                    item["condition"] = "attention"
                    item["operation_id"] = operation.get("operation_id", "")
            self.status_by_id = {item["component"]: item for item in payload}
            self._render_status(payload, selected_id)

        def _render_status(self, payload: list[dict[str, Any]], selected_id: str) -> None:
            """Render the current component or stack projection without another probe."""

            self.rows = (
                self.topology.all_components()
                if self.view == "components"
                else [self.topology.stacks[name] for name in sorted(self.topology.stacks)]
            )
            if len(self.screen_stack) != 1:
                return
            tables = self.query("#components")
            if not tables:
                return
            table = tables.first(DataTable)
            table.clear()
            if self.view == "components":
                from .llmops_ui import STATUS_COLUMNS

                for component in self.rows:
                    item = self.status_by_id[component.qualified_id]
                    cells = tuple((field, item.get(field, "")) for field, _ in STATUS_COLUMNS)
                    table.add_row(
                        *(
                            Text(str(value), style=status_cell_style(field, item))
                            for field, value in cells
                        )
                    )
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
                        else "down"
                        if "down" in states
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
                argv = shlex.split(command)[1:]
                if config_home:
                    argv = ["--config-home", str(self.topology.paths.config_home), *argv]
                operation = dispatch(
                    self.topology.paths,
                    argv=argv,
                    action=action,
                    target=(
                        target.qualified_id
                        if hasattr(target, "qualified_id")
                        else target.name
                    ),
                    command=command,
                    plan=plan,
                    host=(
                        target.host
                        if hasattr(target, "host")
                        else ",".join(sorted({item["host"] for item in plan}))
                    ),
                )
                self.query_one("#detail", Static).update(
                    f"Operation queued: {operation['operation_id']}\n{command}\n"
                    "The operation continues independently if the TUI exits."
                )
            except (ExecutionError, TopologyError) as exc:
                self.query_one("#detail", Static).update(str(exc))
            finally:
                self.mutating = False
                self.action_refresh()

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
            channels = (
                ("service", "raw-request", "rendered-prompt", "raw-response")
                if component.driver == "model-proxy"
                else ("service",)
            )
            channel = channels[0]
            if len(channels) > 1:
                selected = await self.push_screen_wait(LogChannelScreen(channels))
                if selected is None:
                    return
                channel = selected
            result = await asyncio.to_thread(
                ComponentRunner(self.topology).logs,
                component,
                channel=channel,
            )
            heading = (
                f"Host: {component.host}  Run as: {self.topology.hosts[component.host].user}  "
                f"Channel: {channel}\n"
            )
            self.query_one("#detail", Static).update(
                heading + (result.stdout or result.stderr or "No log output")
            )

        def action_logs(self) -> None:
            component = self.selected_component()
            if component is not None and hasattr(component, "component_id"):
                self.run_worker(self.show_logs(component), exclusive=True)

        async def edit_component(self, component: Any) -> None:
            changes = await self.push_screen_wait(SchemaEditComponent(self.desired_topology, component))
            if changes is None:
                return
            if not changes["assignments"] and not changes["unsets"]:
                self.query_one("#detail", Static).update("No configuration changes")
                return
            plan = configure_component_schema(
                self.desired_topology,
                component.qualified_id,
                assignments=changes["assignments"],
                unsets=changes["unsets"],
                apply=False,
            )
            restart_affected = bool(changes["restart_affected"])
            plan["restart_affected"] = restart_affected
            command = schema_configure_command(
                component.qualified_id,
                changes["assignments"],
                changes["unsets"],
                expected_hash=plan["authority_hash"],
                restart_affected=restart_affected,
            )
            review_plan = [
                {"action": "save persistent configuration", "component": component.qualified_id}
            ]
            if restart_affected:
                review_plan.extend(
                    {"action": "restart if running", "component": item}
                    for item in plan["affected_components"]
                )
            approved = await self.push_screen_wait(
                ConfirmOperation(
                    command,
                    review_plan,
                    title="Confirm persistent configuration",
                    confirm_label="Save & Restart" if restart_affected else "Save",
                    confirm_variant="primary",
                )
            )
            if not approved:
                return
            argv = shlex.split(command)[1:]
            if config_home:
                argv = ["--config-home", str(self.desired_topology.paths.config_home), *argv]
            operation = dispatch(
                self.desired_topology.paths,
                argv=argv,
                action="configure",
                target=component.qualified_id,
                command=command,
                plan=review_plan,
                host=component.host,
            )
            self.query_one("#detail", Static).update(
                f"Configuration operation queued: {operation['operation_id']}\n{command}\n"
                "Saved changes are persistent. The operation continues independently if the TUI exits."
            )
            self.action_refresh()

        def action_edit(self) -> None:
            component = self.selected_component()
            if component is not None and hasattr(component, "component_id"):
                desired = self.desired_topology.resolve_component(component.qualified_id)
                self.run_worker(self.edit_component(desired), exclusive=True)

        def action_details(self) -> None:
            selected = self.selected_component()
            if selected is not None and hasattr(selected, "component_id"):
                desired = self.desired_topology.resolve_component(selected.qualified_id)
                self.run_worker(
                    self.show_component_details(desired),
                    exclusive=True,
                )
            elif selected is not None and hasattr(selected, "components"):
                self.run_worker(self.show_stack_details(selected), exclusive=True)

        async def show_component_details(self, component: Any) -> None:
            action = await self.push_screen_wait(
                DetailsScreen(
                    self.desired_topology,
                    component,
                    self.status_by_id.get(component.qualified_id, {}),
                )
            )
            if not action:
                return
            template, argv, mutating = llmops_cli.template_action_argv(
                self.desired_topology,
                component.qualified_id,
                action,
            )
            command = shlex.join(
                ["llmops", "component", "action", component.qualified_id, action]
                + (["--apply", "--yes"] if mutating else ["--apply"])
            )
            approved = await self.push_screen_wait(
                ConfirmOperation(
                    command,
                    [{"action": action, "component": component.qualified_id}],
                )
            )
            if not approved:
                return
            result = await asyncio.to_thread(
                ComponentRunner(self.desired_topology).run_argv,
                component,
                action,
                argv,
            )
            self.query_one("#detail", Static).update(
                f"{template.template_id}:{action}\n{result.stdout or result.stderr}"
            )

        async def show_stack_details(self, stack: Any) -> None:
            reference = await self.push_screen_wait(StackDetailsScreen(stack))
            if reference:
                await self.edit_component(self.desired_topology.resolve_component(reference))

        async def open_catalog(self) -> None:
            selected = self.selected_component()
            selected_component = None
            if selected is not None and hasattr(selected, "qualified_id"):
                selected_component = self.desired_topology.resolve_component(selected.qualified_id)
            selection = await self.push_screen_wait(
                ServiceCatalogScreen(self.desired_topology, selected_component)
            )
            if selection is None:
                return
            action, reference = selection
            if action == "import":
                source_value = await self.push_screen_wait(TemplateImportScreen())
                if source_value is None:
                    return
                source = Path(source_value).expanduser()
                try:
                    plan = import_template(self.desired_topology.paths, source, apply=False)
                except (ConfigOperationError, TemplateError) as exc:
                    self.query_one("#detail", Static).update(f"Template import refused: {exc}")
                    return
                command = shlex.join(
                    [
                        "llmops",
                        "template",
                        "import",
                        str(source),
                        "--expected-hash",
                        plan["authority_hash"],
                        "--apply",
                        "--yes",
                    ]
                )
                approved = await self.push_screen_wait(
                    ConfirmOperation(
                        command,
                        [
                            {
                                "action": "import reviewed template",
                                "component": plan["template"],
                                "validation": "passed",
                                "destination": plan["destination"],
                                "authority_hash": plan["authority_hash"],
                                "restart_impact": "none",
                            }
                        ],
                        confirm_label="Import",
                        confirm_variant="primary",
                    )
                )
                if not approved:
                    return
                try:
                    result = await asyncio.to_thread(
                        import_template,
                        self.desired_topology.paths,
                        source,
                        apply=True,
                        expected_hash=plan["authority_hash"],
                    )
                except (ConfigOperationError, TemplateError) as exc:
                    self.query_one("#detail", Static).update(f"Template import failed: {exc}")
                    return
                self.query_one("#detail", Static).update(json.dumps(result, indent=2, sort_keys=True))
                self.desired_topology = llmops_cli.desired_topology(config_home)
                await self.inspect()
                return
            if action == "edit":
                component = self.desired_topology.resolve_component(reference)
                await self.edit_component(component)
                return
            if action == "clone":
                component = self.desired_topology.resolve_component(reference)
                values = await self.push_screen_wait(CloneComponentScreen(component))
                if values is None:
                    return
                plan = clone_component(
                    self.desired_topology,
                    reference,
                    values["new_id"],
                    share_profile=values["share_profile"],
                    apply=False,
                )
                command = shlex.join(
                    [
                        "llmops",
                        "component",
                        "clone",
                        reference,
                        values["new_id"],
                        "--share-profile" if values["share_profile"] else "--clone-profile",
                        "--apply",
                        "--yes",
                    ]
                )
                approved = await self.push_screen_wait(
                    ConfirmOperation(command, [{"action": "clone", "component": plan["component"]}])
                )
                if not approved:
                    return
                result = await asyncio.to_thread(
                    clone_component,
                    self.desired_topology,
                    reference,
                    values["new_id"],
                    share_profile=values["share_profile"],
                    apply=True,
                    expected_hash=plan["authority_hash"],
                )
                self.query_one("#detail", Static).update(json.dumps(result, indent=2, sort_keys=True))
                self.desired_topology = llmops_cli.desired_topology(config_home)
                await self.inspect()
                return
            if action in {"retire", "restore"}:
                restore = action == "restore"
                plan = retire_component(
                    self.desired_topology,
                    reference,
                    restore=restore,
                    apply=False,
                )
                command = f"llmops component {action} {shlex.quote(reference)} --apply --yes"
                approved = await self.push_screen_wait(
                    ConfirmOperation(command, [{"action": action, "component": reference}])
                )
                if not approved:
                    return
                component = self.desired_topology.resolve_component(reference)
                if not restore and await asyncio.to_thread(
                    ComponentRunner(self.desired_topology).is_running,
                    component,
                ):
                    await asyncio.to_thread(
                        Executor(self.desired_topology).execute_component,
                        component,
                        "stop",
                    )
                result = await asyncio.to_thread(
                    retire_component,
                    self.desired_topology,
                    reference,
                    restore=restore,
                    apply=True,
                    expected_hash=plan["authority_hash"],
                )
                self.query_one("#detail", Static).update(json.dumps(result, indent=2, sort_keys=True))
                self.desired_topology = llmops_cli.desired_topology(config_home)
                await self.inspect()
                return
            template_id = reference
            template = load_template_registry(self.desired_topology.paths)[template_id]
            values = await self.push_screen_wait(AddComponentScreen(self.desired_topology, template))
            if values is None:
                return
            plan = provision_component(
                self.desired_topology,
                template_id=template_id,
                apply=False,
                **values,
            )
            command_argv = [
                    "llmops",
                    "component",
                    "add",
                    values["component_id"],
                    "--template",
                    template_id,
                    "--profile",
                    values["profile_name"],
                    "--stack",
                    values["stack_name"],
                    "--host",
                    values["host"],
            ]
            if values["execution_user"]:
                command_argv.extend(("--execution-user", values["execution_user"]))
            for name, connection in sorted(values["connections"].items()):
                command_argv.extend(
                    (
                        "--connect",
                        f"{name}={connection['component']}@{connection['endpoint']}",
                    )
                )
            if values["create_new_profile"]:
                command_argv.append("--create-profile")
                for assignment in _flatten_values(values["profile_values"]):
                    command_argv.extend(("--set-profile", assignment))
            command_argv.extend(("--apply", "--yes"))
            command = shlex.join(command_argv)
            approved = await self.push_screen_wait(
                ConfirmOperation(
                    command,
                    [
                        {
                            "action": "provision",
                            "component": plan["component"],
                            "validation": "passed",
                            "files": plan["files"],
                            "authority_hash": plan["authority_hash"],
                            "connections": values["connections"],
                            "inferred_dependencies": sorted(
                                {
                                    connection["component"]
                                    for connection in values["connections"].values()
                                }
                            ),
                            "restart_impact": "none; component is created disabled",
                        }
                    ],
                )
            )
            if not approved:
                return
            result = await asyncio.to_thread(
                provision_component,
                self.desired_topology,
                template_id=template_id,
                apply=True,
                expected_hash=plan["authority_hash"],
                **values,
            )
            self.query_one("#detail", Static).update(json.dumps(result, indent=2, sort_keys=True))
            self.desired_topology = llmops_cli.desired_topology(config_home)
            await self.inspect()

        def action_catalog(self) -> None:
            self.run_worker(self.open_catalog(), exclusive=True)

        def action_toggle_view(self) -> None:
            selected_id = self._selected_id()
            self.view = "stacks" if self.view == "components" else "components"
            if self.status_by_id:
                self._render_status(list(self.status_by_id.values()), selected_id)
            else:
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
            operation = dispatch(
                self.topology.paths,
                argv=["update", "--apply"],
                action="update",
                target="LLM-Ops-Kit toolkit",
                command="llmops update --apply",
                plan=[{"action": "update", "component": "LLM-Ops-Kit toolkit"}],
                host="authority",
            )
            self.query_one("#detail", Static).update(
                f"Operation queued: {operation['operation_id']}\nllmops update --apply"
            )

        def action_update_apply(self) -> None:
            self.run_worker(self.apply_update(), exclusive=True)

        def action_doctor(self) -> None:
            errors = llmops_cli.validate_topology(self.topology)
            self.query_one("#detail", Static).update(
                "Configuration valid" if not errors else "\n".join(errors)
            )

        def on_button_pressed(self, event: Any) -> None:
            actions = {
                "action-refresh": self.action_refresh,
                "action-start": self.action_start,
                "action-stop": self.action_stop,
                "action-restart": self.action_restart,
                "action-logs": self.action_logs,
                "action-details": self.action_details,
                "action-configure": self.action_edit,
                "action-catalog": self.action_catalog,
                "action-topology": self.action_topology,
                "action-settings": self.action_settings,
                "action-help": self.action_help,
            }
            if event.button.id == "action-quit":
                self.exit()
                return
            action = actions.get(event.button.id)
            if action is not None:
                action()

        def on_data_table_row_highlighted(self, event: Any) -> None:
            if (
                len(self.screen_stack) != 1
                or getattr(getattr(event, "data_table", None), "id", None) != "components"
            ):
                return
            if 0 <= event.cursor_row < len(self.rows):
                self._show_detail(self.rows[event.cursor_row])

        def on_data_table_row_selected(self, event: Any) -> None:
            if (
                len(self.screen_stack) != 1
                or getattr(getattr(event, "data_table", None), "id", None) != "components"
            ):
                return
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
