# Manual End-to-End Release Test Checklist

**Created**: 2026-05-10
**Updated**: 2026-05-10

Back: [docs/INDEX.md](./INDEX.md)

Use this checklist before tagging a release. It covers the administrator
workstation, config migration, local staging, remote push/apply, local runtime
commands, remote runtime commands, model/agent/proxy/TTS smoke tests, and final
release gates.

Fill these in before starting:

```bash
export LLMOPS_TEST_TAG="production"
export LLMOPS_TEST_BUNDLE="$(date +%Y%m%d-%H%M%S)-release-test"
export LLMOPS_TEST_STAGE="$HOME/.local/share/llm-ops/stage/$LLMOPS_TEST_BUNDLE"
export LLMOPS_TEST_LLM_HOST="<inventory-llm-host-name>"
export LLMOPS_TEST_AGENT_HOST="<inventory-agent-host-name>"
export LLMOPS_TEST_MODEL="Qwen3.6"
export LLMOPS_TEST_MODEL_PATH="$HOME/LLM_Repository/<path-to-qwen3.6.gguf>"
```

## 1. Admin Workstation Baseline

- [ ] Confirm the repo is on the intended release branch.

```bash
git status --short --branch
git log -1 --oneline
```

- [ ] Confirm ignored local artifacts are either expected or cleaned.

```bash
git clean -Xdn
```

- [ ] Run the full local precheck.

```bash
scripts/precheck
```

Expected:

- `precheck: OK`
- shell syntax checks pass
- shellcheck passes
- Python tests pass

- [ ] Confirm runtime manifest is stable.

```bash
scripts/generate-manifest
git diff -- scripts/runtime-links.manifest
```

Expected:

- no unexpected `runtime-links.manifest` diff

- [ ] Confirm removed/obsolete command references are gone except stale-link cleanup entries.

```bash
rg -n "openclaw-start|node-hygiene|sanitized-daily-report|scripts/gateway|scripts/openclaw-stack|seckit export|secrets-doctor" \
  README.md docs scripts bin deploy .github
```

Expected:

- only intentional stale-link cleanup hits in `deploy-runtime-links.sh` / `verify-runtime-links.sh`

## 2. Config And Migration Checks

- [ ] Inspect platform-neutral path resolution.

```bash
scripts/llmops-admin config-doctor --dry-run
```

Expected:

- config under `~/.config/llm-ops`
- state/logs under `~/.local/state/llm-ops`
- cache under `~/.cache/llm-ops`

- [ ] Validate live inventory.

```bash
scripts/llmops-admin inventory-validate
scripts/llmops-admin inventory-validate --tag "$LLMOPS_TEST_TAG"
scripts/llmops-admin inventory-validate --host-name "$LLMOPS_TEST_LLM_HOST"
scripts/llmops-admin inventory-validate --host-name "$LLMOPS_TEST_AGENT_HOST"
```

Expected:

- all selected host records validate
- no YAML inventory is selected by default

- [ ] Dry-run legacy migration.

```bash
scripts/llmops-admin migrate-config --dry-run
```

Expected:

- reports sources and JSON destinations
- writes nothing
- legacy files are treated as migration input only

- [ ] Validate rendered config for target hosts.

```bash
scripts/llmops-admin config-settings --host-name "$LLMOPS_TEST_LLM_HOST" --model "$LLMOPS_TEST_MODEL"
scripts/llmops-admin config-settings --host-name "$LLMOPS_TEST_AGENT_HOST"
scripts/llmops-admin config-doctor --host-name "$LLMOPS_TEST_LLM_HOST" --model "$LLMOPS_TEST_MODEL"
scripts/llmops-admin config-doctor --host-name "$LLMOPS_TEST_AGENT_HOST"
```

Expected:

- required model/agent/proxy/TTS values are present
- source reporting is understandable
- no missing required fields for the selected host roles

