# Troubleshooting

**Created**: 2026-07-16
**Updated**: 2026-07-20

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

If `llmops` is missing or points at an old release, run `/usr/local/bin/bash ~/.local/llm-ops/current/scripts/install-runtime.sh --repair`. Repair uses the installed immutable release and does not require a checkout.

If configuration is missing, set `LLMOPS_CONFIG_HOME` explicitly or initialize a new root. Installed host commands normally use the role-filtered revision selected through `current-config`.

If a model, proxy, or TTS profile is not found, verify the profile exists in the canonical directory and is included in the selected host snapshot. Repository profiles and shell overrides are intentionally ignored.

If SSH update or reconciliation fails, verify noninteractive access using the inventory user, host, port, key, and optional proxy jump. The failing host remains explicit, and a partial multi-host runtime update rolls back hosts changed by that invocation.

If a component start fails, the executor removes only dependencies started by that invocation. Check component logs and readiness targets before retrying.

If configuration hash validation reports a changed file, do not merge remote changes automatically. Review the target, correct authoritative configuration when appropriate, and rerun reconciliation. Toolkit-version drift is corrected with a planned `llmops update` operation.
