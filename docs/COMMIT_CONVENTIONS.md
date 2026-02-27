# Local Commit Conventions

**Created**: 2026-02-20
**Updated**: 2026-02-26

Use short prefix tags for local history readability:

- `hygiene:` ignore rules, tracking policy, scrub actions
- `runtime:` runtime behavior/config wiring updates
- `policy:` docs, privacy/security policy decisions
- `dr:` backup/restore/disaster-recovery planning
- `workspace:` workspace behavior/memory structure changes

Examples:
- `hygiene: ignore runtime session/auth churn files`
- `policy: phase-1 local-only repo boundaries`
- `dr: add sanitized backup export contract`
