# Release Audit Checklist

**Created**: 2026-04-17
**Updated**: 2026-04-17

Use this checklist after end-to-end testing and before the final release commit/tag.

## Runtime payload audit

- confirm `stage/` is ignored and not tracked
- confirm staged payload contains only runtime files
- confirm staged payload excludes tests, docs, `.env`, `.openclaw`, secrets, and host-local state
- confirm managed commands in `runtime-links.manifest` match the intended release surface

## Transitional code cleanup

- remove any temporary test helpers that were added only for development
- remove deprecated script paths or compatibility shims that are no longer needed
- remove stale repo-sync-first references from docs if staged deploy replaced them
- remove unused manifest entries or dead managed command names

## Documentation check

- README quick start matches the admin workstation deployment flow
- deployment overview matches the shipped `llmops-admin` command names
- script mini-guide exists for `llmops-admin`
- config guide documents inventory-based deployment config and runtime venv behavior
- docs explicitly state that `.openclaw` is out of scope

## Release candidate check

- runtime installer works from a staged payload root
- push workflow works for localhost-over-SSH and at least one remote host
- optional runtime venv creation works
- optional Secrets-Kit install path works when enabled
- repo tree is clean apart from intentional release changes
- version/tag will represent the cleaned staged-deploy workflow, not an intermediate migration snapshot
