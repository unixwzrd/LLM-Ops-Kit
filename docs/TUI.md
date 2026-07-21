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
| `down` | Dark red | Intentionally stopped by an LLM-Ops-Kit lifecycle operation |
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
| `e` | Edit the selected component with its template-generated form |
| `c` | Open the Service Catalog to add, edit, clone, retire, or restore components |
| `Enter` | Open full component or stack details |
| `v` | Toggle component and stack views |
| `t` | Open the bounded topology view |
| `,` | Edit local refresh and theme settings |
| `o` | Edit shared organization and site labels |
| `h` or `?` | Open contextual help |
| `u` | Check specifically for an LLM-Ops-Kit toolkit update |
| `Ctrl+U` | Review and apply a toolkit update |
| `d` | Run deterministic configuration validation |
| `q` | Exit |

Common lifecycle and navigation actions are also clickable in the action bar. `Escape` cancels or closes every modal without applying a mutation.

Every lifecycle or configuration mutation displays its ordered plan and equivalent `llmops` command before confirmation. Confirmed long-running lifecycle and toolkit-update actions are recorded under the operational state root and executed by a detached short-lived worker. The TUI shows `starting`, `stopping`, `restarting`, `updating`, or `reconciling` while the operation is active. Exiting the TUI does not cancel or wait for the operation; use `llmops operation list` and `llmops operation show` to inspect it.

Automatic refresh defaults to 15 seconds and pauses while a modal, edit, confirmation, or mutation is active. Local preferences are stored in `~/.config/llm-ops/ui.json` and are excluded from reconciled configuration identity. Shared organization and site labels are stored in canonical `config.json`, validated, backed up, and reconciled normally.

The component editor changes desired state only. Changing a component's host does not provision its executable, transfer data, or perform a service cutover.

## Service Catalog And Details

The Service Catalog is generated from the same versioned templates used by the CLI. Add Component selects a template, component identity, stack, host alias, execution user, reusable or new profile, lifecycle fields, endpoint connections, and dependencies. Template constraints are validated before a plan is shown. For llama.cpp, selecting n-gram speculation disables and clears draft-model or MTP fields that cannot coexist.

The full-screen Details view shows effective component and profile values, value sources, execution identity, adapter and template, endpoints, dependencies, probes, timeouts, restart policy, runtime identity, versions, and log channels. Tool templates such as RTK expose their reviewed actions in the same view.

Canonical writes execute on `control.authority_host`. Starting the TUI on another trusted controller transparently opens the authority-host TUI through SSH. Untrusted or stale controllers cannot write desired state.

## Topology

The topology page groups components under collapsible hosts and provides populated host, stack, driver, and condition selectors. Selecting a component shows its immediate dependencies and dependents. It deliberately avoids presenting an unbounded full-system graph by default.

The same projection is available through `llmops topology show`; see [topology views](./TOPOLOGY.md).

## Beta Boundaries

The beta has no raw secret editor, autonomous remediation, data-plane workflow engine, stateful component relocation, or third-party product update application. Reviewed built-in and authority-local templates can provision configuration and lifecycle integration, but changing a host field alone remains a desired-state edit rather than service or data relocation. Product update providers and stateless relocation use optional adapter capabilities only after their rollback contracts pass acceptance.
