# TTS Remote-Cloning Canary Evidence

**Created**: 2026-08-21
**Updated**: 2026-08-21

## Gate status

The isolated Base and CustomVoice functional canary passed. At the operator's direction, the retained Conda production engine and Hermes-host bridge were stopped and the validated patched runtime was promoted. Production now uses patched MLX-Audio `0.5.0+unixwzrd.1` on the inference host and the co-located LLM-Ops bridge; the isolated canary listeners are stopped. Hermes uses the bridge's advertised LAN endpoint. A real Hermes `text_to_speech_tool` request through the production bridge returned a valid 24 kHz mono WAV using the accepted registered pair.

## Environment

- Host: Apple Silicon inference host with 96 GB unified memory.
- Engine: immutable UV environment under `~/.local/llm-ops/products/mlx-audio/0.5.0+unixwzrd.1`.
- Bridge: LLM-Ops application Python with canary assets under `~/.local/llm-ops/products/tts-canary/0.5.0+unixwzrd.1`.
- Models: the initial functional pass used the existing provenance-unknown Qwen checkpoints. The comparison pass used new revision-qualified directories with completion records; the old directories were not modified.
- Registry: two persistent reviewed pairs with neutral local aliases; discovery returned two records without transcript content, audio, or paths. The aliases intentionally omit the upstream synthesized-voice labels.

## Objective results

| Path | Model/mode | Output duration | Total request time | RTF | Result |
|---|---|---:|---:|---:|---|
| Direct registered ID, cold pair cache | Qwen Base clone | 2.88 s | 27.695 s | 9.62 | Valid 24 kHz mono WAV |
| Bridge alias, warm pair cache | Qwen Base clone | 4.80 s | 2.441 s | 0.51 | Valid 24 kHz mono WAV |
| Inline audio plus exact transcript | Qwen Base clone | 2.00 s | 1.350 s | 0.67 | Valid 24 kHz mono WAV |
| Long non-streaming paragraph | Qwen Base clone | 32.48 s | 12.153 s | 0.37 | Valid 24 kHz mono WAV; engine remained healthy |
| Short streaming recovery | Qwen Base clone | 2.00 s | 1.770 s | 0.89 | Valid 24 kHz mono WAV |
| Registered ID | Patched CustomVoice ICL clone | 2.64 s | 1.468 s | 0.56 | Valid 24 kHz mono WAV |
| Named speaker plus instruction | CustomVoice named-speaker compatibility | 2.64 s | 4.648 s | 1.76 | Valid 24 kHz mono WAV |
| Post-error bridge request | Qwen Base clone | 3.36 s | 1.622 s | 0.48 | Valid WAV after malformed requests |

The engine log recorded one SHA-256 pair cache miss followed by a hit without audio or transcript content. The bridge log retained only redacted target/reference fields and the registered reference ID. A token scan of both logs was negative. Observed resident memory after loading Base was approximately 2.1 GiB; a reliable unified-memory peak capture remains part of the multi-model comparison.

Malformed text-only, `voice` plus reference, unauthorized deletion, and unsupported Qwen clone instruction requests returned 422, 422, 401, and 422 respectively. A valid request immediately afterward succeeded.

## Revision-pinned model comparison

All seven requested production-evaluation checkpoints downloaded at the manifest revisions. Higgs Audio was not downloaded. Each candidate ran in a fresh engine process so model state and encoded caches could not leak between results.

| Candidate | Revision prefix | Output duration | Total request time | RTF | Result |
|---|---|---:|---:|---:|---|
| Qwen3 0.6B Base 8-bit | `50f45ef0047c` | 4.08 s | 2.802 s | 0.69 | Valid WAV |
| Qwen3 0.6B CustomVoice 8-bit, patched ICL | `049ef77fe881` | 4.64 s | 2.810 s | 0.61 | Valid WAV |
| Qwen3 1.7B Base 8-bit | `e7dd05856522` | 4.16 s | 2.992 s | 0.72 | Valid WAV |
| Chatterbox Multilingual v3 | `03565773edd7` | 4.16 s | 5.943 s | 1.43 | Valid WAV after language-boundary correction |
| Audio8/ArkTTS 0.6B BF16 | `e59b26ec0ad7` | 4.37 s | 4.434 s | 1.02 | Valid WAV |
| ZONOS2 | `3ad1bd8b27d4` | 12.77 s | 32.010 s | 2.51 | Produced a WAV, but failed human review as broken; rejected |
| Confucius4 int8 | `3cbe563153df` | — | 17.751 s to failure | — | Failed twice with a Metal GPU timeout and zero audio |

