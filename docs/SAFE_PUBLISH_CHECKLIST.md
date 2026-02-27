# Safe Publish Checklist

**Created**: 2026-02-26
**Updated**: 2026-02-26


Before pushing to public GitHub:

- [ ] No secrets/tokens/API keys in tracked files.
- [ ] No private chat/session logs included.
- [ ] No machine-specific sensitive paths or usernames in docs unless intentional.
- [ ] `.openclaw` runtime state is not included.
- [ ] `docs/internal/` content excluded if meant to stay private.
- [ ] README links/images render correctly on GitHub.
- [ ] Changelog entry added for significant changes.
- [ ] `bash -n` passes for modified shell scripts.
- [ ] `verify-runtime-links.sh` passes on target host.
