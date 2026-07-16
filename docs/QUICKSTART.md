# Quickstart

Back: [Documentation Index](./INDEX.md)

## Requirements

- macOS on Apple Silicon
- Python 3.9 or newer
- SSH access for each remote host
- Runtime executables required by the components you enable

## Create Configuration

For one machine:

```bash
llmops init --preset single-host
```

For a model host plus an agent host:

```bash
llmops init --preset local-lan --user <remote-user> --model-host <model-host> --agent-host <agent-host>
```

The generated starter components are disabled. Edit the files under `~/.config/llm-ops/`, replace placeholder paths, enable only the components you intend to operate, then validate:

```bash
llmops doctor
llmops config show --json
llmops plan --action start
```

`init` never installs model engines, downloads weights, changes launchd, or starts an agent.

## Operate Components

```bash
llmops component list
llmops component plan start <component>
llmops component start <component>
llmops component status <component>
llmops component restart <component>
llmops component stop <component>
```

Starting a component starts missing upstream dependencies. Restarting a component affects only that component. Stopping a component with active dependents requires confirmation through the interactive surface or an explicit `--force`; use `--cascade` to stop dependents first.

Use `<stack>:<component>` when the short ID is ambiguous.

## Operate Stacks

```bash
llmops stack list
llmops stack plan start <stack>
llmops stack start <stack>
llmops stack status <stack>
llmops stack stop <stack>
```

Stacks start in dependency order and stop in reverse dependency order. They do not prevent independent component operation.

## Deploy to a LAN

Run deployment from the administrator checkout:

```bash
scripts/llmops-admin deploy --config-home ~/.config/llm-ops --bundle-id <bundle-id> --dry-run
scripts/llmops-admin deploy --config-home ~/.config/llm-ops --bundle-id <bundle-id>
```

The command stages, validates, pushes, applies, and checks drift. A deployment includes code and a role-filtered configuration snapshot in the same immutable release.

```bash
llmops drift --stage ~/.local/share/llm-ops/stage/<bundle-id>
llmops rollback
```

Keep the previous runtime until the new release has passed the required operational reporting cycles.

## Compatibility Commands

For one release, existing wrappers remain available:

```bash
llmops modelctl <profile> status
llmops agentctl status hermes
llmops agentctl status openclaw
llmops model-proxy status
llmops tts-bridge status
```

`agentctl` has no implicit target. New configuration should use stack components.
