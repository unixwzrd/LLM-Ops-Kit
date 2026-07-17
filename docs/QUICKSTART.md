# Quickstart

Back: [Documentation index](./INDEX.md)

## Prerequisites

Confirm macOS, Apple Silicon, Python 3.9 or newer, GNU Bash at `/usr/local/bin/bash`, and SSH access to every configured remote host. LLM-Ops-Kit does not install engines, agents, or model weights.

## Fresh Install

```bash
git clone <repository-url> LLM-Ops-Kit
cd LLM-Ops-Kit
/usr/local/bin/bash scripts/install-runtime.sh
```

The installer creates an immutable release under `~/.local/llm-ops/releases/`, updates `current`, retains the prior release as `previous`, creates internal driver links under `~/.local/llm-ops/bin`, and exposes only `~/.local/bin/llmops` publicly.

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
llmops component list
llmops component plan start <component>
llmops component start <component>
llmops component restart <component>
llmops component status <component>
llmops component stop <component>
```

Use `<stack>:<component>` when a short ID is ambiguous. Generated components remain disabled until their profiles are reviewed and the operator explicitly enables them.

## Existing Proof-of-Concept Installation

Follow [Migration](./MIGRATION.md) before enabling migrated components.

## Repair or Remove

```bash
/usr/local/bin/bash scripts/install-runtime.sh --repair
/usr/local/bin/bash scripts/uninstall-runtime.sh
```

Use `scripts/uninstall-runtime.sh --purge` only when configuration, data, state, and cache should also be removed. Model weights, agent state, and unrelated logs are never owned by the installer.
