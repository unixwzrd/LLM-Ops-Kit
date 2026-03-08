#!/usr/bin/env python
"""OpenAI-TTS-compatible bridge to MLX Audio.

Accepts OpenAI-style POST /v1/audio/speech and forwards to an MLX endpoint,
injecting configured model/voice/reference media defaults.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib import error, request


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
    if fmt in ("opus", "ogg"):
        return "audio/ogg"
    if fmt == "flac":
        return "audio/flac"
    return "application/octet-stream"


def _plan_response_format(requested: str, fallback: str = "wav") -> tuple[str, str, bool]:
    requested = (requested or fallback or "wav").lower()
    fallback = (fallback or "wav").lower()

    # MLX Audio does not currently support opus output. For OpenAI-compatible
    # callers, request wav upstream and transcode locally when possible.
    if requested in ("opus", "ogg"):
        return fallback, requested, shutil.which("ffmpeg") is not None

    return requested, requested, False


def _transcode_audio(audio_bytes: bytes, src_format: str, dst_format: str) -> bytes:
    src_format = (src_format or "wav").lower()
    dst_format = (dst_format or src_format).lower()
    if dst_format == src_format:
        return audio_bytes

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg_not_found")

    with tempfile.TemporaryDirectory(prefix="tts-bridge-") as tmpdir:
        src = os.path.join(tmpdir, f"input.{src_format}")
        dst_ext = "ogg" if dst_format in ("opus", "ogg") else dst_format
        dst = os.path.join(tmpdir, f"output.{dst_ext}")
        with open(src, "wb") as f:
            f.write(audio_bytes)

        cmd = [ffmpeg, "-y", "-v", "error", "-i", src]
        if dst_format in ("opus", "ogg"):
            cmd += ["-c:a", "libopus", "-b:a", "48k", dst]
        else:
            cmd += [dst]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with open(dst, "rb") as f:
            return f.read()


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
                        "ffmpeg": shutil.which("ffmpeg") is not None,
                        "opus_transcode": True,
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
        upstream_format, final_format, should_transcode = _plan_response_format(
            str(requested_format), str(cfg.get("response_format", "wav"))
        )

        output["input"] = incoming.get("input", "")
        output["response_format"] = upstream_format

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
                content_type = resp.headers.get("Content-Type") or _content_type_for_format(upstream_format)

                if should_transcode:
                    try:
                        response_body = _transcode_audio(response_body, upstream_format, final_format)
                        content_type = _content_type_for_format(final_format)
                    except Exception as exc:  # noqa: BLE001
                        self._json(
                            502,
                            {
                                "error": f"transcode_error: {exc}",
                                "requested_format": requested_format,
                                "upstream_format": upstream_format,
                            },
                        )
                        return

                self.send_response(resp.status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(response_body)))
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
        sys.stderr.write("%s - - [%s] %s
" % (self.client_address[0], self.log_date_time_string(), fmt % args))


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