## 3. GGUF Profile And Simulation Checks

- [ ] Inspect the primary Qwen3.6 GGUF without launching it.

```bash
scripts/llmops-admin model-inspect "$LLMOPS_TEST_MODEL_PATH" --no-cache
```

Expected:

- GGUF metadata is readable
- architecture/context metadata is reported when present

- [ ] Generate or preview the Qwen3.6 JSON profile.

```bash
scripts/llmops-admin model-add "$LLMOPS_TEST_MODEL" \
  --gguf "$LLMOPS_TEST_MODEL_PATH" \
  --cache-prompt \
  --cache-reuse 512 \
  --slot-save-path "$HOME/.local/state/llm-ops/slots" \
  --spec-type ngram-map \
  --spec-ngram-size-n 12 \
  --spec-ngram-size-m 48 \
  --perf \
  --fa \
  --no-cpu-moe \
  --no-host \
  --dry-run
```

Expected:

- profile renders as JSON
- llama-server performance flags are represented

- [ ] Render and simulate model, agent, and service profiles.

```bash
scripts/llmops-admin model-render-env "$LLMOPS_TEST_MODEL"
scripts/llmops-admin model-profile-doctor "$LLMOPS_TEST_MODEL"
scripts/llmops-admin model-simulate "$LLMOPS_TEST_MODEL" --action start
scripts/llmops-admin model-simulate "$LLMOPS_TEST_MODEL" --action status
scripts/llmops-admin agent-render-env openclaw
scripts/llmops-admin agent-simulate openclaw --action start
scripts/llmops-admin agent-simulate openclaw --action status
scripts/llmops-admin service-render-env model-proxy
scripts/llmops-admin service-render-env tts-bridge
```

Expected:

- commands do not start real models/agents
- rendered env includes expected paths, ports, and flags
- profile doctor reports no required-field gaps

## 4. Admin Deployment Dry Runs

- [ ] Preview host selection and target paths.

```bash
scripts/llmops-admin deploy-plan --tag "$LLMOPS_TEST_TAG" --bundle-id "$LLMOPS_TEST_BUNDLE" --dry-run
```

Expected:

- selected hosts are correct
- remote package/release/config paths are correct
- no SSH connection is attempted

- [ ] Preview SSH bootstrap.

```bash
scripts/llmops-admin bootstrap-host --tag "$LLMOPS_TEST_TAG" --dry-run
```

Expected:

- planned key path and remote readiness commands are correct
- no remote mutation occurs

- [ ] Preview staging.

```bash
scripts/llmops-admin stage --tag "$LLMOPS_TEST_TAG" --bundle-id "$LLMOPS_TEST_BUNDLE" --dry-run
```

Expected:

- planned stage path is `$LLMOPS_TEST_STAGE`
- selected host config outputs are listed
- no stage directory is created by dry-run

## 5. Build And Validate Local Stage

- [ ] Build the real stage bundle.

```bash
scripts/llmops-admin stage --tag "$LLMOPS_TEST_TAG" --bundle-id "$LLMOPS_TEST_BUNDLE"
```

Expected:

- `stage created: $LLMOPS_TEST_STAGE`
- `stage validation: OK`

- [ ] Validate and inspect the stage.

```bash
scripts/llmops-admin stage-validate --tag "$LLMOPS_TEST_TAG" --stage "$LLMOPS_TEST_STAGE"
scripts/llmops-admin deploy-report --tag "$LLMOPS_TEST_TAG" --stage "$LLMOPS_TEST_STAGE"
find "$LLMOPS_TEST_STAGE" -maxdepth 3 -type f | sort
```

Expected:

- package exists under `package/llm-ops-kit.tar.gz`
- each selected host has `config.env`, `config.json`, and `config-sources.json`
- `manifest.json` exists

- [ ] Confirm staged payload excludes docs/tests/secrets.

