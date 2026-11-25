# Remote Voice Cloning and TTS Evaluation

**Created**: 2026-08-21
**Updated**: 2026-11-19

The production TTS architecture co-locates the patched MLX-Audio engine and the LLM-Ops bridge on `xanax-model`. The engine owns immutable reference audio/transcript pairs; the bridge owns operator-friendly voice aliases and input normalization. Hermes is only a client and does not need model dependencies, sample files, or a fallback bridge.

## Product boundary

Patched MLX-Audio `0.5.0+unixwzrd.1` provides the cloning engine, atomic reference registry, inline reference payloads, allowlisted legacy server paths, strong bounded Qwen ICL caching, CustomVoice ICL routing, administrative mutation authentication, and model capability reporting.

The LLM-Ops TTS bridge provides named aliases, pronunciation and special-character substitution on target input only, normalized expressive controls, model-specific compatibility translation, strict capability validation, alias discovery, and redacted diagnostics. It never modifies a reference transcript and never logs target text, reference text, sample paths, audio, credentials, or inline payloads.

This system guarantees that a registered reference audio file and transcript are stored and addressed as one immutable pair. It does not claim to prove that the transcript semantically matches the recording; known-pair review remains the acceptance authority.

## Capture audio for a listening comparison

On the bridge host, use `tts-bridge status` to find the service's `config_dir`. Capture is off unless the bridge's execution user places an owner-only (mode `0600`) `audio-capture.json` there. The standalone Python bridge also accepts `--audio-capture-config PATH`. Set `directory` to an absolute private local path (mode `0700`), outside shared or synced storage. For example:

```json
{
  "enabled": true,
  "directory": "/path/to/private/tts-capture",
  "max_responses": 10,
  "max_bytes": 26214400,
  "include_text": false
}
```

Restart **only the bridge** when speech is idle. The recorder saves the exact HTTP response audio bytes and a JSON receipt with UTC time, format, byte count and SHA-256. Raw PCM remains raw; `pcm_sample_rate` can document a known PCM rate in the receipt, without changing the recording. Set `include_text` to true only if you want the processed synthesis text saved alongside the audio. It never captures reference audio/text, headers or credentials. A shared bridge can see any request passing through it, including other clients; use a short, controlled test window. The optional `voice` filter matches the bridge's selected alias, not the requesting app.

Check the counters under `audio_capture` in `GET /health`. Limits are at most 100 responses and 25 MiB including receipts. In the default `"retention": "batch"` mode, capture stops at the first bound and never replaces saved files.

For intermittent playback problems, set `"retention": "rolling"` and choose a **new, dedicated private directory**. This retains the most recent pairs: a new response replaces the oldest complete pair when the response limit is reached, or as many oldest pairs as needed for the byte limit. Each numbered subdirectory contains the exact audio and its `receipt.json`, published together. The sequence persists across restarts, and a response too large for the whole budget is skipped without deleting earlier pairs. Copy a suspect pair out of the rolling directory promptly if you want to keep it. Never point rolling mode at an existing batch or another project's directory. If a previous write was interrupted, the recorder can remove its own incomplete staging data, but refuses to remove unknown files.

Turn off either mode by setting `enabled` to false and restarting only the bridge. Neither the normal bridge log nor its health response includes recorded audio, text, or the destination path.

## Reference APIs

Registry creation, metadata renaming, and deletion require `MLX_AUDIO_REFERENCE_ADMIN_TOKEN`. The token is supplied as a bearer token or `X-MLX-Audio-Admin-Token` and must not be placed in command history or committed configuration. Renaming changes only the public label; the immutable audio/transcript pair, hashes, and `reference_id` remain unchanged.

```bash
curl -fsS -X POST http://127.0.0.1:12439/v1/audio/references \
  -H "Authorization: Bearer $MLX_AUDIO_REFERENCE_ADMIN_TOKEN" \
  -F 'name=Mia1 neutral' \
  -F 'language=en' \
  -F 'emotion=neutral' \
  -F 'audio=@mia1-neutral.wav;type=audio/wav' \
  -F 'transcript=<mia1-neutral.txt'
```

`GET /v1/audio/references` and `GET /v1/audio/references/{id}` return IDs, hashes, duration, language, style, byte count, and clone capability without returning paths, audio, or transcript content. `DELETE /v1/audio/references/{id}` is administrative. `POST /v1/audio/speech` accepts one of `reference_id`, an inline `reference` object, or the legacy allowlisted `ref_audio` and `ref_text` pair.

