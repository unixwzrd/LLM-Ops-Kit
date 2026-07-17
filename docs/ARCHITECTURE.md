# Architecture

**Created**: 2026-07-16
**Updated**: 2026-07-16

Back: [Documentation index](./INDEX.md)

LLM-Ops-Kit is a local-first macOS control layer, not a container scheduler. The administrator configuration is converted into a validated topology, dependency plan, typed driver command, and local or SSH operation.

```text
canonical JSON -> topology validation -> dependency planner -> typed driver -> local or SSH transport
```

Component start satisfies missing upstream dependencies. Component restart affects only the target by default. Component stop refuses active dependents unless `--force` or `--cascade` is used. Stack operations compose the same component planner in dependency order.

The executor is idempotent. A failed start stops only components started by that invocation and leaves pre-existing services untouched. Mutations use a lifecycle lock; status and logs are read-only.

Model, proxy, and TTS wrappers use `llmops_profiles.py` to resolve canonical JSON. Generic agents use normal argv action profiles through the typed agent driver. Proof-of-concept shell profiles and agent-specific adapters are not runtime inputs.

Deployment creates one package and one host-filtered configuration snapshot per selected host. Code and configuration are applied to the same immutable release. Drift compares active bundle, manifest, and configuration hashes. Remote changes are reported and never merged.

Future UI integrations must consume the same control modules or stable JSON output. They must not implement a second planner or initialize model engines.
