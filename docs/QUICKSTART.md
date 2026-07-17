# Quickstart

**Created**: 2026-07-16
**Updated**: 2026-07-16

Back: [Documentation index](./INDEX.md)

## Fresh Install

```bash
git clone <repository-url> LLM-Ops-Kit
cd LLM-Ops-Kit
/usr/local/bin/bash scripts/install-runtime.sh
```

The installer creates an immutable release under `~/.local/llm-ops/releases/`, updates `current`, retains the prior release as `previous`, creates internal command links under `~/.local/llm-ops/bin`, and exposes only `~/.local/bin/llmops` publicly.

## Initialize

Single host:

```bash
llmops init --preset single-host
```

Local LAN:

```bash
llmops init --preset local-lan --user <user> --model-host <model-host> --agent-host <agent-host>
```

Edit the generated JSON, replace placeholder paths, define agent actions, and enable only intended components.

```bash
llmops doctor
llmops config show --json
llmops plan --action start --json
```

## Operate

```bash
llmops component list
llmops component plan start <component>
llmops component start <component>
llmops component restart <component>
llmops component status <component>
llmops component stop <component>
```

Use `<stack>:<component>` when a short ID is ambiguous. Use `--cascade` only when downstream components must be included.

## Migrate Proof-of-Concept Configuration

```bash
llmops migrate-config --legacy-home ~/.llm-ops --dry-run --json
llmops migrate-config --legacy-home ~/.llm-ops
llmops doctor
```

Migration parses scalar assignments without executing shell files. It is idempotent for unchanged input and refuses changed input or existing destinations unless `--force` is explicitly used after review and backup. Migrated shell files are never runtime inputs.

## Repair or Remove

```bash
/usr/local/bin/bash scripts/install-runtime.sh --repair
/usr/local/bin/bash scripts/uninstall-runtime.sh
```

Use `scripts/uninstall-runtime.sh --purge` only when configuration, data, state, and cache should also be removed. Model weights, agent state, and unrelated logs are never owned by this installer.
