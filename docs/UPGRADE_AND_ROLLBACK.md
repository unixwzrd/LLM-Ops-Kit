# Upgrade and Rollback

Back: [Documentation Index](./INDEX.md)

## Before Upgrade

```bash
git status --short
llmops doctor
llmops plan --action start
scripts/llmops-admin deploy --config-home ~/.config/llm-ops --bundle-id <bundle-id> --dry-run
```

Record the active `current` and `previous` targets on each host. Keep the prior validated runtime until the new release has completed the required operational reporting cycles.

## Upgrade

```bash
scripts/llmops-admin deploy --config-home ~/.config/llm-ops --bundle-id <bundle-id>
```

Deployment refuses dirty source by default. It applies code and the resolved host configuration atomically, leaves existing component processes alone unless restart was explicitly requested, and runs drift verification after apply.

## Verify

```bash
llmops drift --stage ~/.local/share/llm-ops/stage/<bundle-id>
llmops stack status <stack>
llmops component status <critical-component>
```

Run functional acceptance for the components changed by the release. For a model engine upgrade, use target-only component restart first and confirm proxies and agents remain running.

## Roll Back

```bash
llmops rollback --dry-run
llmops rollback
```

Rollback exchanges `current` and `previous`, so running the command again returns to the newer release. It refreshes managed command links after the pointer exchange.

After rollback, run status and functional checks. Processes that cache code in memory may require a deliberate component restart; use component scope unless downstream restart is required.

## Failed Apply

Apply installs into a new release directory and verifies content before switching. Its failure trap restores the prior `current` and `previous` targets and removes the failed release if a post-switch step fails.

Do not delete the failed stage bundle until its manifest and logs have been inspected.

## Uninstall

Use the existing uninstall runtime command only after saving any untracked configuration needed for migration. Never treat model weights, agent state, logs, or secrets as part of the runtime package.
