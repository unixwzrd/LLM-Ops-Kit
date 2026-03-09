#!/usr/bin/env python
"""OpenAI-TTS-compatible bridge to MLX Audio.

Accepts OpenAI-style POST /v1/audio/speech and forwards to an MLX endpoint,
injecting configured model/voice/reference media defaults.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib import error, request


UNSUPPORTED_FORMAT_FALLBACKS = {
    "opus": "wav",
    "ogg": "wav",
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _normalize_base(url: str) -> str:
    return url.rstrip("/")


def _mlx_speech_url(base: str) -> str:
    base = _normalize_base(base)
    if base.endswith("/v1"):
        return f"{base}/audio/speech"
    return f"{base}/v1/audio/speech"


def _content_type_for_format(fmt: str) -> str:
    fmt = (fmt or "wav").lower()
    if fmt == "wav":
        return "audio/wav"
    if fmt == "mp3":
        return "audio/mpeg"
    if fmt in ("ogg", "opus"):
        return "audio/ogg"
    if fmt == "flac":
        return "audio/flac"
    return "application/octet-stream"


def _normalize_response_format(requested: str, fallback: str = "wav") -> tuple[str, str | None]:
    requested = (requested or fallback or "wav").lower()
    normalized = UNSUPPORTED_FORMAT_FALLBACKS.get(requested, requested)
    if normalized != requested:
        return normalized, requested
    return normalized, None


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "tts-bridge/1.0"

    def _json(self, code: int, obj: dict[str, Any]) -> None:
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/v1/health"):
            cfg = self.server.bridge_config  # type: ignore[attr-defined]
            self._json(
                200,
                {
                    "ok": True,
                    "upstream": cfg["upstream_base"],
                    "listen_host": cfg["listen_host"],
                    "listen_port": cfg["listen_port"],
                    "defaults": {
                        "model": cfg.get("model", ""),
                        "voice": cfg.get("voice", ""),
                        "ref_audio": cfg.get("ref_audio", ""),
                        "ref_text": cfg.get("ref_text", ""),
                        "response_format": cfg.get("response_format", "wav"),
                    },
                    "compat": {
                        "unsupported_response_formats": UNSUPPORTED_FORMAT_FALLBACKS,
                    },
                },
            )
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in ("/v1/audio/speech", "/audio/speech"):
            self._json(404, {"error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            incoming = json.loads(raw.decode("utf-8"))
            if not isinstance(incoming, dict):
                raise ValueError("payload must be an object")
        except Exception as exc:  # noqa: BLE001
            self._json(400, {"error": f"invalid_json: {exc}"})
            return

        cfg = self.server.bridge_config  # type: ignore[attr-defined]
        output: dict[str, Any] = {}

        requested_format = incoming.get("response_format", cfg.get("response_format", "wav"))
        response_format, downgraded_from = _normalize_response_format(
            str(requested_format), str(cfg.get("response_format", "wav"))
        )

        output["input"] = incoming.get("input", "")
        output["response_format"] = response_format

        model = cfg.get("model") or incoming.get("model", "")
        if model:
            output["model"] = model

        if cfg.get("prefer_incoming_voice"):
            voice = incoming.get("voice") or cfg.get("voice")
        else:
            voice = cfg.get("voice") or incoming.get("voice")
        if voice:
            output["voice"] = voice

        ref_audio = incoming.get("ref_audio") or cfg.get("ref_audio")
        if ref_audio:
            output["ref_audio"] = ref_audio

        ref_text = incoming.get("ref_text") or cfg.get("ref_text")
        if ref_text:
            if isinstance(ref_text, str) and os.path.isfile(ref_text):
                ref_text = _read_text_file(ref_text)
            output["ref_text"] = ref_text

        for k in ("speed", "language", "verbose"):
            if k in incoming:
                output[k] = incoming[k]

        upstream_url = _mlx_speech_url(cfg["upstream_base"])
        print(
            "tts-bridge upstream payload: "
            + json.dumps(output, ensure_ascii=False),
            file=sys.stderr,
            flush=True,
        )
        body = json.dumps(output).encode("utf-8")
        req = request.Request(
            upstream_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=cfg["timeout_seconds"]) as resp:  # noqa: S310
                response_body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", _content_type_for_format(response_format))
                self.send_header("Content-Length", str(len(response_body)))
                if downgraded_from:
                    self.send_header("X-TTS-Bridge-Requested-Format", downgraded_from)
                    self.send_header("X-TTS-Bridge-Delivered-Format", response_format)
                self.end_headers()
                self.wfile.write(response_body)
        except error.HTTPError as exc:
            err_body = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as exc:  # noqa: BLE001
            self._json(502, {"error": f"upstream_error: {exc}"})

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpenAI TTS -> MLX bridge")
    p.add_argument("--listen-host", default=_env("TTS_BRIDGE_HOST", "127.0.0.1"))
    p.add_argument("--listen-port", type=int, default=int(_env("TTS_BRIDGE_PORT", "11440")))
    p.add_argument("--upstream-base", default=_env("TTS_BRIDGE_UPSTREAM_BASE", "http://127.0.0.1:11439/v1"))
    p.add_argument("--model", default=_env("TTS_BRIDGE_MODEL", ""))
    p.add_argument("--voice", default=_env("TTS_BRIDGE_VOICE", "serena"))
    p.add_argument(
        "--prefer-incoming-voice",
        action="store_true",
        default=_env("TTS_BRIDGE_PREFER_INCOMING_VOICE", "0").lower() in ("1", "true", "yes"),
    )
    p.add_argument("--ref-audio", default=_env("TTS_BRIDGE_REF_AUDIO", ""))
    p.add_argument("--ref-text", default=_env("TTS_BRIDGE_REF_TEXT", ""))
    p.add_argument("--response-format", default=_env("TTS_BRIDGE_RESPONSE_FORMAT", "wav"))
    p.add_argument("--timeout-seconds", type=int, default=int(_env("TTS_BRIDGE_TIMEOUT_SECONDS", "120")))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    config = {
        "listen_host": args.listen_host,
        "listen_port": args.listen_port,
        "upstream_base": args.upstream_base,
        "model": args.model,
        "voice": args.voice,
        "prefer_incoming_voice": args.prefer_incoming_voice,
        "ref_audio": args.ref_audio,
        "ref_text": args.ref_text,
        "response_format": args.response_format,
        "timeout_seconds": args.timeout_seconds,
    }
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), BridgeHandler)
    server.bridge_config = config  # type: ignore[attr-defined]
    print(
        "tts-bridge: listening on "
        f"http://{args.listen_host}:{args.listen_port} "
        f"upstream={args.upstream_base}",
        flush=True,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
