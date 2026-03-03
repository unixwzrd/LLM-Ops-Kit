# BGEen

**Created**: 2026-02-26
**Updated**: 2026-03-01

## Purpose

Run/control embedding model profile for memory indexing/retrieval.

## Syntax

```bash
~/bin/BGEen [start|stop|restart|status|settings|verify|test]
```

## Examples

```bash
~/bin/BGEen settings
~/bin/BGEen verify
~/bin/BGEen test
~/bin/BGEen restart
```

## Notes

If indexing fails with token/context errors, check `settings` + OpenClaw chunking config.
`verify` checks process + `/v1/models` response.
`test` sends a minimal embedding request.