```bash
tar -tzf "$LLMOPS_TEST_STAGE/package/llm-ops-kit.tar.gz" | sort | tee /tmp/llmops-stage-files.txt
rg -n "scripts/tests|^docs/|\\.env$|\\.openclaw|secret|token|password" /tmp/llmops-stage-files.txt || true
```

Expected:

- no `scripts/tests`
- no `docs/`
- no `.env`
- no `.openclaw`
- no obvious secret-bearing paths

## 6. Remote Push And Apply

- [ ] Bootstrap SSH for selected hosts if not already done.

```bash
scripts/llmops-admin bootstrap-host --tag "$LLMOPS_TEST_TAG"
```

Expected:

- key exists or is created
- public key installs successfully
- each host gets a readiness marker

- [ ] Dry-run push.

```bash
scripts/llmops-admin push --tag "$LLMOPS_TEST_TAG" --stage "$LLMOPS_TEST_STAGE" --workers 4 --dry-run
```

Expected:

- each selected host reports planned package/config transfer
- no remote files are changed

- [ ] Push staged package and configs.

```bash
scripts/llmops-admin push --tag "$LLMOPS_TEST_TAG" --stage "$LLMOPS_TEST_STAGE" --workers 4
```

Expected:

- all selected hosts succeed
- failed hosts are isolated and clearly reported if any fail

- [ ] Dry-run remote apply.

```bash
scripts/llmops-admin apply --tag "$LLMOPS_TEST_TAG" --stage "$LLMOPS_TEST_STAGE" --workers 4 --dry-run
```

Expected:

- remote release/current/link actions are shown
- no remote files are changed

- [ ] Apply staged runtime.

```bash
scripts/llmops-admin apply --tag "$LLMOPS_TEST_TAG" --stage "$LLMOPS_TEST_STAGE" --workers 4
```

Expected:

- remote release directory is created
- `current` points at the new release
- runtime links are installed/refreshed
- role-specific verification runs

## 7. Remote Runtime Verification

For each target host, SSH in and run the relevant block.

### LLM or Hybrid Host

- [ ] Confirm installed runtime and links.

```bash
ssh "$LLMOPS_TEST_LLM_HOST" 'set -e; readlink ~/.llm-ops/current; ls -l ~/bin/modelctl ~/bin/Qwen3 ~/bin/BGEm3'
```

- [ ] Confirm settings render.

```bash
ssh "$LLMOPS_TEST_LLM_HOST" '~/bin/modelctl list && ~/bin/modelctl status && ~/bin/Qwen3 settings && ~/bin/BGEm3 settings'
```

- [ ] Start model services if this host is safe for live model testing.

```bash
ssh "$LLMOPS_TEST_LLM_HOST" '~/bin/Qwen3 start && ~/bin/BGEm3 start'
```

- [ ] Verify model endpoints.

```bash
ssh "$LLMOPS_TEST_LLM_HOST" '~/bin/Qwen3 verify && ~/bin/BGEm3 verify'
ssh "$LLMOPS_TEST_LLM_HOST" '~/bin/Qwen3 test && ~/bin/BGEm3 test'
```

- [ ] Confirm runtime logs are under state path.

```bash
ssh "$LLMOPS_TEST_LLM_HOST" 'ls -lah ~/.local/state/llm-ops/logs; tail -n 40 ~/.local/state/llm-ops/logs/llama-server-*.log 2>/dev/null || true'
```

### Agent or Hybrid Host

- [ ] Confirm agent command surface.

```bash
ssh "$LLMOPS_TEST_AGENT_HOST" '~/bin/agentctl current; ~/bin/agentctl status all'
```

- [ ] Start and stop direct-run agent wrapper if safe.

```bash
ssh "$LLMOPS_TEST_AGENT_HOST" '~/bin/agentctl start openclaw; sleep 3; ~/bin/agentctl status openclaw; ~/bin/agentctl stop openclaw'
```

