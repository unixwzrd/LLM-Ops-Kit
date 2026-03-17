# openclaw-stack

**Created**: 2026-02-26
**Updated**: 2026-02-26

## Purpose

Control grouped service lifecycle (gateway/model-proxy/models).

## Syntax

```bash
~/bin/openclaw-stack [start|stop|restart|status] [all|gateway|llm|embedding|model-proxy|models]
```

## Examples

```bash
~/bin/openclaw-stack start all
~/bin/openclaw-stack status
~/bin/openclaw-stack restart models
```

## Notes

`models` target controls `Qwen3` + `BGEm3` in parallel.
