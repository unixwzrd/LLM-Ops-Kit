# Configuration

**Created**: 2026-07-16
**Updated**: 2026-07-21

Back: [Documentation index](./INDEX.md)

## Authority and Precedence

Configuration precedence is shipped runtime defaults, global JSON, referenced profile JSON, host snapshot values, then temporary CLI overrides. Process environment may provide secrets and documented emergency overrides, but no shell configuration file is read implicitly.

`LLMOPS_CONFIG_HOME`, `LLMOPS_DATA_HOME`, `LLMOPS_STATE_HOME`, and `LLMOPS_CACHE_HOME` select alternate runtime roots. Installed immutable releases use the role-filtered revision selected by `~/.local/llm-ops/current-config`, then fall back to the release's migration snapshot when no managed revision exists.

Mutating configuration commands use the authority's mutable `~/.config/llm-ops/` tree rather than editing `current-config`. Set `LLMOPS_AUTHORITY_CONFIG_HOME` only when the desired-state authority uses a different canonical root. Reconciliation publishes validated revisions after desired-state editing.

Canonical configuration contains:

```text
config.json
inventory.json
products.json
models/*.json
agents/*.json
services/*.json
stacks/*.json
templates/*.json
```

Optional organization and site labels are canonical display metadata:

```json
{
  "display": {
    "organization": "Example Organization",
    "site": "Local AI Lab"
  }
}
```

Plan and apply them with:

```bash
llmops config display --organization "Example Organization" --site "Local AI Lab" --plan
llmops config display --organization "Example Organization" --site "Local AI Lab" --apply --yes
```

Textual refresh and theme preferences live separately in `ui.json`. That host-local file is not included in desired-state hashes or reconciled snapshots.

## Product Releases

`products.json` records release identity independently from component lifecycle and LLM-Ops-Kit's immutable runtime version:

```json
{
  "schema_version": 1,
  "products": {
    "llama-cpp": {
      "installed_version": "build 1057 / c5a4a0bb8",
      "latest_version": "rolling",
      "update_state": "review",
      "source": "https://github.com/ggml-org/llama.cpp",
      "last_verified": "2026-07-27",
      "last_updated": "2026-07-23",
      "version_strategy": "manifest",
      "decision": "review upstream before replacement"
    }
  },
  "components": {
    "local-ai:chat": "llama-cpp",
    "local-ai:embedding": "llama-cpp"
  },
  "history": [
    {
      "product_id": "llama-cpp",
      "installed_version": "build 1057 / c5a4a0bb8",
      "recorded_at": "2026-07-27",
      "previous_version": "build 1000",
      "stack": "local-ai",
      "host": "model-host",
      "execution_user": "operator",
      "operation_id": "upgrade-2026-07-27",
      "artifact_identity": "c5a4a0bb8",
      "validation": "chat and embedding checks passed",
      "rollback": "previous locally compiled binary"
    }
  ]
}
```

Valid update states are `current`, `available`, `held`, `review`, and `unknown`. The compact status table shows the installed product version and highlights versions needing review; latest version, source, verification date, and decision remain in component details, JSON status, and:

```bash
llmops product list
llmops product show llama-cpp
llmops component version local-ai:chat
```

The product inventory is desired state and is reconciled with the topology. It does not probe or mutate upstream packages by itself.

`history` is an optional append-only installation and selection ledger. Trusted
control snapshots retain the complete ledger; role-filtered component-host
snapshots omit it. Inspect the ledger with:

```bash
llmops product history
llmops product history llama-cpp
llmops product history --newest
llmops product history --newest --tsv
llmops product show llama-cpp
```

`-n`/`--newest` selects the newest ledger entry per product, or the single
newest entry when a product ID is supplied. `-t`/`--tsv` emits a conventional
header row followed by unprefixed tab-separated values. The flags compose as
`llmops product history -n -t`; TSV and JSON output are mutually exclusive.

History records must be backed by an installation operation, immutable runtime,
artifact manifest, or retained acceptance evidence. Unknown previous versions
remain empty rather than being inferred.

`version_strategy` defaults to `manifest`. Use `observed-runtime` only when the managed product is the immutable LLM-Ops-Kit process itself, such as model-proxy or tts-bridge. That keeps a still-running older process visible until it is deliberately restarted while the selected toolkit and latest product release remain separate fields.

