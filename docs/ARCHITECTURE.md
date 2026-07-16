# Architecture

Back: [Documentation Index](./INDEX.md)

## Scope

LLM-Ops-Kit is a local-first macOS control layer, not a container scheduler. It coordinates existing model engines, agents, proxies, bridges, tunnels, dashboards, and launchd services without taking ownership of model weights, application state, logs, or secrets.

## Control Model

The administrator machine owns desired state. Canonical JSON configuration is loaded into a `Topology`, validated, and converted to ordered `Operation` objects. The same planner and executor modules are used by the CLI, tests, and future interfaces.

```text
JSON configuration -> topology validation -> dependency planner -> typed component driver -> local or SSH transport
```

Stacks are dependency graphs. They provide coordinated start, stop, restart, and status operations but do not hide or prevent component-level control.

## Lifecycle Semantics

- Component start includes missing upstream dependencies unless `--no-deps` is explicitly used.
- Component stop affects only the target and refuses when active dependents exist unless `--force` or `--cascade` is supplied.
- Component restart affects only the target by default.
- Cascade stop and restart operate over the active dependent closure in dependency-safe order.
- Stack start is dependency first; stack stop is reverse dependency order.
- Operations are idempotent.
- A failed start stops only components started by that invocation.
- Read-only status and log operations do not acquire the lifecycle mutation lock.

## Drivers

Typed drivers construct lifecycle commands for `modelctl`, managed processes, launchd services, model-proxy, tts-bridge, SSH tunnels, and agents. The advanced command driver is disabled by default and accepts argv arrays rather than shell strings.

Transport is either local execution or noninteractive SSH. SSH transport has bounded retry for deployment push, apply, drift, and rollback operations.

## Immutable Releases

An authoritative deployment produces a checksummed package and one role-filtered configuration archive per host. Each archive contains global settings, a host-local inventory, host-local stack graphs, required profiles, and a resolution manifest. Cross-host dependencies are recorded as external dependencies rather than causing unrelated profiles to be copied.

Code and configuration are extracted into the same release directory. The `current` symlink selects the active release and `previous` retains the rollback target. Runtime links point through `current`.

## Drift

Drift compares the desired deployment manifest with the active remote bundle, manifest, and resolved configuration hashes. Remote changes are reported and never merged into administrator state.

## Agent Independence

Agent components use generic process, launchd, or argv action profiles. Hermes and OpenClaw are compatibility adapters for one release. There is no default agent target.

## Future UI Boundary

Any web UI or TUI must call the shared control library or versioned JSON API. It must not contain a second planner or executor.

The intended web shape is a separate loopback-only control process with static HTML, CSS, vanilla JavaScript, a small optional FastAPI backend, REST action endpoints, and SSE lifecycle events. It must remain available while all managed components are stopped and must not import model engines.
