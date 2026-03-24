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
USE_CUSTOM_TEMPLATE=1 CHAT_TEMPLATE=/absolute/path/to/template.jinja ~/bin/Qwen3.5 settings
```

## Notes

This profile does not assume a custom template by default.

Operator overrides belong in `~/.llm-ops/config.env`.
Enable a custom template explicitly there, for example:

```bash
export USE_CUSTOM_TEMPLATE=1
export CHAT_TEMPLATE=/absolute/path/to/template.jinja
export TEMP=0.9
export TOP_P=0.95
export TOP_K=20
export MIN_P=0.0
export PRESENCE_PENALTY=1.5
export REPEAT_PENALTY=1.0
```

Set both `USE_CUSTOM_TEMPLATE=1` and `CHAT_TEMPLATE=...` before starting the model.

`verify` checks process + `/v1/models` response.
`test` sends a minimal completion request.