## Inventory

```json
{
  "schema_version": 2,
  "defaults": {
    "user": "operator",
    "port": 22,
    "install_root": "~/.local/llm-ops",
    "public_bin_dir": "~/.local/bin",
    "ssh_key": "~/.ssh/id_ed25519_llmops"
  },
  "hosts": [
    {
      "name": "model-host",
      "role": "llm",
      "host": "model-host.local",
      "control_host": "model-host.local",
      "transport": "ssh"
    }
  ]
}
```

`config.json` designates exactly one desired-state authority by inventory alias:

```json
{
  "schema_version": 2,
  "control": {
    "authority_host": "model-host"
  }
}
```

The authority host must have `trusted_control: true`. Trusted peers receive the complete secret-free catalog, but independently edited revisions are rejected rather than merged.

Supported roles are `admin`, `llm`, `agent`, and `hybrid`. Supported transports are `local` and `ssh`.

`host` is the address used by the deployment authority. `control_host` is the routable address placed in the shared observer catalog for peer-to-peer status checks and defaults to `host`. Set `control_host` explicitly when `host` is `localhost`, a loopback address, or otherwise meaningful only to the deployment authority.

Set `trusted_control` to the JSON boolean `true` only for a managed host that may issue restricted `llmops host` operations to peers. The shared catalog records this grant without distributing SSH private keys or secret values. Authentication continues to use the operator-provisioned SSH configuration, while peer execution uses the target host's configured absolute `llmops` path.

Set `peer_observable` to `false` when components run in a local desktop login domain that managed peers intentionally cannot authenticate into. Peer status then reports those components as `authority-only` instead of incorrectly reporting them as unreachable. The authoritative desktop account continues to inspect and manage them through its full configuration.

## Components

```json
{
  "id": "chat",
  "host": "model-host",
  "driver": "modelctl",
  "template_id": "llama-cpp",
  "profile": "chat",
  "enabled": false,
  "tags": ["model", "chat"],
  "depends_on": [],
  "ownership": "managed",
  "restart_policy": "never",
  "health": {
    "type": "http",
    "target": "http://127.0.0.1:11434/health",
    "timeout_seconds": 60
  },
  "timeouts": {
    "start": 900,
    "stop": 120,
    "restart": 900,
    "status": 30,
    "logs": 30
  }
}
```

Drivers are `modelctl`, `process`, `launchd`, `model-proxy`, `tts-bridge`, `ssh-tunnel`, `agent`, and gated `command`. Generic process and agent profiles define lifecycle actions as argument arrays. No agent implementation receives privileged treatment.

Tags are optional operator-defined subsystem labels used by `llmops status <tag>`. Libraries embedded inside another process are not independently manageable components unless a process, service, or health adapter is configured for them.

Lifecycle command timeouts are seconds in the range 1 through 86400. A timed-out command returns code 124 and is recorded as a failed operation; the detached worker remains independent of the TUI process.

`restart_policy` is `never` or `on-failure`. It is adapter supervision metadata, not permission to override desired state. An explicit stop records desired `stopped`; a supervised adapter must not recover that process until the operator starts it again.

## Schema-Driven Operations

Inspect templates and current fields before changing desired state:

```bash
llmops template list
llmops template show llama-cpp
llmops template fields llama-cpp
llmops component fields local-ai:chat
llmops component details local-ai:chat
```

Mutate typed fields as one validated candidate:

```bash
llmops component configure local-ai:chat \
  --set profile.llama.ctx_size=65536 \
  --set profile.server.spec_type=ngram \
  --unset profile.server.draft_model \
  --plan

llmops component configure local-ai:chat \
  --set profile.llama.ctx_size=65536 \
  --apply --yes

llmops component configure local-ai:chat \
  --set profile.mmproj_path=/models/mmproj-model.gguf \
  --apply --yes
```

`--unset` restores a schema default when one exists. Arrays and objects use JSON literals. Unknown paths, invalid values, read-only fields, and cross-field constraint violations fail before any file is replaced.

