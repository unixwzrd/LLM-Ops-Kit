"""Read-only topology projections and portable graph renderers."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from .llmops_topology import Component, Topology


def project_topology(
    topology: Topology,
    *,
    component: Optional[str] = None,
    host: Optional[str] = None,
    stack: Optional[str] = None,
    adapter: Optional[str] = None,
) -> dict[str, Any]:
    """Return a bounded, stable topology projection."""

    components = topology.all_components()
    if component:
        target = topology.resolve_component(component)
        related = {target.qualified_id, *target.depends_on}
        related.update(
            item.qualified_id
            for item in components
            if target.qualified_id in item.depends_on
        )
        components = [item for item in components if item.qualified_id in related]
    if host:
        components = [item for item in components if item.host == host]
    if stack:
        components = [item for item in components if item.stack == stack]
    if adapter:
        components = [item for item in components if item.driver == adapter]
    selected = {item.qualified_id for item in components}
    records = [
        {
            "id": item.qualified_id,
            "component_id": item.component_id,
            "stack": item.stack,
            "host": item.host,
            "driver": item.driver,
            "profile": item.profile,
            "enabled": item.enabled,
            "ownership": item.ownership,
            "tags": list(item.tags),
            "depends_on": list(item.depends_on),
            "dependents": sorted(
                candidate.qualified_id
                for candidate in topology.all_components()
                if item.qualified_id in candidate.depends_on
            ),
        }
        for item in components
    ]
    edges = [
        {"from": dependency, "to": item.qualified_id}
        for item in components
        for dependency in item.depends_on
        if dependency in selected
    ]
    return {
        "hosts": sorted({item.host for item in components}),
        "components": records,
        "edges": edges,
    }


def render_table(projection: dict[str, Any]) -> str:
    """Render a host-grouped topology summary."""

    lines: list[str] = []
    by_host: dict[str, list[dict[str, Any]]] = {}
    for item in projection["components"]:
        by_host.setdefault(item["host"], []).append(item)
    for host in sorted(by_host):
        lines.append(f"HOST {host}")
        for item in sorted(by_host[host], key=lambda value: value["id"]):
            dependencies = ", ".join(item["depends_on"]) or "none"
            lines.append(
                f"  {item['id']}  driver={item['driver']}  profile={item['profile']}  depends_on={dependencies}"
            )
    return "\n".join(lines)


def _node_id(value: str) -> str:
    return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", value)


def render_mermaid(projection: dict[str, Any]) -> str:
    """Render the bounded projection as Mermaid."""

    lines = ["flowchart LR"]
    by_host: dict[str, list[dict[str, Any]]] = {}
    for item in projection["components"]:
        by_host.setdefault(item["host"], []).append(item)
    for index, host in enumerate(sorted(by_host)):
        lines.append(f'  subgraph host_{index}["{host}"]')
        for item in sorted(by_host[host], key=lambda value: value["id"]):
            lines.append(f'    {_node_id(item["id"])}["{item["id"]}"]')
        lines.append("  end")
    for edge in projection["edges"]:
        lines.append(f'  {_node_id(edge["from"])} --> {_node_id(edge["to"])}')
    return "\n".join(lines)


def render_dot(projection: dict[str, Any]) -> str:
    """Render the bounded projection as Graphviz DOT."""

    lines = ["digraph llmops {", "  rankdir=LR;"]
    for item in projection["components"]:
        lines.append(f'  "{item["id"]}" [label={json.dumps(item["id"])}];')
    for edge in projection["edges"]:
        lines.append(f'  "{edge["from"]}" -> "{edge["to"]}";')
    lines.append("}")
    return "\n".join(lines)
