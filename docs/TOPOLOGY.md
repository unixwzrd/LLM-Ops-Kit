# Topology Views

**Created**: 2026-07-21
**Updated**: 2026-07-21

Back: [Documentation index](./INDEX.md)

Topology views are read-only projections of canonical hosts, components, and dependency edges.

```bash
llmops topology show
llmops topology show --component <component>
llmops topology show --host <host>
llmops topology show --stack <stack>
llmops topology show --adapter <driver>
llmops topology show --format table|json|mermaid|dot
```

The default table groups components by host. A component selection includes only the selected component, its immediate dependencies, and its immediate dependents. Host, stack, and adapter filters bound larger installations before rendering.

Mermaid and DOT output use dependency-provider to dependent-consumer edges. They describe topology, not the deterministic sequence selected for a particular lifecycle plan.

The Textual topology page uses the same projection and adds condition filtering and collapsible host groups.
