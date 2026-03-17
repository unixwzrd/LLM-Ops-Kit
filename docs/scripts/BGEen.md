# BGEen (Legacy Alias)

**Created**: 2026-02-26
**Updated**: 2026-03-16

## Purpose

Legacy alias documentation for the old embedding launcher name.
Prefer `BGEm3` for the current `bge-m3` embedding profile.

## Syntax

```bash
~/bin/BGEen [start|stop|restart|status|settings|verify|test]
~/bin/BGEm3 [start|stop|restart|status|settings|verify|test]
```

## Examples

```bash
~/bin/BGEm3 settings
~/bin/BGEm3 verify
~/bin/BGEm3 test
~/bin/BGEm3 restart
```

## Notes

Use [`BGEm3.md`](./BGEm3.md) as the primary operator guide.
If indexing fails with token/context errors, check `settings` and the OpenClaw chunking config.
`verify` checks process and `/v1/models`.
`test` sends a minimal embedding request.
