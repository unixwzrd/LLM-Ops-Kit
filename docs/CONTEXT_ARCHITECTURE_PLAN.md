# Context Architecture Plan

**Created**: 2026-02-24
**Updated**: 2026-02-26

- [Context Architecture Plan](#context-architecture-plan)
  - [Goal](#goal)
  - [Scope](#scope)
  - [Canonical Routing Model](#canonical-routing-model)
  - [Bootstrap Model](#bootstrap-model)
  - [Context File Layout (Current)](#context-file-layout-current)
  - [Privacy and Access Model](#privacy-and-access-model)
  - [Prune-Time Refresh Model](#prune-time-refresh-model)
  - [Migration Notes](#migration-notes)
  - [Validation Checklist](#validation-checklist)

## Goal

Provide deterministic, channel-keyed context bootstrapping with strict private-scope isolation while keeping prompt size stable as contexts grow.

## Scope

- `OpenClaw-workspace`: canonical context routing, context metadata, context constraints, private knowledge files.
- `LLM-Ops-Kit`: operational/runtime scripts and backend operator documentation.

## Canonical Routing Model

Route key format:

- `channel:mode:target`

Active keys:

- `telegram:group:-1003713298137` -> private context
- `telegram:direct:*` -> primary control context
- `webui:default` -> primary control context
- `tui:default` -> primary control context

Priority order:

1. Exact key
2. Wildcard key
3. Channel default
4. Privacy-safe fallback

## Bootstrap Model

Stage A (always):

1. `SOUL.md`
2. `USER.md`
3. `CONTEXTS.md`

Stage B (matched context):

1. Read matched `CONTEXT_INFO.md`
2. Read `constraints_file` (`CONTEXT_CONSTRAINTS.md`)
3. Continue with startup/read guidance from `CONTEXT_INFO.md`

## Context File Layout (Current)

- `OpenClaw-workspace/CONTEXTS.md` (single source router/index)
- `OpenClaw-workspace/contexts/primary/telegram_direct/CONTEXT_INFO.md`
- `OpenClaw-workspace/contexts/primary/telegram_direct/CONTEXT_CONSTRAINTS.md`
- `OpenClaw-workspace/contexts/primary/webui/CONTEXT_INFO.md`
- `OpenClaw-workspace/contexts/primary/webui/CONTEXT_CONSTRAINTS.md`
- `OpenClaw-workspace/contexts/primary/tui/CONTEXT_INFO.md`
- `OpenClaw-workspace/contexts/primary/tui/CONTEXT_CONSTRAINTS.md`
- `OpenClaw-workspace/contexts/private/telegram_group_-1003713298137/CONTEXT_INFO.md`
- `OpenClaw-workspace/contexts/private/telegram_group_-1003713298137/CONTEXT_CONSTRAINTS.md`
- `OpenClaw-workspace/contexts/private/knowledge/*.md`
- `OpenClaw-workspace/contexts/docs/*` (operator docs/templates; not required for startup)

## Privacy and Access Model

- Private route loads `contexts/private/knowledge/*` and scoped policy files.
- Non-private contexts block `contexts/private/knowledge/*`.
- Security/access/tool constraints live in each context's `CONTEXT_CONSTRAINTS.md`.

## Prune-Time Refresh Model

Recommended refresh boundary is prune:

1. Re-read active context `CONTEXT_INFO.md`
2. Re-read active `CONTEXT_CONSTRAINTS.md`
3. Re-read minimal policy anchor files listed in `refresh_files`

## Migration Notes

Private memory canonicalization remains:

- `memory/identity/intimate_rules.md` -> `contexts/private/knowledge/intimate_rules.md`
- `memory/identity/michael.md` -> `contexts/private/knowledge/michael.md`
- `memory/identity/pre_consent_agreement_Mia.md` -> `contexts/private/knowledge/pre_consent_agreement_Mia.md`
- `memory/identity/pre_consent_agreement_Michael.md` -> `contexts/private/knowledge/pre_consent_agreement_Michael.md`
- `memory/personas/mia_and michael_backstory.md` -> `contexts/private/knowledge/mia_and_michael_backstory.md`

## Validation Checklist

1. Route key resolves to exactly one context.
2. Private route loads private knowledge; non-private routes do not.
3. `CONTEXTS.md` remains short (routing/index only).
4. Context behavior lives in `CONTEXT_INFO.md` + `CONTEXT_CONSTRAINTS.md`.
5. Prune refresh reload set stays minimal.
