# Upgrade and Rollback

**Created**: 2026-07-16
**Updated**: 2026-07-16

Back: [Documentation index](./INDEX.md)

## Local Installation

Run the installer from the new clean checkout. It creates a new release, preserves the old `current` target as `previous`, and atomically updates links.

```bash
/usr/local/bin/bash scripts/install-runtime.sh
/usr/local/bin/bash scripts/install-runtime.sh --repair
```

`--repair` does not copy source or create a release. It validates the active target and reconstructs managed links and install state.

## LAN Upgrade

```bash
llmops doctor
llmops deploy --bundle-id <release> --dry-run
llmops deploy --bundle-id <release>
llmops drift --stage ~/.local/share/llm-ops/stage/<release>
```

Retain the prior release until the new version passes operational acceptance. Restart only changed components.

## Rollback

```bash
llmops rollback --dry-run
llmops rollback
```

Rollback exchanges `current` and `previous` and reconstructs managed links. A second rollback exchanges them again. Processes that already loaded code may require a deliberate component restart.

## Uninstall

```bash
/usr/local/bin/bash scripts/uninstall-runtime.sh
/usr/local/bin/bash scripts/uninstall-runtime.sh --purge
```

Default uninstall removes the runtime, managed links, and install record while preserving canonical configuration, operational data, state, and cache. `--purge` removes those LLM-Ops-Kit roots too. Model weights and agent-owned state are outside installer ownership.