The generic MLX-Audio request schema had defaulted `lang_code` to Kokoro's `a`, which Chatterbox rejects. The patched server now leaves the code unset so each model uses its native default; the bridge maps alias `language` to the upstream `lang_code`. A live bridge alias request confirmed `reference_id`, `lang_code: en`, and `intensity` translated to `exaggeration: 0.65`, producing a valid WAV without logging text or paths.

Confucius4 produced `kIOGPUCommandBufferCallbackErrorTimeout`, and subsequent model initialization in the same Metal state failed. The evaluator now isolates model processes, captures a per-model engine log, detects HTTP 200 responses with zero audio as stream failures, and supports include/exclude ordering. The canary recovered after stopping that engine process; the then-current production engine was not stopped during evaluation. Confucius4 is disqualified on this host pending an upstream or model-specific fix.

### Accepted reference pass

The accepted registered record is the exact remastered 20-second variant-2 pair. The source and registered audio hashes match, and the source and registered transcript hashes match. A separate process-isolated pass used that immutable pair rather than the comparison reference. The private hashes remain in the retained acceptance record rather than the release source.

| Candidate | Output duration | Total request time | RTF | Result |
|---|---:|---:|---:|---|
| Qwen3 0.6B Base 8-bit | 7.68 s | 3.925 s | 0.51 | Valid WAV |
| Qwen3 0.6B CustomVoice 8-bit, patched ICL | 9.60 s | 4.432 s | 0.46 | Valid WAV |
| Qwen3 1.7B Base 8-bit | 6.88 s | 4.133 s | 0.60 | Valid WAV |

These objective results establish that all three Qwen cloning paths accept the registered pair correctly. Speaker identity and emotional fidelity remain subject to human listening review.

HTTP header-first-byte timing is not treated as time-to-first-audio because the streaming response sends headers before generated audio. The table therefore reports total request time and RTF; a client-side first-audio probe remains required before promotion.

## Artifact hashes

| Artifact | SHA-256 |
|---|---|
| `base-reference-id.wav` | `b8404d022cdffafb8700eeb942d7d5d6e5345647c4ead46ef0c902a7bd0a6160` |
| `base-bridge-alias.wav` | `7d93174690c88e63349abd304ebe3e58e23df9f6b457cc087229efdda0a57717` |
| `base-inline.wav` | `60c3e58178e893513088fea760f60a129a468f5f2a0033d18e215834a6ac6c7b` |
| `base-long.wav` | `190160c2b63adc40338380a2c65333b5a995d0262f16afc2b92ee56a8bea938d` |
| `base-stream.wav` | `ccab5a00056e9eaa561b34d80162d9b963f02e9787b401881febb08c240b779f` |
| `custom-reference-id.wav` | `16e1f9d951e8183e41b4e51b9a34e9092fd691589c9ea95b723359b95283a62d` |
| `custom-named.wav` | `01eb5fc1209936c1be438b3e024772f83626ed7197c405b054df39f809ecbfb1` |

## Production cutover and remaining listening review

Production promotion completed after explicit operator direction to stop and restart the TTS components. The production engine reports `0.5.0+unixwzrd.1`; the bridge reports two aliases, two references, registry reachability, and the matching upstream capability revision. The redacted bridge diagnostic for the Hermes acceptance request records the selected alias, its registered reference ID, the revision-pinned Qwen Base path, and HTTP 200 without exposing input or transcript content.

Listen to the retained artifacts and production output and record speaker similarity, intelligibility, emotional fidelity, unexpected noise, truncation, repetition, and prosody. Objective validity and stability do not substitute for that review; use the retained Conda runtime and pre-cutover configuration backup if the production listening result is unacceptable.
