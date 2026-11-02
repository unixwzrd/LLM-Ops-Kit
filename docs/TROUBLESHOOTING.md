# Troubleshooting

**Created**: 2026-07-16
**Updated**: 2026-11-02

Back: [Documentation index](./INDEX.md)

Start with read-only output:

```bash
llmops doctor --json
llmops config show --json
llmops component status <component> --json
llmops component logs <component>
llmops status --json
llmops config hash --json
llmops config reconcile --all-hosts --plan --json
```

If `llmops` is missing or points at an old release, run `bash ~/.local/llm-ops/current/scripts/install-runtime.sh --repair`. Repair uses the installed immutable release and does not require a checkout.

If configuration is missing, set `LLMOPS_CONFIG_HOME` explicitly or initialize a new root. Installed host commands normally use the role-filtered revision selected through `current-config`.

If a model, proxy, or TTS profile is not found, verify the profile exists in the canonical directory and is included in the selected host snapshot. Repository profiles and shell overrides are intentionally ignored.

If SSH update or reconciliation fails, verify noninteractive access using the inventory user, host, port, key, and optional proxy jump. The failing host remains explicit, and a partial multi-host runtime update rolls back hosts changed by that invocation.

If a component start fails, the executor removes only dependencies started by that invocation. Check component logs and readiness targets before retrying.

If configuration hash validation reports a changed file, do not merge remote changes automatically. Review the target, correct authoritative configuration when appropriate, and rerun reconciliation. Toolkit-version drift is corrected with a planned `llmops update` operation.

## Following Service Logs

Ordinary `tail -F <log-file>` and `llmops component logs <component> --follow` should show new service output. Periodic MARKTIME lines are appended by a separate timer; they are not proof that application output is being appended correctly.

Older launchers opened service output without append mode. A marker could extend the file beyond the producer's current offset, causing later application output to overwrite earlier bytes rather than extend EOF. Restarting `tail` cannot correct the producer's open descriptor. The corrected launchers archive intentionally at startup, then open output in append mode. Python TTS/bridge output is unbuffered. The bridge's rotating logger also reopens only standard descriptors already attached to its previous log inode onto the new active file; unrelated streams are left alone.

Adoption requires the corrected runtime and a controlled reload of the affected services during an idle window. Keep existing logs and use the component's configured host/user/path; do not delete logs or restart the whole stack merely to diagnose a silent tail. This correction does not change model weights, engine dependencies, verbosity or the proxy's metadata-only privacy policy. Existing copy/truncate maintenance still has its usual concurrent-write window; this is not a guarantee of lossless multi-process rotation.
