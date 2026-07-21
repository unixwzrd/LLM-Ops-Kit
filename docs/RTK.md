# RTK Integration

**Created**: 2026-07-21
**Updated**: 2026-07-21

Back: [Documentation index](./INDEX.md)

RTK is represented as a `tool` component. It reports installation, version, telemetry state, verification, and gain metrics. Start and stop do not apply.

```bash
llmops profile create rtk --template rtk --values rtk-profile.json --plan
llmops component add rtk --template rtk --profile rtk --stack tools --host agent-host --plan
llmops component action tools:rtk version --plan
llmops component action tools:rtk telemetry --plan
llmops component action tools:rtk verify --plan
llmops component action tools:rtk metrics --plan
llmops component action tools:rtk configure --plan
llmops component action tools:rtk enable-canary-plan --plan
llmops component action tools:rtk disable-canary-plan --plan
```

The built-in profile requires telemetry disabled, and RTK health is degraded if its telemetry probe does not report disabled. Component status extracts the observed RTK version from the installed executable.

The Hermes canary remains review-gated. `enable-canary-plan` and `disable-canary-plan` are dry runs; they never write files. The reviewed live dry run identified the Hermes plugin module, plugin manifest, and Hermes configuration as the owned targets and wrote nothing. Before exposing a mutating Enable Canary action, LLM-Ops-Kit must back up those targets, capture the gain baseline, prove automatic rollback after injected failure, and receive explicit operator approval. It does not enable RTK globally for shells, Codex, or unrelated agents.

Use raw commands for exact regression failures, tracebacks, snapshots, diffs, and ordering-sensitive logs. Compressed output is an optimization, not the evidence authority.
