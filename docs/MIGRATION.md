# Migration from the Proof of Concept

**Created**: 2026-07-16
**Updated**: 2026-07-21

Back: [Documentation index](./INDEX.md)

Migration is a one-way conversion into canonical JSON. Runtime commands never read legacy shell configuration after migration.

## Back Up

Back up the legacy configuration and current runtime before migration. Keep the backup and previous immutable runtime until operational acceptance is complete.

## Preview

```bash
llmops migrate-config --legacy-home ~/.llm-ops --dry-run --json
```

The preview reports each source and destination, classified profile type, secret-reference conversions, warnings, and skipped unknown inputs. Preview does not write files.

## Classification

| Legacy input | Canonical destination | Behavior |
|---|---|---|
| Files containing `MODEL` or `MODEL_TYPE` | `models/<name>.json` | Preserves runtime values in `environment` and assigns `llm`, `embedding`, or `tts` type. |
| Model proxy variables | `services/model-proxy.json` | Creates an explicit service environment. |
| TTS bridge variables | `services/tts-bridge.json` | Creates an explicit service environment. |
| `config/agents/*.env` | `agents/<name>.json` | Imports environment values but leaves lifecycle actions empty and disabled for review. |
| JSON or supported simple YAML inventory | `inventory.json` | Converts to canonical schema version 2. |
| Unknown input | None | Reports the file and refuses a normal migration. |

Literal fields whose names indicate keys, tokens, passwords, credentials, or secrets become `env:<VARIABLE>` references. The literal values are not written.

## Apply

```bash
llmops migrate-config --legacy-home ~/.llm-ops
```

If the preview contains intentionally unsupported files, review them and use `--allow-partial` to apply only classified inputs. Existing destinations are never overwritten unless `--force` is supplied after backup and review.

## Validate

```bash
llmops doctor
llmops doctor --probe
llmops config show --json
llmops plan --action start --json
```

Add reviewed lifecycle actions to migrated agents, create or update disabled stack components, and resolve every warning before enabling anything.

## Rollback

Migration does not modify the legacy source. To abandon migrated configuration, move the new configuration root aside and restore the backup. Runtime rollback is independent and uses `llmops rollback`.

## Canonical Schema Migration

Existing operator-v1 JSON uses a separate one-time migration:

```bash
llmops migrate-schema --authority-host model-host --plan
llmops migrate-schema --authority-host model-host --apply --yes
```

`--authority-host` must name a `trusted_control` inventory host. Setting it during migration avoids relying on inventory order and makes the desired-state authority explicit before reconciliation.

The plan assigns reviewed built-in template IDs from existing drivers, preserves profile values, adds explicit restart policy defaults, and reports ambiguous profiles for review. Application is refused while findings remain. After migration, normal runtime commands accept schema version 2 only; version 1 documents remain test fixtures rather than compatibility inputs.
