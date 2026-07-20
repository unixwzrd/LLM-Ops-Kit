# Quickstart

**Created**: 2026-07-16
**Updated**: 2026-07-20

Back: [Documentation index](./INDEX.md)

## Install

Download the standalone installer and checksum from the selected GitHub release, verify it, and run it:

```bash
curl -fLO https://github.com/unixwzrd/LLM-Ops-Kit/releases/download/<version>/install-llmops
curl -fLO https://github.com/unixwzrd/LLM-Ops-Kit/releases/download/<version>/install-llmops.sha256
shasum -a 256 -c install-llmops.sha256
chmod +x install-llmops
./install-llmops --version <version>
```

The installer bootstraps a verified UV binary when necessary, installs a managed Python under `~/.local/llm-ops/python/`, installs the project and Textual from the archive's offline wheelhouse, and switches the immutable `current` release only after verification. It does not require a checkout or modify shell startup files.

Use `--minimal` to omit Textual. Repair the active installation using its installed runtime resource:

```bash
/usr/local/bin/bash ~/.local/llm-ops/current/scripts/install-runtime.sh --repair
```

## Initialize

```bash
llmops init --preset single-host
llmops init --preset local-lan --user <user> --model-host <model-host> --agent-host <agent-host>
```

Interactive initialization can import selected model profiles from another configuration root and bind chat, embedding, and TTS defaults. Generated components remain disabled until reviewed.

For automation:

```bash
llmops init --preset local-lan --model-defaults-from ~/.config/llm-ops --import-model ChatModel --import-model EmbeddingModel --default-chat ChatModel --default-embedding EmbeddingModel
```

Non-interactive and JSON execution never prompt.

## Validate And Operate

```bash
llmops doctor --probe
llmops adapter doctor
llmops status
llmops component list
llmops component plan start <component>
llmops component start <component>
llmops component restart <component>
llmops component logs <component>
llmops stack status
llmops tui
```

Use `<stack>:<component>` when a short ID is ambiguous. `llmops stack status` may omit the stack when exactly one stack exists; mutating stack commands require an explicit stack.

## Synchronize A LAN

From the desired-state authority:

```bash
llmops config reconcile --all-hosts --plan --json
llmops config reconcile --all-hosts --apply --yes
llmops update --all-hosts --plan --version <version>
llmops update --all-hosts --apply --version <version>
```

The configuration operation sends role-filtered snapshots. The update operation sends the same verified release to every observable managed host. Neither command depends on remote login-shell initialization.
