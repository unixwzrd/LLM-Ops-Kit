# Adapters

**Created**: 2026-07-20
**Updated**: 2026-07-20

Back: [Documentation index](./INDEX.md)

Adapters connect the shared planner and executor to native subsystem lifecycle behavior. Inspect the registry with:

```bash
llmops adapter list
llmops adapter show launchd
llmops adapter doctor
```

The beta ships launchd, standalone process and generic agent, SSH tunnel, llama.cpp/modelctl, model-proxy, and tts-bridge adapters.

Python distributions register adapters through the `llmops.adapters` entry-point group. A registration callable returns one or more `AdapterManifest` values containing a stable ID, semantic version, adapter API version, drivers, capabilities, platforms, executables, transports, and schema metadata.

Adding an adapter must not require changes to the planner, executor, CLI parser, or Textual console. The conformance tests reject duplicate IDs, incompatible API majors, drivers claimed by multiple adapters, and configured drivers with no adapter.

Third-party catalog installation and signature policy are post-beta work. The beta discovers only already installed Python entry points and never installs an adapter implicitly.
