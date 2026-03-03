# Qwen3.5

**Created**: 2026-02-26
**Updated**: 2026-03-01

## Purpose

Run/control Qwen3.5 llama.cpp profile.

## Syntax

```bash
~/bin/Qwen3.5 [start|stop|restart|status|settings|verify|test]
```

## Examples

```bash
~/bin/Qwen3.5 settings
~/bin/Qwen3.5 verify
~/bin/Qwen3.5 test
QWEN35_PRESET=thinking-coding ~/bin/Qwen3.5 settings
QWEN35_TEMPLATE_MODE=new ~/bin/Qwen3.5 settings
```

## Notes

Supports sampling presets and template mode switching via env vars.
`verify` checks process + `/v1/models` response.
`test` sends a minimal completion request.
