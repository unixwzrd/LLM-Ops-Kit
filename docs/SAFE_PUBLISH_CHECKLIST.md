# Safe Publish Checklist (Public)

**Created**: 2026-02-28  
**Updated**: 2026-03-01

Use this before pushing to a public remote.

- [x] No secrets/tokens/private keys in tracked files.
- [x] No private runtime/session logs in repo.
- [x] Public docs do not depend on internal-only documents.
- [x] Machine-specific paths/IPs are either placeholders or explicitly labeled local examples.
- [x] `.env.example` is present and contains no secrets.
- [x] Script syntax checks pass (`bash -n`).
- [x] Runtime command docs match actual CLI behavior.
- [x] `docs/CHANGELOG.md` includes the release-ready changes.

See local internal operator checklist for the detailed gate (not part of public release content).
