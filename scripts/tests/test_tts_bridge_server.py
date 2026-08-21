#!/usr/bin/env python
"""Focused tests for the local MLX TTS bridge."""

from __future__ import annotations

import argparse
import importlib.util
import json
import socket
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request


MODULE_PATH = Path(__file__).resolve().parents[1] / "tts_bridge_server.py"
SCRIPTS_DIR = MODULE_PATH.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
SPEC = importlib.util.spec_from_file_location("tts_bridge_server", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _free_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
    except PermissionError as exc:
        raise unittest.SkipTest(f"local socket bind not permitted in this environment: {exc}") from exc


class _FakeUpstreamHandler(BaseHTTPRequestHandler):
    received: list[dict[str, object]] = []
    audio_bytes = b"RIFFfakewav"

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/v1/audio/capabilities"):
            payload = json.dumps(
                {
                    "revision": "0.5.0+unixwzrd.1",
                    "family": "qwen3_tts",
                    "clone_mode": "audio_transcript",
                    "transcript_required": True,
                    "style_controls": [],
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/v1/audio/references":
            payload = json.dumps({"object": "list", "data": []}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/v1/models":
            payload = json.dumps({"data": [{"id": "fake-model"}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        payload = json.loads(body.decode("utf-8"))
        type(self).received.append(payload)
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(self.audio_bytes)))
        self.end_headers()
        self.wfile.write(self.audio_bytes)

    def log_message(self, fmt: str, *args: object) -> None:
        return


@contextmanager
def _run_server(server: ThreadingHTTPServer):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


class TTSBridgeServerTests(unittest.TestCase):
    def test_apply_pronounce_map_prefers_longest_match(self) -> None:
        text, replacements = MODULE._apply_pronounce_map(
            "Use <= and / here",
            {"<=": " less than or equal to ", "<": " open angle ", "/": " slash "},
        )
        self.assertEqual(text, "Use  less than or equal to  and  slash  here")
        self.assertEqual(replacements, 2)

    def test_apply_pronounce_map_allows_empty_replacement(self) -> None:
        text, replacements = MODULE._apply_pronounce_map('A "quoted" value', {'"': ""})
        self.assertEqual(text, "A quoted value")
        self.assertEqual(replacements, 2)

    def test_build_bridge_config_uses_defaults_from_config_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples_dir = root / "samples"
            samples_dir.mkdir()
            (root / "pronounce.json").write_text(
                json.dumps({"/": " slash "}), encoding="utf-8"
            )
            (root / "voice-map.json").write_text(
                json.dumps({"Faith": {"sample": "faith.wav"}}),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                listen_host="127.0.0.1",
                listen_port=11440,
                upstream_base="http://127.0.0.1:11439/v1",
                model="",
                voice="",
                prefer_incoming_voice=False,
                ref_audio="",
                ref_text="",
                response_format="wav",
                timeout_seconds=120,
                config_dir=str(root),
                pronounce_config=None,
                voice_map_config=None,
                samples_dir=str(samples_dir),
            )
            cfg = MODULE.build_bridge_config(args)
            self.assertEqual(cfg["config_dir"], str(root.resolve()))
            self.assertEqual(cfg["pronounce_config"], str((root / "pronounce.json").resolve()))
            self.assertEqual(cfg["voice_map_config"], str((root / "voice-map.json").resolve()))
            self.assertEqual(cfg["pronounce_map"], {"/": " slash "})
            self.assertIn("faith", cfg["voice_map"])

    def test_build_bridge_config_parses_voice_map_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples_dir = root / "samples"
            samples_dir.mkdir()
            (root / "voice-map.json").write_text(
                json.dumps(
                    {
                        "defaults": {
                            "sample_dir": "mia",
                            "sample": "default.wav",
                        },
                        "Faith": {"sample": "faith.wav"},
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                listen_host="127.0.0.1",
                listen_port=11440,
                upstream_base="http://127.0.0.1:11439/v1",
                model="",
                voice="",
                prefer_incoming_voice=False,
                ref_audio="",
                ref_text="",
                response_format="wav",
                timeout_seconds=120,
                config_dir=str(root),
                pronounce_config=None,
                voice_map_config=None,
                samples_dir=str(samples_dir),
            )
            cfg = MODULE.build_bridge_config(args)
            self.assertEqual(cfg["voice_map_defaults"]["sample_dir"], "mia")
            self.assertEqual(cfg["voice_map_defaults"]["sample"], "default.wav")

    def test_build_bridge_config_invalid_json_fails_with_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples_dir = root / "samples"
            samples_dir.mkdir()
            bad = root / "pronounce.json"
            bad.write_text("{bad", encoding="utf-8")
            args = argparse.Namespace(
                listen_host="127.0.0.1",
                listen_port=11440,
                upstream_base="http://127.0.0.1:11439/v1",
                model="",
                voice="",
                prefer_incoming_voice=False,
                ref_audio="",
                ref_text="",
                response_format="wav",
                timeout_seconds=120,
                config_dir=str(root),
                pronounce_config=None,
                voice_map_config=None,
                samples_dir=str(samples_dir),
            )
            with self.assertRaises(MODULE.BridgeConfigError) as ctx:
                MODULE.build_bridge_config(args)
            self.assertIn("pronounce config invalid JSON", str(ctx.exception))
            self.assertIn(str(bad.resolve()), str(ctx.exception))

    def test_build_bridge_config_malformed_alias_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples_dir = root / "samples"
            samples_dir.mkdir()
            (root / "voice-map.json").write_text(
                json.dumps({"Faith": {}}),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                listen_host="127.0.0.1",
                listen_port=11440,
                upstream_base="http://127.0.0.1:11439/v1",
                model="",
                voice="",
                prefer_incoming_voice=False,
                ref_audio="",
                ref_text="",
                response_format="wav",
                timeout_seconds=120,
                config_dir=str(root),
                pronounce_config=None,
                voice_map_config=None,
                samples_dir=str(samples_dir),
            )
            with self.assertRaises(MODULE.BridgeConfigError) as ctx:
                MODULE.build_bridge_config(args)
            self.assertIn("exactly one of 'sample' or 'reference_id'", str(ctx.exception))
            self.assertIn("Faith", str(ctx.exception))

    def test_build_upstream_payload_applies_alias_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples_dir = root / "samples"
            samples_dir.mkdir()
            sample = samples_dir / "Mia-Faith-Prof-Emotive-20s-Sample-Mastered-01.wav"
            transcript = sample.with_suffix(".txt")
            sample.write_bytes(b"wav")
            transcript.write_text("sample transcript", encoding="utf-8")
            cfg = {
                "model": "model-path",
                "voice": "",
                "prefer_incoming_voice": False,
                "ref_audio": "",
                "ref_text": "",
                "response_format": "wav",
                "pronounce_map": {"/": " slash "},
                "voice_map_defaults": {},
                "voice_map": {
                    "faith": {
                        "alias": "Faith",
                        "sample": sample.name,
                    }
                },
                "samples_dir": str(samples_dir),
            }
            output, response_format, downgraded_from = MODULE.build_upstream_payload(
                {"input": "a/b", "voice": "FAITH"},
                cfg,
            )
            self.assertEqual(response_format, "wav")
            self.assertIsNone(downgraded_from)
            self.assertEqual(output["input"], "a slash b")
            self.assertNotIn("voice", output)
            self.assertEqual(output["ref_audio"], str(sample.resolve()))
            self.assertEqual(output["ref_text"], str(transcript.resolve()))
            self.assertEqual(output["model"], "model-path")

    def test_explicit_refs_override_alias_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples_dir = root / "samples"
            samples_dir.mkdir()
            alias_sample = samples_dir / "faith.wav"
            alias_transcript = alias_sample.with_suffix(".txt")
            alias_sample.write_bytes(b"wav")
            alias_transcript.write_text("sample transcript", encoding="utf-8")
            explicit_sample = root / "explicit.wav"
            explicit_transcript = root / "explicit.txt"
            explicit_sample.write_bytes(b"wav")
            explicit_transcript.write_text("explicit transcript", encoding="utf-8")
            cfg = {
                "model": "",
                "voice": "",
                "prefer_incoming_voice": False,
                "ref_audio": "",
                "ref_text": "",
                "response_format": "wav",
                "pronounce_map": {},
                "voice_map_defaults": {},
                "voice_map": {
                    "faith": {
                        "alias": "Faith",
                        "sample": alias_sample.name,
                    }
                },
                "samples_dir": str(samples_dir),
            }
            output, _, _ = MODULE.build_upstream_payload(
                {
                    "input": "hello",
                    "voice": "Faith",
                    "ref_audio": str(explicit_sample),
                    "ref_text": str(explicit_transcript),
                },
                cfg,
            )
            self.assertEqual(output["ref_audio"], str(explicit_sample))
            self.assertEqual(output["ref_text"], str(explicit_transcript))

    def test_missing_alias_sample_forwards_path_for_upstream_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples_dir = root / "samples"
            samples_dir.mkdir()
            cfg = {
                "model": "",
                "voice": "",
                "prefer_incoming_voice": False,
                "ref_audio": "",
                "ref_text": "",
                "response_format": "wav",
                "pronounce_map": {},
                "voice_map_defaults": {},
                "voice_map": {
                    "faith": {
                        "alias": "Faith",
                        "sample": "missing.wav",
                    }
                },
                "samples_dir": str(samples_dir),
            }
            output, _, _ = MODULE.build_upstream_payload(
                {"input": "hello", "voice": "Faith"}, cfg
            )
            self.assertEqual(output["ref_audio"], str((samples_dir / "missing.wav").resolve()))
            self.assertEqual(output["ref_text"], str((samples_dir / "missing.txt").resolve()))

    def test_health_payload_reports_config_paths_and_counts(self) -> None:
        cfg = {
            "upstream_base": "http://127.0.0.1:11439/v1",
            "listen_host": "127.0.0.1",
            "listen_port": 11440,
            "model": "model-path",
            "voice": "",
            "ref_audio": "/tmp/sample.wav",
            "ref_text": "/tmp/sample.txt",
            "response_format": "wav",
            "config_dir": "/tmp/config",
            "pronounce_config": "/tmp/config/pronounce.json",
            "pronounce_config_exists": True,
            "pronounce_map": {"/": " slash "},
            "voice_map_config": "/tmp/config/voice-map.json",
            "voice_map_config_exists": False,
            "voice_map_defaults": {"sample_dir": "/tmp/samples"},
            "voice_map": {"faith": {"alias": "Faith", "sample": "faith.wav"}},
            "samples_dir": "/tmp/samples",
            "samples_dir_exists": True,
        }
        payload = MODULE._build_health_payload(cfg)
        self.assertEqual(payload["config"]["config_dir"], "/tmp/config")
        self.assertEqual(payload["config"]["pronounce_entry_count"], 1)
        self.assertEqual(payload["config"]["voice_map_entry_count"], 1)
        self.assertEqual(payload["alias_count"], 1)
        self.assertNotIn("voice_map_defaults", payload["config"])
        self.assertNotIn("samples_dir", payload["config"])
        self.assertNotIn("ref_audio", payload["defaults"])
        self.assertNotIn("ref_text", payload["defaults"])

    def test_voice_map_defaults_can_supply_sample_dir_and_fallback_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples_dir = root / "global-samples"
            samples_dir.mkdir()
            voice_set_dir = samples_dir / "mia"
            voice_set_dir.mkdir()
            sample = voice_set_dir / "default-faith.wav"
            transcript = voice_set_dir / "default-faith.txt"
            sample.write_bytes(b"wav")
            transcript.write_text("sample transcript", encoding="utf-8")
            cfg = {
                "model": "",
                "voice": "",
                "prefer_incoming_voice": False,
                "ref_audio": "",
                "ref_text": "",
                "response_format": "wav",
                "pronounce_map": {},
                "voice_map_defaults": {
                    "sample": "default-faith.wav",
                    "sample_dir": "mia",
                },
                "voice_map": {},
                "samples_dir": str(samples_dir),
            }
            output, _, _ = MODULE.build_upstream_payload({"input": "hello"}, cfg)
            self.assertEqual(output["ref_audio"], str(sample.resolve()))
            self.assertEqual(output["ref_text"], str(transcript.resolve()))

    def test_no_configured_voice_leaves_voice_unset(self) -> None:
        cfg = {
            "model": "",
            "voice": "",
            "prefer_incoming_voice": False,
            "ref_audio": "",
            "ref_text": "",
            "response_format": "wav",
            "pronounce_map": {},
            "voice_map_defaults": {},
            "voice_map": {},
            "samples_dir": "/tmp/samples",
        }
        output, _, _ = MODULE.build_upstream_payload({"input": "hello"}, cfg)
        self.assertNotIn("voice", output)

    def test_bridge_health_endpoint_reports_loaded_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples_dir = root / "samples"
            samples_dir.mkdir()
            pronounce = root / "pronounce.json"
            voice_map = root / "voice-map.json"
            pronounce.write_text(json.dumps({"/": " slash "}), encoding="utf-8")
            voice_map.write_text(
                json.dumps({"Faith": {"sample": "faith.wav"}}),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                listen_host="127.0.0.1",
                listen_port=_free_port(),
                upstream_base=f"http://127.0.0.1:{_free_port()}/v1",
                model="model-path",
                voice="",
                prefer_incoming_voice=False,
                ref_audio="",
                ref_text="",
                response_format="wav",
                timeout_seconds=5,
                config_dir=str(root),
                pronounce_config=None,
                voice_map_config=None,
                samples_dir=str(samples_dir),
            )
            cfg = MODULE.build_bridge_config(args)
            server = ThreadingHTTPServer((args.listen_host, args.listen_port), MODULE.BridgeHandler)
            server.bridge_config = cfg  # type: ignore[attr-defined]
            with _run_server(server):
                with request.urlopen(
                    f"http://{args.listen_host}:{args.listen_port}/health", timeout=5
                ) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["config"]["pronounce_entry_count"], 1)
            self.assertEqual(payload["config"]["voice_map_entry_count"], 1)
            self.assertNotIn("samples_dir", payload["config"])
            self.assertFalse(payload["registry_reachable"])

    def test_bridge_post_rewrites_text_and_resolves_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples_dir = root / "samples"
            samples_dir.mkdir()
            sample = samples_dir / "Mia-Faith-Prof-Emotive-20s-Sample-Mastered-01.wav"
            transcript = sample.with_suffix(".txt")
            sample.write_bytes(b"wav")
            transcript.write_text("sample transcript", encoding="utf-8")

            _FakeUpstreamHandler.received = []
            upstream_port = _free_port()
            upstream = ThreadingHTTPServer(("127.0.0.1", upstream_port), _FakeUpstreamHandler)

            args = argparse.Namespace(
                listen_host="127.0.0.1",
                listen_port=_free_port(),
                upstream_base=f"http://127.0.0.1:{upstream_port}/v1",
                model="model-path",
                voice="",
                prefer_incoming_voice=False,
                ref_audio="",
                ref_text="",
                response_format="wav",
                timeout_seconds=5,
                config_dir=str(root),
                pronounce_config=None,
                voice_map_config=None,
                samples_dir=str(samples_dir),
            )
            cfg = MODULE.build_bridge_config(args)
            cfg["pronounce_map"] = {"/": " slash "}
            cfg["voice_map_defaults"] = {}
            cfg["voice_map"] = {
                "faith": {
                    "alias": "Faith",
                    "sample": sample.name,
                }
            }
            bridge = ThreadingHTTPServer((args.listen_host, args.listen_port), MODULE.BridgeHandler)
            bridge.bridge_config = cfg  # type: ignore[attr-defined]

            with _run_server(upstream), _run_server(bridge):
                req = request.Request(
                    f"http://{args.listen_host}:{args.listen_port}/v1/audio/speech",
                    data=json.dumps(
                        {
                            "input": "alpha/beta",
                            "voice": "Faith",
                            "response_format": "ogg",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with request.urlopen(req, timeout=5) as resp:
                    body = resp.read()
                    headers = dict(resp.headers.items())

            self.assertEqual(body, _FakeUpstreamHandler.audio_bytes)
            self.assertEqual(headers.get("X-TTS-Bridge-Requested-Format"), "ogg")
            self.assertEqual(headers.get("X-TTS-Bridge-Delivered-Format"), "wav")
            self.assertEqual(len(_FakeUpstreamHandler.received), 1)
            upstream_payload = _FakeUpstreamHandler.received[0]
            self.assertEqual(upstream_payload["input"], "alpha slash beta")
            self.assertNotIn("voice", upstream_payload)
            self.assertEqual(upstream_payload["model"], "model-path")
            self.assertEqual(upstream_payload["response_format"], "wav")
            self.assertEqual(upstream_payload["ref_audio"], str(sample.resolve()))
            self.assertEqual(upstream_payload["ref_text"], str(transcript.resolve()))

    def test_reference_id_alias_exposes_metadata_without_paths(self) -> None:
        cfg = {
            "model": "qwen-model",
            "voice": "",
            "prefer_incoming_voice": False,
            "ref_audio": "",
            "ref_text": "",
            "response_format": "wav",
            "pronounce_map": {"/": " slash "},
            "voice_map_defaults": {},
            "voice_map": {
                "faith-emotive": {
                    "alias": "Faith-Emotive",
                    "reference_id": "ref_0123456789abcdef0123456789abcdef",
                    "language": "en",
                    "emotion": "warm",
                    "intensity": 0.7,
                }
            },
            "samples_dir": "/private/samples",
            "upstream_capabilities": {
                "family": "qwen3_tts",
                "style_controls": [],
            },
        }
        output, _, _ = MODULE.build_upstream_payload(
            {"input": "a/b", "voice": "Faith-Emotive", "emotion": "warm"}, cfg
        )
        self.assertEqual(output["input"], "a slash b")
        self.assertEqual(
            output["reference_id"], "ref_0123456789abcdef0123456789abcdef"
        )
        self.assertEqual(output["lang_code"], "en")
        self.assertNotIn("language", output)
        self.assertNotIn("ref_audio", output)
        self.assertNotIn("ref_text", output)
        voices = MODULE._build_voices_payload(cfg, cfg["upstream_capabilities"])
        voice = voices["data"][0]
        self.assertEqual(voice["source"], "reference_id")
        self.assertEqual(voice["style"]["emotion"], "warm")
        self.assertNotIn("/private/samples", str(voice))

    def test_inline_reference_overrides_alias_and_is_redacted(self) -> None:
        cfg = {
            "model": "qwen-model",
            "voice": "",
            "prefer_incoming_voice": False,
            "ref_audio": "",
            "ref_text": "",
            "response_format": "wav",
            "pronounce_map": {"sample": "changed"},
            "voice_map_defaults": {},
            "voice_map": {
                "faith": {
                    "alias": "Faith",
                    "reference_id": "ref_0123456789abcdef0123456789abcdef",
                }
            },
            "samples_dir": "/tmp/samples",
            "upstream_capabilities": {
                "family": "qwen3_tts",
                "style_controls": [],
            },
        }
        reference = {
            "filename": "voice.wav",
            "audio_base64": "private-audio",
            "transcript": "sample transcript must remain exact",
        }
        output, _, _ = MODULE.build_upstream_payload(
            {"input": "sample target", "voice": "Faith", "reference": reference},
            cfg,
        )
        self.assertEqual(output["input"], "changed target")
        self.assertEqual(output["reference"]["transcript"], reference["transcript"])
        self.assertNotIn("reference_id", output)
        redacted = MODULE._redact_upstream_payload(output)
        self.assertNotIn("private-audio", str(redacted))
        self.assertNotIn("sample transcript", str(redacted))
        self.assertNotIn("changed target", str(redacted))

    def test_style_controls_translate_or_reject_strictly(self) -> None:
        base_cfg = {
            "model": "model",
            "voice": "",
            "prefer_incoming_voice": False,
            "ref_audio": "",
            "ref_text": "",
            "response_format": "wav",
            "pronounce_map": {},
            "voice_map_defaults": {},
            "voice_map": {},
            "samples_dir": "/tmp/samples",
        }
        chatterbox = dict(base_cfg)
        chatterbox["upstream_capabilities"] = {
            "family": "chatterbox",
            "style_controls": ["exaggeration"],
        }
        output, _, _ = MODULE.build_upstream_payload(
            {
                "input": "hello",
                "reference_id": "ref_0123456789abcdef0123456789abcdef",
                "intensity": 0.65,
            },
            chatterbox,
        )
        self.assertEqual(output["exaggeration"], 0.65)
        self.assertNotIn("intensity", output)

        qwen_named = dict(base_cfg)
        qwen_named["upstream_capabilities"] = {
            "family": "qwen3_tts",
            "style_controls": ["instruct"],
        }
        output, _, _ = MODULE.build_upstream_payload(
            {"input": "hello", "voice": "Ethan", "instruction": "calm"},
            qwen_named,
        )
        self.assertEqual(output["instruct"], "calm")
        with self.assertRaises(MODULE.BridgeRequestError) as ctx:
            MODULE.build_upstream_payload(
                {
                    "input": "hello",
                    "reference_id": "ref_0123456789abcdef0123456789abcdef",
                    "instruction": "calm",
                },
                qwen_named,
            )
        self.assertEqual(ctx.exception.status, 422)

    def test_voice_map_accepts_distinct_reference_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice-map.json"
            path.write_text(
                json.dumps(
                    {
                        "Neutral": {
                            "reference_id": "ref_00000000000000000000000000000000",
                            "emotion": "neutral",
                        },
                        "Emotive": {
                            "reference_id": "ref_11111111111111111111111111111111",
                            "emotion": "joyful",
                        },
                    }
                ),
                encoding="utf-8",
            )
            _, aliases = MODULE._normalize_voice_map(path)
            self.assertNotEqual(
                aliases["neutral"]["reference_id"],
                aliases["emotive"]["reference_id"],
            )


if __name__ == "__main__":
    unittest.main()
