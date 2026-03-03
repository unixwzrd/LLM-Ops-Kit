# Qwen3

**Created**: 2026-02-26
**Updated**: 2026-03-01

## Purpose

Run/control Qwen3 llama.cpp profile.

## Syntax

```bash
~/bin/Qwen3 [start|stop|restart|status|settings|verify|test]
```

## Examples

```bash
~/bin/Qwen3 settings
~/bin/Qwen3 verify
~/bin/Qwen3 test
~/bin/Qwen3 restart
```

## Notes

`settings` prints effective runtime parameters and template path.
`verify` checks process + `/v1/models` response.
`test` sends a minimal completion request.
