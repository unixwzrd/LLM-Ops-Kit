# Troubleshooting

**Created**: 2026-07-16
**Updated**: 2026-07-16

Back: [Documentation index](./INDEX.md)

Start with read-only output:

```bash
llmops doctor --json
llmops config show --json
llmops component status <component> --json
llmops component logs <component>
llmops drift --stage <stage> --json
```

If `llmops` is missing or points at an old release, run `/usr/local/bin/bash scripts/install-runtime.sh --repair` from the matching source checkout.

If configuration is missing, set `LLMOPS_CONFIG_HOME` explicitly or initialize a new root. Installed host commands normally use the configuration snapshot bundled under `current/config`.

If a model, proxy, or TTS profile is not found, verify the profile exists in the canonical directory and is included in the selected host snapshot. Repository profiles and shell overrides are intentionally ignored.

If SSH deployment fails, verify noninteractive access using the inventory user, host, port, key, and optional proxy jump. Deployment retries transient push and apply failures three times and then reports the failing host.

If a component start fails, the executor removes only dependencies started by that invocation. Check component logs and readiness targets before retrying.

If drift reports a hash difference, do not merge remote changes. Compare the active release against the desired stage, correct authoritative configuration, and redeploy.
