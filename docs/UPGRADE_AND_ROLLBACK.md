# Upgrade and Rollback

Use this runbook when upgrading an existing checkout-based or directory-style
LLM-Ops-Kit installation to staged releases.

## Preflight

Do not update or clean the target host's source checkout as part of runtime
deployment. Preserve untracked operational files until they are inventoried.

```bash
git status --short --branch
git log -1 --oneline
./scripts/precheck
scripts/llmops-admin migrate-config --legacy-home ~/.llm-ops --dry-run
scripts/llmops-admin inventory-validate --inventory <inventory.json>
```

Confirm that the inventory uses the accepted SSH identity and the intended
`install_root`. Inventory paths beginning with `~/` expand in the remote
account's home directory.

## Configuration Migration

Preview migration first. A dry run reports sources and destinations without
writing files.

```bash
scripts/llmops-admin migrate-config \
  --legacy-home ~/.llm-ops \
  --output ~/.config/llm-ops/config.json \
  --dry-run
```

Write the migration only after reviewing the plan:

```bash
scripts/llmops-admin migrate-config \
  --legacy-home ~/.llm-ops \
  --output ~/.config/llm-ops/config.json
```

Existing destinations are refused. Use `--force` only after backing up and
reviewing the generated JSON. Repeating a migration with unchanged inputs must
produce identical documents.

Paths under `<legacy-home>/current` are rebased to the runtime containing the
migration command. Invoking the installed `bin/llmops-admin` entry point uses
the stable `<install-root>/current` path. Durable data paths elsewhere under
the legacy home are preserved.

If legacy `pronounce.json` or `voice-map.json` files are present, the migrated
TTS bridge profile records their existing durable paths. Relocate them only as
a separate reviewed operation.

## Staged Upgrade

Use a unique bundle ID for every release.

```bash
BUNDLE="$(date +%Y%m%d-%H%M%S)-upgrade"
STAGE="$HOME/.local/share/llm-ops/stage/$BUNDLE"

scripts/llmops-admin deploy-plan --inventory <inventory.json> \
  --bundle-id "$BUNDLE" --dry-run
scripts/llmops-admin stage --inventory <inventory.json> \
  --bundle-id "$BUNDLE"
scripts/llmops-admin stage-validate --inventory <inventory.json> \
  --stage "$STAGE"
scripts/llmops-admin push --inventory <inventory.json> \
  --stage "$STAGE" --dry-run
scripts/llmops-admin apply --inventory <inventory.json> \
  --stage "$STAGE" --dry-run
scripts/llmops-admin push --inventory <inventory.json> --stage "$STAGE"
scripts/llmops-admin apply --inventory <inventory.json> --stage "$STAGE"
```

Remote apply:

- expands `~/` against the remote user's home
- installs an immutable release under `<install_root>/releases/<bundle>`
- verifies remote package, manifest, and host config SHA-256 checksums before
  creating the release
- preserves the resolved old release as `<install_root>/previous`
- moves a legacy directory-style `current` to
  `<install_root>/releases/legacy-current-*`
- switches `current` using macOS- and GNU-compatible symlink replacement
- scopes managed command links to `<install_root>/bin`
- restores both `current` and `previous` if post-switch verification fails

Apply refuses an existing release directory. Use a new bundle ID rather than
overwriting a release.

## Verification

```bash
ssh <target> '
  set -e
  root="$HOME/.local/llm-ops"
  readlink "$root/current"
  readlink "$root/previous" || true
  test -x "$root/current/scripts/llmops-admin"
  test -L "$root/bin/agentctl" || test -L "$root/bin/modelctl"
'
```

Validate each service separately before transferring ownership from its old
manual or launchd procedure. A runtime deployment alone does not change the
owner of a running service.

## Manual Rollback

Automatic rollback handles failures during apply. To roll back after a later
service validation failure:

```bash
ssh <target> '
  set -e
  root="$HOME/.local/llm-ops"
  old=$(readlink "$root/previous")
  test -n "$old" && test -e "$old"
  ln -s "$old" "$root/.current.rollback.$$"
  if ! mv -fh "$root/.current.rollback.$$" "$root/current" 2>/dev/null; then
    mv -fT "$root/.current.rollback.$$" "$root/current"
  fi
'
```

Restart only the service being rolled back, then re-run its status and health
checks. Do not remove the failed release or prior source checkout until the
incident is understood.

## Local Installer Recovery

`scripts/install-runtime.sh` stages and validates its payload before replacing
`current`. Upgrade backups are stored under
`~/.local/state/llm-ops/backups`. A failed upgrade restores the previous
runtime and state file. `scripts/uninstall-runtime.sh` can recover from a
missing manifest by removing only links that target the managed install.
