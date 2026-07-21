# Textual Console

**Created**: 2026-07-20
**Updated**: 2026-07-21

Back: [Documentation index](./INDEX.md)

Run the on-demand console with:

```bash
llmops tui
```

The normal installation includes Textual. A `--minimal` installation intentionally omits it. The console runs in the foreground, starts no daemon, and remains independent of every managed model and agent.

## Dashboard

The dashboard reports condition, lifecycle, health, host, driver, observed component version, and drift. Arrow-key and mouse selection update the detail panel immediately. The selected component remains selected across manual and automatic refreshes.

Conditions use text and color:

| Condition | Color | Meaning |
|---|---|---|
| `ok` | Green | Healthy, intentionally disabled, or otherwise normal |
| `down` | Gray | Intentionally stopped by an LLM-Ops-Kit lifecycle operation |
| `attention` | Amber | Running but degraded, stale, or drifted |
| `error` | Red | Stopped unexpectedly, failed, or unreachable through an authorized route |
| `unobserved` | Cyan | Known to the authority but not observable from this host |

See [status semantics](./STATUS.md) for the complete machine-readable contract.

## Controls

| Key | Action |
|---|---|
| Up/Down | Select a row and update details |
| `r` | Refresh immediately |
| `s` | Start the selected component and missing dependencies |
| `x` | Stop the selected component after dependent-impact review |
| `b` | Restart only the selected component |
| `l` | Show recent component logs |
| `e` | Edit supported desired-state fields |
| `v` | Toggle component and stack views |
| `t` | Open the bounded topology view |
| `,` | Edit local refresh and theme settings |
| `o` | Edit shared organization and site labels |
| `?` | Open contextual help |
| `u` | Check specifically for an LLM-Ops-Kit toolkit update |
| `Ctrl+U` | Review and apply a toolkit update |
| `d` | Run deterministic configuration validation |
| `q` | Exit |

Every lifecycle or configuration mutation displays its ordered plan and equivalent `llmops` command before confirmation. A target-only stop with active dependents requires Cancel, Cascade Stop, or advanced Force Stop; the TUI uses the same safety service as the CLI.

Automatic refresh defaults to 15 seconds and pauses while a modal, edit, confirmation, or mutation is active. Local preferences are stored in `~/.config/llm-ops/ui.json` and are excluded from reconciled configuration identity. Shared organization and site labels are stored in canonical `config.json`, validated, backed up, and reconciled normally.

The component editor changes desired state only. Changing a component's host does not provision its executable, transfer data, or perform a service cutover.

## Topology

The topology page groups components under collapsible hosts and supports host, stack, driver, and condition filters. Selecting a component shows its immediate dependencies and dependents. It deliberately avoids presenting an unbounded full-system graph by default.

The same projection is available through `llmops topology show`; see [topology views](./TOPOLOGY.md).

## Beta Boundaries

The beta has no secret editor, autonomous remediation, arbitrary provisioning, component relocation, or third-party product update application. Product update providers and stateless relocation use optional adapter capabilities after their rollback contracts pass acceptance.
