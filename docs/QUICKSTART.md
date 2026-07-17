# Quickstart

**Created**: 2026-07-16
**Updated**: 2026-07-17

Back: [Documentation index](./INDEX.md)

## Prerequisites

Confirm macOS, Apple Silicon, Python 3.9 or newer, GNU Bash at `/usr/local/bin/bash`, and SSH access to every configured remote host. LLM-Ops-Kit does not install engines, agents, or model weights.

## Fresh Install

```bash
mkdir -p /tmp/llmops-install
cd /tmp/llmops-install
curl -fLO https://github.com/unixwzrd/LLM-Ops-Kit/releases/download/<version>/install-llmops
curl -fLO https://github.com/unixwzrd/LLM-Ops-Kit/releases/download/<version>/install-llmops.sha256
shasum -a 256 -c install-llmops.sha256
chmod +x install-llmops
./install-llmops --version <version>
```

The bootstrap downloads and verifies `LLM-Ops-Kit-<version>.tar.xz`, then invokes its bundled installer. A Git checkout is not required. The installer creates an immutable release under `~/.local/llm-ops/releases/`, updates `current`, retains the prior release as `previous`, creates internal driver links under `~/.local/llm-ops/bin`, and exposes only `~/.local/bin/llmops` publicly.

No release has been published yet; `<version>` remains a placeholder until operator-v1 acceptance is complete. The maintainer build command is:

```bash
python3 scripts/build-release.py --output-dir dist --version <version>
```

It emits the runtime archive, archive checksum, public manifest, standalone bootstrap, and bootstrap checksum. Release builds refuse dirty source trees.

The installer reports when its public command directory is not on `PATH`; it does not silently edit shell startup files. Add that directory once or invoke `~/.local/bin/llmops` explicitly.

## Guided Initialization

Single host:

```bash
llmops init --preset single-host
```

Local LAN:

```bash
llmops init --preset local-lan --user <user> --model-host <model-host> --agent-host <agent-host>
```

When another configuration root contains model profiles, initialization lists them and asks whether to select profiles, import all, or import none. Selected legacy `env` profiles become canonical `environment` profiles, literal secret fields become `env:<VARIABLE>` references, and selected chat, embedding, and TTS defaults are bound to disabled components.

For automation, use `--model-defaults-from`, repeat `--import-model`, and provide `--default-chat`, `--default-embedding`, or `--default-tts`. Use `--import-all-models` to import every valid profile or `--no-model-import` to suppress discovery. Non-interactive and `--json` execution never prompt.

## Validate

```bash
llmops doctor
llmops doctor --probe
llmops config show --json
llmops plan --action start --json
```

`doctor` performs static validation. `doctor --probe` also checks SSH connectivity, Python, GNU Bash, launchd, model and interpreter paths, architecture, and memory without changing services.

## Operate

```bash
llmops status
llmops status model
llmops status <profile-name>
llmops stack status
llmops component list
llmops component plan start <component>
llmops component start <component>
llmops component restart <component>
llmops component status <component>
llmops component stop <component>
```

Use `<stack>:<component>` when a short ID is ambiguous. Generated components remain disabled until their profiles are reviewed and the operator explicitly enables them.

`llmops stack status` may omit the stack name when exactly one stack is configured. Mutating stack commands always require an explicit stack name.

The administrator configuration has the complete cross-host view. Immutable role-filtered snapshots intentionally expose only components assigned to that managed host. A future observer snapshot will provide a portable read-only global view from additional trusted hosts without distributing mutation authority.

## Existing Proof-of-Concept Installation

Follow [Migration](./MIGRATION.md) before enabling migrated components.

## Repair or Remove

```bash
/usr/local/bin/bash scripts/install-runtime.sh --repair
/usr/local/bin/bash scripts/uninstall-runtime.sh
```

Use `scripts/uninstall-runtime.sh --purge` only when configuration, data, state, and cache should also be removed. Model weights, agent state, and unrelated logs are never owned by the installer.
