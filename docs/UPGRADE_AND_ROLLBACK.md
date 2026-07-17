# Upgrade and Rollback

**Created**: 2026-07-16
**Updated**: 2026-07-17

Back: [Documentation index](./INDEX.md)

## Check and Plan

```bash
llmops update --check
llmops update --plan
llmops update --plan --version <version> --json
```

Check and plan operations do not download artifacts or change the installation. Until the first GitHub release is published, use a local release artifact for acceptance testing:

```bash
llmops update --plan --archive /path/to/LLM-Ops-Kit-<version>.tar.xz --checksum-file /path/to/LLM-Ops-Kit-<version>.tar.xz.sha256
```

## Local Update

```bash
llmops update --apply --version <version>
```

The update downloads the archive and checksum from GitHub, verifies the SHA-256 digest, rejects unsafe archive paths, and invokes the bundled immutable installer. It does not require or update a source checkout.

An offline or locally staged update uses:

```bash
llmops update --apply --archive /path/to/LLM-Ops-Kit-<version>.tar.xz --checksum-file /path/to/LLM-Ops-Kit-<version>.tar.xz.sha256
```

## Checkout Installation

Maintainers may still run the installer from a clean checkout. It creates a new release, preserves the old `current` target as `previous`, and atomically updates links.

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

`llmops update` currently updates one local runtime. Cross-host version discovery and coordinated remote update remain release-gate work; continue using the checksummed deployment bundle for the two-host environment until that work is complete.

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