Legacy server paths are disabled unless `MLX_AUDIO_REFERENCE_ROOTS` is configured. The default registry root is `${XDG_DATA_HOME:-~/.local/share}/mlx-audio/references`. Registration accepts WAV, FLAC, MP3, and M4A; defaults are 20 MiB encoded audio, 1 to 30 seconds decoded duration, and 8 KiB exact UTF-8 transcript.

## Voice aliases and controls

An alias may select a registered `reference_id`, an explicit `sample` with optional `ref_text`, or omit both to derive `<alias>.wav` and `<alias>.txt` under the configured samples directory. When `ref_text` is omitted from an explicit sample entry, the bridge derives the transcript by replacing the sample extension with `.txt`. An alias source overrides any default clone source. Derived aliases return HTTP 422 when their audio file, or a transcript required by the loaded model, is missing. `emotion`, `intensity`, and `instruction` are optional normalized style metadata. See [`voice-map.example.json`](../examples/tts/voice-map.example.json).

- Qwen Base and patched Qwen CustomVoice cloning derive speaker and emotional character from the reference pair. Explicit instruction is rejected.
- Qwen CustomVoice named-speaker mode and VoiceDesign map `instruction` to upstream `instruct`.
- Chatterbox maps `intensity` to `exaggeration`; speaker and emotion identity remain reference-driven.
- A requested control unsupported by the loaded model returns HTTP 422.

Pronunciation substitutions are applied only to the target `input`. They are never applied to reference transcripts, including literal inline transcripts.

### Sampling configuration

Set optional numeric controls under `defaults.sampling` or an individual voice alias's `sampling` in `voice-map.json`. Merge these fields into your existing file so reference and pronunciation settings stay intact.

```json
{
  "defaults": {
    "sampling": {"temperature": 0.7, "top_p": 0.95, "top_k": 40, "repetition_penalty": 1.0}
  },
  "Narrator": {
    "sampling": {"temperature": 0.5}
  }
}
```

Each field uses the first value supplied by the request, the voice alias, or the voice-map defaults. If none supplies it, the bridge omits that field and the upstream model uses its own default. Explicit clone references change reference conditioning, not the selected alias's sampling policy. Restart only the bridge after editing its voice map.

`temperature` must be finite and nonnegative; `top_p` must be finite and within `[0, 1]`; `top_k` must be a nonnegative integer; and `repetition_penalty` must be finite and positive. Booleans, numeric strings, nulls, unsupported sampling keys in the voice map, and out-of-range values are rejected. Invalid voice-map sampling fails startup; invalid request sampling returns HTTP 422. The health endpoint shows global sampling defaults, and redacted diagnostics show the effective numeric request settings.

## Canary and production topology

The immutable UV canary uses engine port `12439` and bridge port `12440`, with the bridge upstream set to `http://127.0.0.1:12439/v1`. The canary does not replace or stop production.

The current objective results and remaining listening gate are recorded in [`2026-08-21-tts-canary.md`](./evidence/2026-08-21-tts-canary.md).

After acceptance, the engine remains on `11439`; the model-host bridge listens on `11440` and uses `http://127.0.0.1:11439/v1`. Hermes then uses `http://MODEL_HOST_LAN:11440/v1`. The old Conda engine and Hermes-host bridge remain intact but stopped for rollback.

Cutover requires direct engine, bridge alias, inline pair, and registered-ID tests across Qwen Base and CustomVoice, short and long target text, streaming and non-streaming. Record time to first audio, real-time factor, peak memory, cache benefit, speaker similarity, intelligibility, emotional fidelity, malformed-request recovery, and sample/transcript pair hashes. Logs may retain only reference ID, digest prefix, byte count, duration, and cache result.

## Model evaluation

The revision-pinned inventory is [`model-evaluation-manifest.json`](../examples/tts/model-evaluation-manifest.json). Every download goes into a new revision-qualified directory. Existing unqualified Qwen directories are provenance-unknown and remain untouched.

All candidates use the same accepted reference material and target script. Promotion requires acceptable latency, long-response stability, licensing, bridge compatibility, cache behavior, and rollback—not subjective quality alone. Higgs Audio v3 remains research-only and is not downloaded or production-qualified because of its non-commercial license.

## Rollback

Rollback restores the previous Hermes TTS base URL, stops the model-host bridge, and restarts the retained Conda-backed engine and Hermes-host bridge. Registry records and revision-pinned model directories are retained; encoded in-memory caches are disposable and are rebuilt after restart.