`profile.mmproj_path` is an optional llama.cpp chat-model field. Model resolution passes it to `llama-server` as `--mmproj`; preflight and startup fail when the configured file is missing. Embedding profiles reject the field, and the generic TTS model template does not expose it.

Create reusable profiles and disabled components without editing JSON:

```bash
llmops profile create worker --template standalone --values worker.json --plan
llmops component add worker --template standalone --profile worker \
  --stack local-ai --host agent-host --plan
```

Use `--connect upstream=local-ai:chat@openai` for typed endpoint references. Required endpoint connections imply lifecycle dependencies unless the template opts out. Cloning, retirement, and restoration preserve reusable profiles; restored components remain disabled until explicitly enabled.

Inspect the exact effective non-secret profile, host, execution identity, dependencies, probes, timeouts, endpoints, template, and log settings with:

```bash
llmops config effective
llmops config effective component <component>
llmops component logs <component> --list
llmops component logs <component> --channel service
llmops component logs model-proxy --channel rendered-prompt --lines 500
llmops component logs model-proxy --channel rendered-prompt --follow
```

Log channels come from the component's reviewed service template. `--list` reports the host alias, execution user, resolved remote path or provider unit, availability, readability, size, and modification time when available. Bounded reads default to 200 lines and accept at most 10,000. `--json` is supported for listing and bounded reads; streaming follow is terminal output and rejects JSON. Log paths are resolved and read on the component's configured host. A displayed remote path is never implied to exist on the controlling host, and arbitrary paths are not accepted.

Mutable desired state defaults to `~/.config/llm-ops`. Deployed commands read immutable role-filtered revisions through `current-config`, but `config display`, `component configure`, and `config reconcile` always read and write the authority tree. Set `LLMOPS_AUTHORITY_CONFIG_HOME` when the authority uses a non-default location; do not point it at `current-config`.

## Reusing Model Profiles

Interactive `llmops init` discovers model profiles under an existing default configuration root when the destination differs. Use `--model-defaults-from <path>` to select another source explicitly.

```bash
llmops init --preset local-lan \
  --model-defaults-from <existing-config-root> \
  --import-model ChatModel \
  --import-model EmbeddingModel \
  --default-chat ChatModel \
  --default-embedding EmbeddingModel
```

Legacy `env` objects are normalized to `environment`. Structured profiles remain structured. Imported model names must be unique, model paths must be absolute, home-relative, or provider references, and model types must be `llm`, `embedding`, or `tts`. Source files are never modified.

LLM-Ops-Kit's own Python commands always use the application-owned interpreter under the active immutable release. launchd and SSH never source interactive shell profiles.

External Python-backed components may select their own interpreter through fields such as `TTS_PYTHON_BIN` or structured `runtime.python_bin`. The value may reference Conda, `python -m venv`, virtualenv, uv, or another product-owned runtime. LLM-Ops-Kit passes the explicit path to that component and does not activate its environment.

## Reconciliation

Canonical desired state remains under `~/.config/llm-ops/` on the authority. Trusted control targets receive complete secret-free topology revisions through `llmops config reconcile`; component-only targets receive role-filtered revisions. Neither receives secret values.

```bash
llmops config reconcile --all-hosts --plan --json
llmops config reconcile --all-hosts --apply --yes
```

Each deployed revision contains `resolved.json` with per-file hashes. Manual changes that invalidate those hashes are conflicts and block replacement. Accepted revisions live under `~/.local/llm-ops/config-revisions/`, and `current-config` selects the active revision atomically.

## Secrets

Never put secret values in tracked JSON. Use `env:<VARIABLE>` or `seckit:<reference>` values. Imported legacy literal secret fields are converted to environment references without copying the literal value.

For current external secret injection, launch the command with required variables already present or set `LLMOPS_ENV_FILE` to an explicit untracked file. LLM-Ops-Kit does not search home, repository, or agent `.env` files.

## Validation

```bash
llmops doctor
llmops doctor --probe
llmops config show --json
llmops component list --json
llmops status --json
llmops plan --action start --json
```

Static validation rejects missing profiles, empty inventory, unknown hosts, dependency cycles, ambiguous references, unsupported drivers, disabled command-driver use, embedded secrets, and known configured port conflicts. Active probing checks connectivity and runtime prerequisites without starting or stopping anything.
