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
models/*.json
agents/*.json
services/*.json
stacks/*.json
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

## Inventory

```json
{
  "schema_version": 1,
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
  "profile": "chat",
  "enabled": false,
  "tags": ["model", "chat"],
  "depends_on": [],
  "ownership": "managed",
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

Inspect the exact effective non-secret profile, host, execution identity, dependencies, probes, timeouts, endpoints, template, and log settings with:

```bash
llmops config effective
llmops config effective component <component>
llmops component logs <component> --channel service
llmops component logs model-proxy --channel rendered-prompt
```

Log paths are resolved and read on the component's configured host. A displayed remote path is never implied to exist on the controlling host.

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
