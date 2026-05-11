# Qwen3

**Created**: 2026-02-26
**Updated**: 2026-03-01

## Purpose

Run/control Qwen3 llama.cpp profile.

## Syntax

```bash
llmops Qwen3 [start|stop|restart|status|settings|verify|test]
```

## Examples

```bash
llmops Qwen3 settings
llmops Qwen3 verify
llmops Qwen3 test
llmops Qwen3 restart
USE_CUSTOM_TEMPLATE=1 CHAT_TEMPLATE=/absolute/path/to/template.jinja llmops Qwen3 settings
```

## Notes

Operator overrides belong in `~/.config/llm-ops/config.env`.
Enable a custom template explicitly there, for example:

```bash
export USE_CUSTOM_TEMPLATE=1
export CHAT_TEMPLATE=/absolute/path/to/template.jinja
export TEMP=1.0
export TOP_P=0.95
export TOP_K=20
export MIN_P=0.0
export PRESENCE_PENALTY=1.5
export REPEAT_PENALTY=1.0
```

`settings` prints effective runtime parameters and template path.
`verify` checks process + `/v1/models` response.
`test` sends a minimal completion request.
