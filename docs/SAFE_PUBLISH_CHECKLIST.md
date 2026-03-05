# Safe Publish Checklist

**Created**: 2026-03-03  
**Updated**: 2026-03-03

Use this before pushing to a public remote.

- [ ] No secrets/tokens/private keys in tracked files.
- [ ] No private runtime/session logs in repo.
- [ ] Public docs do not depend on internal-only documents.
- [ ] Machine-specific paths/IPs are placeholders or clearly marked local examples.
- [ ] `.env.example` is present and contains no secrets.
- [ ] Script syntax checks pass (`bash -n`).
- [ ] Python syntax checks pass (`python3 -m py_compile`).
- [ ] Runtime command docs match actual CLI behavior.
- [ ] `docs/CHANGELOG.md` includes release-ready changes.
