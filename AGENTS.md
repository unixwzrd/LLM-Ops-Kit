# AGENTS.md - LLM-Ops-Kit

## Scope and Boundaries

- Work inside this repository only.
- Do not modify `.git/` internals.
- Do not modify `.gitignore` or repo-wide packaging/build configs unless explicitly asked.
- Treat `tmp/` as scratch space: read/write allowed, no assumptions that files there are canonical.
- Never touch model weight directories outside this repo unless explicitly requested.

## Change Discipline

- Make small, incremental changes.
- Prefer `git mv` for tracked file renames/moves.
- Avoid patch-and-delete move patterns unless explicitly requested.
- Do not add new dependencies or frameworks without explicit approval.
- Prefer simplification over new abstraction layers.

## Runtime and Safety

- Do not run destructive commands without explicit confirmation.
- Do not change git remotes/branches/tags without explicit confirmation.
- Keep scripts idempotent where possible.
- For operator scripts, favor clear output and explicit failure messages.

## Scripting Standards (Bash)

- Use `#!/usr/bin/env bash` and `set -euo pipefail` for non-trivial scripts.
- Keep CLI behavior explicit (`--help`, clear options, sane defaults).
- Avoid embedded polyglot blocks when a shell-native approach is practical.
- Keep naming short, stable, and project-agnostic where possible.
- Prefer one canonical command per function; keep compatibility aliases minimal.

## Python Standards (for helper tools)

- Use Python 3.9+ compatible syntax.
- Use type hints for all public functions and important internal helpers.
- Prefer concrete types over `Any`; use `typing` intentionally.
- Prefer keyword arguments over positional arguments for non-trivial calls.
- Use sensible default values in function signatures where appropriate.
- Avoid inline imports unless justified.
- Use explicit UTF-8 encoding for file IO.
- Prefer clear exceptions over silent fallback behavior.
- Use Google-style docstrings for modules, classes, and functions.
- When refactoring code that lacks kwargs/type hints/docstrings, fix those during the refactor (do not defer).
- Prefer `pathlib.Path` over ad-hoc string path handling.
- Keep configuration mutation centralized; avoid changing the same config variable in multiple places.
- Look for common routines and extract reusable helpers instead of duplicating logic.
- Keep modules focused and bounded; refactor before modules become excessively large.
- Treat high LOC as a refactor signal; split by responsibility when complexity grows.

## Markdown and Docs Standards

- Every major doc should include:
  - `# Title`
  - `**Created**: YYYY-MM-DD`
  - `**Updated**: YYYY-MM-DD`
- Use fenced code blocks with language tags.
- Use relative Markdown links for repo-local references.
- Keep docs navigable; split large docs by topic when needed.
- Update docs when script behavior or interfaces change.

## Validation Expectations

After a logical batch, run relevant checks:

- `bash -n` for changed shell scripts.
- Script-level smoke checks (`--help`, `status`, `settings`) where applicable.
- Link/manifest checks when touching runtime links:
  - `scripts/generate-manifest`
  - `scripts/deploy-runtime-links.sh`
  - `scripts/verify-runtime-links.sh`

When a change worsens behavior, revert that batch and rework with a smaller diff.