- [ ] Validate launchd install/status/remove path if testing macOS launchd.

```bash
ssh "$LLMOPS_TEST_AGENT_HOST" '~/bin/agentctl launchd-install openclaw; ~/bin/agentctl launchd-status openclaw; ~/bin/agentctl launchd-remove openclaw'
```

- [ ] Validate Secrets Kit optional path only if Secrets Kit is installed and configured.

```bash
ssh "$LLMOPS_TEST_AGENT_HOST" 'LLMOPS_USE_SECKIT=1 ~/bin/agentctl launchd-run openclaw'
```

Expected:

- `seckit run` wraps OpenClaw only when explicitly enabled
- missing `seckit` fails clearly
- no wrapper-level secret export is used

## 8. Local Runtime Install/Repair Flow

Run on a disposable local account or safe test machine if possible.

- [ ] Install runtime payload from checkout.

```bash
scripts/install-runtime.sh --source "$PWD" --no-links
```

- [ ] Install runtime links.

```bash
scripts/install-runtime.sh --source "$PWD"
```

- [ ] Confirm local runtime state file is in XDG state.

```bash
test -f ~/.local/state/llm-ops/runtime-state.env
cat ~/.local/state/llm-ops/runtime-state.env
```

- [ ] Confirm local commands resolve.

```bash
~/bin/modelctl status
~/bin/agentctl status all
~/bin/model-proxy status || true
~/bin/tts-bridge status || true
~/bin/runtime-maintenance status
```

- [ ] Verify stale old links are removed or flagged.

```bash
scripts/deploy-runtime-links.sh --replace-managed-links
scripts/verify-runtime-links.sh
```

- [ ] Test uninstall keep-files mode on a disposable install only.

```bash
scripts/uninstall-runtime.sh --keep-files
```

Expected:

- managed links are removed
- installed payload remains

## 9. Proxy And TTS Runtime Checks

- [ ] Start or restart model proxy against a known model endpoint.

```bash
~/bin/model-proxy restart --listen-port 11440 --upstream http://<model-host>:11434
~/bin/model-proxy status
```

- [ ] Render one request without forwarding.

```bash
printf '{"model":"test","messages":[{"role":"user","content":"hello"}]}\n' \
  | ~/bin/model-proxy render -i -
```

- [ ] Start TTS bridge against a known MLX TTS endpoint.

```bash
TTS_BRIDGE_UPSTREAM_BASE="http://<tts-host>:11439/v1" ~/bin/tts-bridge restart
~/bin/tts-bridge status
```

- [ ] Send one TTS bridge request.

```bash
curl -sS "http://127.0.0.1:${TTS_BRIDGE_PORT:-11440}/v1/audio/speech" \
  -H 'Content-Type: application/json' \
  -d '{"model":"test","input":"Release validation test.","voice":"serena","response_format":"wav"}' \
  --output /tmp/llmops-tts-test.wav
ls -lh /tmp/llmops-tts-test.wav
```

Expected:

- proxy status shows listener and upstream
- TTS bridge health is reachable
- output WAV file is non-empty when upstream TTS is available

## 10. Final Release Gates

- [ ] Stop any test services you started.

```bash
~/bin/model-proxy stop || true
~/bin/tts-bridge stop || true
~/bin/agentctl stop all || true
~/bin/Qwen3 stop || true
~/bin/BGEm3 stop || true
```

- [ ] Rerun final local checks.

```bash
scripts/precheck
git diff --check
git status --short --branch
git clean -Xdn
```

- [ ] Review release checklist.

```bash
sed -n '1,160p' docs/RELEASE_AUDIT_CHECKLIST.md
```

- [ ] Confirm release notes/changelog are ready.

```bash
sed -n '1,120p' CHANGELOG.md
```

- [ ] Tag only after all relevant boxes above are complete.

```bash
git tag -a <version> -m "<version>"
git status --short --branch
```
