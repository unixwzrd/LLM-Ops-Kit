# BGEm3

**Created**: 2026-03-16
**Updated**: 2026-03-16

## Purpose

Run/control the `bge-m3` embedding model profile for memory indexing and retrieval.

## Syntax

```bash
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

`BGEm3` is the preferred embedding launcher for the current runtime.
If indexing fails with token/context errors, check `settings` and the OpenClaw memory chunking config.
`verify` checks process status and `/v1/models`.
`test` sends a minimal embedding request.
