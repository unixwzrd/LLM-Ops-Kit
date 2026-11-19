# Agent Operator Guide

**Created**: 2026-11-18
**Updated**: 2026-11-18

Use the same `llmops` CLI from Hermes, OpenClaw, or any agent with a shell on an approved controller. LLM Ops Kit coordinates existing services; installing it does not install Hermes, OpenClaw, models, or a credential manager. The [portable skill](../skills/llmops/SKILL.md) teaches the workflow. It is not an access grant, a trust boundary, or a reason to give an agent an operator's shell or credentials.

## Discover or install

First establish where the agent's terminal actually runs (`hostname`, `id -un`, `command -v llmops`). Use the existing launcher and topology when present. If the host lacks an authorized route, hand the work back to the operator; do not create keys, change sudoers, or substitute another account's configuration to make it work.

For a new installation, ask the operator to select the macOS host, service/controller account, installation scope, and exact release tag. Follow the [verified installer instructions](../README.md#install) in a fresh working directory. Download both assets from the selected release, verify the installer before executing it, and stop on any checksum or download failure. The installer verifies the runtime archive separately. Upgrades to an existing install should use the [update plan and rollback workflow](UPGRADE_AND_ROLLBACK.md), not a fresh bootstrap over it. `--prefix` selects the active runtime for that prefix; it is not a dry run.

For an isolated evaluation, use a private scratch home and a clean environment without inherited `LLMOPS_*` or `XDG_*` settings. Pass separate absolute `--prefix`, `--public-bin-dir`, and `--state-home` paths under that scratch directory to the verified installer. For lab commands, set both `LLMOPS_CONFIG_HOME` and `LLMOPS_AUTHORITY_CONFIG_HOME` to the same new lab configuration root, and set `LLMOPS_STATE_HOME`, `LLMOPS_DATA_HOME`, `LLMOPS_CACHE_HOME` and `LLMOPS_RUN_DIR` to private lab paths. Do not point the lab at live PIDs, listeners, configuration, credentials or data.

## Configure and preview

Initialize only an approved **new** configuration root. For a single host, `llmops init --preset single-host --no-model-import --json` writes a starter without importing an existing model profile or starting services. For a trusted LAN, use the [Quickstart](QUICKSTART.md#initialize) after the operator identifies each host and account. Do not use `init --force` to fix a deployed installation.

Inspect `llmops template list`, `llmops component list`, `llmops doctor --probe --json`, and `llmops status --all --json` where the route permits them. Configure an existing component through its schema, following [Configuration](CONFIGURATION.md). For example, set `component` to its qualified ID, and `setting` to a **non-secret** assignment taken from `llmops component fields "$component"`:

```bash
llmops component configure "$component" --set "$setting" --plan --json
```

Propose only the narrow change requested. Where the subcommand supports `--expected-hash`, use `authority_hash` from the reviewed mutation plan, not `config hash` (which describes the active snapshot). An apply to desired state and a restart of a live service are distinct actions. Do not also reconcile peers, upgrade other products, or restart components unless that impact was reviewed and authorized. A route that permits only status and lifecycle may reject `doctor`, configuration and log access by design.

## Load the skill

Copy the reviewed `skills/llmops/` directory from an identified repository revision to the intended agent's skill root (or give a shell-capable agent the Markdown directly). Avoid overwriting an existing skill of the same name. Use the host's supported discovery mechanism, not a symlink to a writable production checkout:

- **Hermes:** Put `llmops/` under the intended profile's `skills/` directory and check `hermes skills list` for that profile. See [Hermes skills documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/).
- **OpenClaw:** Put `llmops/` under the intended workspace's `skills/` directory and check `openclaw skills list` in that context. See [OpenClaw skills documentation](https://docs.openclaw.ai/tools/skills).
- **Other agents:** Follow the host's [Agent Skills](https://agentskills.io/specification) loading convention. The skill has no install hooks or extra agent-specific dependencies.

## Evaluate without risking the agent's own session

1. **Observe:** In a fresh agent conversation, ask: “Use the LLM Ops skill to report the lifecycle, health and drift of `<stack>:<component>`. Do not change anything.” Compare with independently run CLI status. Try a disabled or deliberately unobservable fixture and verify the agent does not interpret it as an unexpected outage.
2. **Preview:** Ask for a restart plan for one disposable service. Verify the assistant names the exact component, reports prerequisites and interruption, and does not perform the restart until authorized. Use a test fixture with an isolated configuration and a process you can stop independently.
3. **Operate:** Approve only the disposable component, then check its start time and readiness from the controller. Verify unrelated components were left alone. For a self-restart request, require the agent to give the operator the command and verification steps before any interruption. An independent controller must run and verify an actual self-restart; use a disposable agent/profile and an idle window for that acceptance test. Native `llmops operation list` and `llmops operation show` inspect operations already dispatched by a supported background workflow (such as the TUI); these commands do not enqueue an operation.

## Recover after a credential change

Before a planned credential-provider update, have the owner confirm which services consume its credentials, what healthy looks like on each consumer's actual route, and how to revert the provider and credential source independently. Keep the recovery material private and outside the repository. Do not bundle a credential migration, toolkit update, and service restart into one step.

Check the failing component's observed health and readiness, not just whether its PID exists. Distinguish a missing SSH route, a running gateway with an unavailable dashboard, and failed authentication on the actual client route. If the fault began with a credential-manager update, check which loader the service actually uses and have the owner verify the expected credential is present there. Do not copy values into prompts, logs, command-line arguments, or the repository. Do not assume a credential manager's successful install or rollback also restored the agent's environment. Repair credentials as a separate owner-approved operation, then restart and verify only the affected service from the controller. If status or health still fails, report the failing step and stop rather than cycling the entire stack.
