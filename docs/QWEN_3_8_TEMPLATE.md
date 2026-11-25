# Qwen 3.8 Tool and Media History Template

**Created**: 2026-11-24
**Updated**: 2026-11-24

The optimized template is [Qwen-3_8-media-history-template.jinja](../scripts/templates/Qwen-3_8-media-history-template.jinja). Qwen 3.8 is its documented target; Qwen 3.5 compatibility has not been established. The older Qwen 3.5-named file remains unchanged for existing configurations.

It omits tool-call-only assistant messages and tool results from closed turns before the latest actual user message. Assistant prose is retained even when its old tool calls are omitted. The current turn retains its tool calls, results and compatibility tool-response wrappers. Media-history rules retain current structured vision while suppressing stale textual tool media as covered by synthetic regressions.

This is a model-specific chat template, distinct from the [readable exchange report](PROXY_TAP_RUNBOOK.md). Selecting it as the proxy's `template.path` renders a diagnostic copy and does not prune forwarded JSON. To affect inference, select the template in the model server's supported configuration. Proxy SIGHUP does not reload that server.

Keep a rollback copy and qualify synthetic closed-turn/active-turn tool chains, image inputs and current results before changing a serving template. Verify the actual model route during an idle maintenance window. Do not infer compatibility from a filename alone.
