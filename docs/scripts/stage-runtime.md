# stage-runtime

**Created**: 2026-04-17
**Updated**: 2026-04-17

Build a staged virtual target filesystem from the local git checkout.

```bash
scripts/stage-runtime [--config-name <name>] [--stage-dir <path>] [--force] [-v]
```

Default stage output:

- `./stage/<config-name>/`

The staged tree mirrors the real destination path layout below `stage/<config-name>/`.
Example: a target install path of `/Users/miafour/.llm-ops` stages as `stage/<config-name>/Users/miafour/.llm-ops`.

This is an internal helper command. Operators should normally use `./build-stage`.
See [DEPLOYMENT_SYNC_RUNBOOK](../DEPLOYMENT_SYNC_RUNBOOK.md) for the full deploy flow.
