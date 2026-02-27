# Contract: `scripts/backup/export-sanitized.sh` (Design Only)

**Created**: 2026-02-20
**Updated**: 2026-02-26

## Status

Design contract only (not implemented in phase 1).

## Goal

Produce a timestamped sanitized recovery bundle for migration/DR planning without exporting runtime/session/auth secrets.

## Inputs

- `--repo-root <path>` (repeatable): repository roots to process
- `--out-dir <path>`: output directory for bundle
- `--profile <name>`: sanitization profile (default: `phase1-local`)

## Output

- `sanitized-export-YYYYMMDD-HHMMSS.tar.gz`
- companion manifest:
  - included paths
  - excluded paths
  - git commit refs (if available)
  - generation timestamp

## Exclude by Default

- runtime session transcripts and indexes
- auth/runtime device state
- credential/token files
- offsets, caches, sqlite runtime DBs
- `.bak`/temp churn artifacts

## Include by Default

- stable config files with env placeholders
- docs/policies/TODOs
- scripts needed for rebuild workflow
- restore instructions

## Non-Goals (Phase 1)

- full state replay of active conversations
- shipping raw logs or unredacted payloads
