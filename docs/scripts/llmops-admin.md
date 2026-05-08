# llmops-admin

**Created**: 2026-04-27
**Updated**: 2026-05-07

Back: [Script Guides](./README.md)

Administrator workstation deployment command.

```bash
scripts/llmops-admin inventory-validate
scripts/llmops-admin bootstrap-host [--role <role>] [--tag <tag>] [--host-name <name>] [--dry-run]
scripts/llmops-admin stage [--bundle-id <id>] [--role <role>] [--tag <tag>] [--dry-run]
scripts/llmops-admin stage-validate [--stage <path>] [--role <role>] [--tag <tag>] [--no-package]
scripts/llmops-admin deploy-report [--stage <path>] [--role <role>] [--tag <tag>] [--no-package]
scripts/llmops-admin push [--stage <path>] [--workers <n>] [--dry-run]
scripts/llmops-admin apply [--stage <path>] [--workers <n>] [--restart <script>] [--dry-run]
scripts/llmops-admin config-settings [--host-name <name>] [--model <profile>]
scripts/llmops-admin config-doctor [--role <role>] [--model <profile>] [--dry-run]
scripts/llmops-admin migrate-config [--legacy-home <path>] [--output <path>] [--dry-run] [--force]
scripts/llmops-admin model-inspect <model.gguf> [--json] [--no-cache]
scripts/llmops-admin model-add <name> --gguf <model.gguf> [--output <path>] [--dry-run] [--force]
scripts/llmops-admin model-render-env <name> [--profile-path <path>] [--json]
scripts/llmops-admin model-simulate <name> [--profile-path <path>] [--action start|status|stop]
scripts/llmops-admin model-profile-doctor <name> [--profile-path <path>] [--remote]
scripts/llmops-admin agent-render-env openclaw|hermes [--profile-path <path>] [--json]
scripts/llmops-admin agent-simulate openclaw|hermes [--profile-path <path>] [--action start|status|stop]
scripts/llmops-admin service-render-env model-proxy|tts-bridge [--profile-path <path>] [--json]
scripts/llmops-admin deploy-plan [--role <role>] [--tag <tag>] [--host-name <name>] [--bundle-id <id>] [--dry-run]
```

Use this command from the administrator workstation to:

- validate host inventory
- bootstrap SSH access
- build local deployment bundles
- validate staged deployment bundles and host config checksums
- report staged deployment bundle/package/release mapping
- push packages and host config in parallel
- apply a pushed bundle on remote hosts
- install or refresh deployed runtime scripts and command links
- inspect rendered config and source layers
- inspect the platform-neutral config/state/cache/log path layout
- plan or write JSON config migration outputs from legacy env/profile files
- inspect GGUF metadata before generating a model profile
- generate a JSON model profile from GGUF metadata
- render a JSON model profile into shell-compatible environment values
- validate and simulate model runner actions without launching a model
- render a JSON agent profile into shell-compatible environment values
- validate and simulate agent runner actions without launching a backend
- render JSON service profiles for model proxy and TTS bridge wrappers
- inspect selected deployment hosts and target paths without staging or SSH

Start with [Deployment Overview](../DEPLOYMENT_OVERVIEW.md) for the full
operator workflow.

The target hosts can be cloud instances, local servers, virtual machines, or
hybrid nodes. The inventory decides where the bundle goes; the admin workstation
does the staging and fan-out.

Default admin paths use the platform-neutral layout:

- inventory: `~/.config/llm-ops/inventory.json`
- stage root: `~/.local/share/llm-ops/stage`
- staged host config: `hosts/<host>/config.env` and `hosts/<host>/config.json`

## Config Rework Helpers

The current config rework keeps JSON as the new canonical format and treats
legacy env and shell profile files as migration inputs.

Inspect the resolved platform-neutral path layout without writing files:

```bash
scripts/llmops-admin config-doctor --dry-run
```

Plan migration from the current legacy layout without writing files:

```bash
scripts/llmops-admin migrate-config --dry-run
```

The dry run reports each source and destination. A real migration writes:

- `config.json`
- `models/<profile>.json`
- `agents/<backend>.json`
- `services/model-proxy.json`
- `services/tts-bridge.json`

User model overrides are merged with shipped model profiles case-insensitively;
the shipped profile seeds defaults and the user override wins for duplicate
variables. Runtime proxy and TTS bridge env values are also split into service
profiles when present. Existing JSON outputs are not overwritten unless
`--force` is used.

Inspect a GGUF model without starting it:

```bash
scripts/llmops-admin model-inspect /path/to/Qwen3.6.gguf
```

The command reads only the GGUF header and metadata table. It reports the model
id, display name, architecture, context length when present, and metadata key
count. By default it caches metadata under `~/.cache/llm-ops/gguf-metadata/`;
use `--no-cache` for read-only inspection.

Generate a first-pass JSON profile from GGUF metadata:

```bash
scripts/llmops-admin model-add qwen3.6 --gguf /path/to/Qwen3.6.gguf --dry-run
scripts/llmops-admin model-add qwen3.6 --gguf /path/to/Qwen3.6.gguf
```

The default destination is `~/.config/llm-ops/models/<name>.json`. Use
`--output <file-or-directory>` to write elsewhere. Existing profile files are
not overwritten unless `--force` is supplied.

`model-add` also accepts llama-server performance and feature switches:

```bash
scripts/llmops-admin model-add qwen3.6 \
  --gguf /path/to/Qwen3.6.gguf \
  --cache-prompt \
  --cache-reuse 512 \
  --slot-save-path ~/.local/state/llm-ops/slots \
  --spec-type ngram-map \
  --spec-ngram-size-n 12 \
  --spec-ngram-size-m 48 \
  --perf \
  --fa \
  --no-cpu-moe \
  --no-host
```

Use `--extra-flag <flag-or-value>` for newly added llama-server switches before
they have first-class profile fields.

Render a JSON profile into the current runner-facing env shape:

```bash
scripts/llmops-admin model-render-env qwen3.6
scripts/llmops-admin model-render-env qwen3.6 --profile-path ./qwen3.6.json
```

Simulate runner behavior without starting `llama-server`:

```bash
scripts/llmops-admin model-simulate qwen3.6 --profile-path ./qwen3.6.json --action start
scripts/llmops-admin model-simulate qwen3.6 --profile-path ./qwen3.6.json --action status
```

Simulate agent runner behavior without starting OpenClaw or Hermes:

```bash
scripts/llmops-admin agent-simulate openclaw --action start
scripts/llmops-admin agent-simulate hermes --action status
```

Render a JSON agent profile into the current `agentctl` env shape:

```bash
scripts/llmops-admin agent-render-env openclaw
scripts/llmops-admin agent-render-env openclaw --profile-path ./openclaw.json
```

Render a JSON service profile into the current wrapper env shape:

```bash
scripts/llmops-admin service-render-env model-proxy
scripts/llmops-admin service-render-env tts-bridge --profile-path ./tts-bridge.json
```

Plan deployment host selection and target paths without building a package,
writing staged files, or opening SSH connections:

```bash
scripts/llmops-admin deploy-plan --dry-run --bundle-id smoke
scripts/llmops-admin deploy-plan --role agent --dry-run --bundle-id smoke-agent
```

Flag local or remote profile JSON that is missing fields added by newer
LLM-Ops-Kit versions:

```bash
scripts/llmops-admin model-profile-doctor qwen3.6 --profile-path ./qwen3.6.json
scripts/llmops-admin model-profile-doctor qwen3.6 --profile-path ./remote-qwen3.6.json --remote
```
