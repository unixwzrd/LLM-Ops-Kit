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
from pathlib import Path
from typing import Any
from urllib import error, request

from log_rotation import RotatingLogWriter

UNSUPPORTED_FORMAT_FALLBACKS = {
    "opus": "wav",
    "ogg": "wav",
}

DEFAULT_CONFIG_DIR = "~/.llm-ops"
DEFAULT_PRONOUNCE_CONFIG = "pronounce.json"
DEFAULT_VOICE_MAP_CONFIG = "voice-map.json"
DEFAULT_SAMPLES_DIR = "~/LLM_Repository/TTS/Samples"
DEFAULT_LOG_PATH = "~/.llm-ops/logs/tts-bridge.log"


class BridgeConfigError(RuntimeError):
    """Raised when bridge startup configuration is invalid."""


class BridgeRequestError(RuntimeError):
    """Raised when a request cannot be normalized into an upstream payload."""

    def __init__(self, status: int, domain: str, message: str):
        super().__init__(message)
        self.status = status
        self.domain = domain
        self.message = message


LOGGER: RotatingLogWriter | None = None


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


def _normalize_custom_voice(voice: str) -> str:
    return (voice or "").strip()


def _log(message: str) -> None:
    global LOGGER
    line = f"tts-bridge: {message}\n"
    if LOGGER is not None:
        LOGGER.write(line)
        return
    print(line, file=sys.stderr, end="", flush=True)


def _expand_path(raw: str) -> Path:
    return Path(os.path.expanduser(raw)).resolve()


def _resolve_path(cli_value: str | None, env_name: str, default_value: str) -> Path:
    raw = (cli_value or _env(env_name) or default_value).strip()
    return _expand_path(raw)


def _resolve_child_path(cli_value: str | None, env_name: str, parent: Path, filename: str) -> Path:
    raw = (cli_value or _env(env_name)).strip()
    if raw:
        return _expand_path(raw)
    return (parent / filename).resolve()


def _read_json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise BridgeConfigError(f"{label} invalid JSON at {path}: {exc}") from exc
    except OSError as exc:
        raise BridgeConfigError(f"{label} read failed at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise BridgeConfigError(f"{label} must be a JSON object at {path}")
    return data


def _load_pronounce_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if not path.is_file():
        raise BridgeConfigError(f"pronounce config is not a file: {path}")
    data = _read_json_file(path, "pronounce config")
    resolved: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise BridgeConfigError(f"pronounce config key must be string at {path}")
        if not isinstance(value, str):
            raise BridgeConfigError(
                f"pronounce config value for '{key}' must be string at {path}"
            )
        if not key:
            raise BridgeConfigError(f"pronounce config contains empty key at {path}")
        resolved[key] = value
    return resolved


def _validate_optional_text(label: str, alias_name: str, value: Any, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BridgeConfigError(
            f"voice-map alias '{alias_name}' field '{label}' must be a non-empty string in {path}"
        )
    return value.strip()


def _normalize_voice_alias_entry(alias_name: str, entry: dict[str, Any], path: Path) -> dict[str, Any]:
    missing = [
        field
        for field in ("speaker", "sample")
        if field not in entry or not isinstance(entry[field], str) or not str(entry[field]).strip()
    ]
    if missing:
        raise BridgeConfigError(
            f"voice-map alias '{alias_name}' missing required fields {missing} in {path}"
        )
    normalized: dict[str, Any] = {
        "alias": alias_name.strip(),
        "speaker": _validate_optional_text("speaker", alias_name, entry["speaker"], path),
        "sample": _validate_optional_text("sample", alias_name, entry["sample"], path),
    }
    for field in ("ref_text", "response_format", "language", "sample_dir"):
        if field in entry:
            normalized[field] = _validate_optional_text(field, alias_name, entry[field], path)
    if "speed" in entry:
        speed = entry["speed"]
        if not isinstance(speed, (int, float, str)):
            raise BridgeConfigError(
                f"voice-map alias '{alias_name}' field 'speed' must be string, int, or float in {path}"
            )
        normalized["speed"] = speed
    return normalized


def _normalize_voice_map_defaults(path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in ("speaker", "sample", "ref_text", "response_format", "language", "sample_dir"):
        if field in entry:
            normalized[field] = _validate_optional_text(field, "defaults", entry[field], path)
    if "speed" in entry:
        speed = entry["speed"]
        if not isinstance(speed, (int, float, str)):
            raise BridgeConfigError(
                f"voice-map defaults field 'speed' must be string, int, or float in {path}"
            )
        normalized["speed"] = speed
    return normalized


def _normalize_voice_map(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not path.exists():
        return {}, {}
    if not path.is_file():
        raise BridgeConfigError(f"voice-map config is not a file: {path}")
    data = _read_json_file(path, "voice-map config")
    defaults: dict[str, Any] = {}
    raw_defaults = data.get("defaults")
    if raw_defaults is not None:
        if not isinstance(raw_defaults, dict):
            raise BridgeConfigError(f"voice-map defaults must be a JSON object in {path}")
        defaults = _normalize_voice_map_defaults(path, raw_defaults)
    resolved: dict[str, dict[str, Any]] = {}
    for alias_name, entry in data.items():
        if alias_name == "defaults":
            continue
        if not isinstance(alias_name, str) or not alias_name.strip():
            raise BridgeConfigError(f"voice-map alias name must be a non-empty string in {path}")
        if not isinstance(entry, dict):
            raise BridgeConfigError(
                f"voice-map alias '{alias_name}' must be a JSON object in {path}"
            )
        resolved[alias_name.strip().lower()] = _normalize_voice_alias_entry(alias_name, entry, path)
    return defaults, resolved


def _resolve_alias_path(samples_dir: Path, raw_path: str) -> Path:
    candidate = Path(os.path.expanduser(raw_path))
    if candidate.is_absolute():
        return candidate.resolve()
    return (samples_dir / candidate).resolve()


def _apply_pronounce_map(text: str, pronounce_map: dict[str, str]) -> tuple[str, int]:
    if not pronounce_map or not text:
        return text, 0
    keys = sorted(pronounce_map, key=len, reverse=True)
    out: list[str] = []
    i = 0
    replacements = 0
    while i < len(text):
        matched = False
        for key in keys:
            if text.startswith(key, i):
                out.append(pronounce_map[key])
                i += len(key)
                replacements += 1
                matched = True
                break
        if matched:
            continue
        out.append(text[i])
        i += 1
    return "".join(out), replacements


def _find_voice_alias(voice: str, voice_map: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    candidate = (voice or "").strip().lower()
    if not candidate:
        return None
    return voice_map.get(candidate)


def _build_ref_paths_for_alias(alias: dict[str, Any], samples_dir: Path) -> tuple[Path, Path]:
    sample_path = _resolve_alias_path(samples_dir, str(alias["sample"]))
    raw_ref_text = alias.get("ref_text")
    if raw_ref_text:
        ref_text_path = _resolve_alias_path(samples_dir, str(raw_ref_text))
    else:
        ref_text_path = sample_path.with_suffix(".txt")
    return sample_path, ref_text_path


def _resolve_sample_root(cfg: dict[str, Any], mapping: dict[str, Any] | None = None) -> Path:
    raw = ""
    if mapping is not None:
        raw = str(mapping.get("sample_dir", "")).strip()
    if raw:
        return _resolve_alias_path(Path(cfg["samples_dir"]), raw)
    return Path(cfg["samples_dir"])


def _build_health_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
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
        "config": {
            "config_dir": cfg["config_dir"],
            "log_path": cfg.get("log_path", str(_expand_path(DEFAULT_LOG_PATH))),
            "log_rotate_seconds": cfg.get("log_rotate_seconds", 86400),
            "log_rotate_keep": cfg.get("log_rotate_keep", 5),
            "pronounce_config": cfg["pronounce_config"],
            "pronounce_config_exists": cfg["pronounce_config_exists"],
            "pronounce_entry_count": len(cfg["pronounce_map"]),
            "voice_map_config": cfg["voice_map_config"],
            "voice_map_config_exists": cfg["voice_map_config_exists"],
            "voice_map_entry_count": len(cfg["voice_map"]),
            "voice_map_defaults": cfg.get("voice_map_defaults", {}),
            "samples_dir": cfg["samples_dir"],
            "samples_dir_exists": cfg["samples_dir_exists"],
        },
    }


def build_bridge_config(args: argparse.Namespace) -> dict[str, Any]:
    config_dir = _resolve_path(args.config_dir, "TTS_BRIDGE_CONFIG_DIR", DEFAULT_CONFIG_DIR)
    if config_dir.exists() and not config_dir.is_dir():
        raise BridgeConfigError(f"bridge config dir is not a directory: {config_dir}")

    pronounce_config = _resolve_child_path(
        args.pronounce_config,
        "TTS_BRIDGE_PRONOUNCE_CONFIG",
        config_dir,
        DEFAULT_PRONOUNCE_CONFIG,
    )
    voice_map_config = _resolve_child_path(
        args.voice_map_config,
        "TTS_BRIDGE_VOICE_MAP_CONFIG",
        config_dir,
        DEFAULT_VOICE_MAP_CONFIG,
    )
    samples_dir = _resolve_path(args.samples_dir, "TTS_BRIDGE_SAMPLES_DIR", DEFAULT_SAMPLES_DIR)
    if not samples_dir.exists() or not samples_dir.is_dir():
        raise BridgeConfigError(f"samples dir is not a directory: {samples_dir}")

    pronounce_map = _load_pronounce_map(pronounce_config)
    voice_map_defaults, voice_map = _normalize_voice_map(voice_map_config)

    log_path = getattr(args, "log_path", _env("TTS_BRIDGE_LOG_PATH", DEFAULT_LOG_PATH))
    log_rotate_seconds = int(
        getattr(args, "log_rotate_seconds", int(_env("TTS_BRIDGE_LOG_ROTATE_SECONDS", "86400")))
    )
    log_rotate_keep = int(
        getattr(args, "log_rotate_keep", int(_env("TTS_BRIDGE_LOG_ROTATE_KEEP", "5")))
    )

    cfg = {
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
        "log_path": str(_expand_path(str(log_path))),
        "log_rotate_seconds": log_rotate_seconds,
        "log_rotate_keep": log_rotate_keep,
        "config_dir": str(config_dir),
        "pronounce_config": str(pronounce_config),
        "pronounce_config_exists": pronounce_config.exists(),
        "voice_map_config": str(voice_map_config),
        "voice_map_config_exists": voice_map_config.exists(),
        "samples_dir": str(samples_dir),
        "samples_dir_exists": samples_dir.exists(),
        "pronounce_map": pronounce_map,
        "voice_map_defaults": voice_map_defaults,
        "voice_map": voice_map,
    }

    _log(
        "startup config loaded: "
        + json.dumps(
            {
                "config_dir": cfg["config_dir"],
                "pronounce_config": cfg["pronounce_config"],
                "pronounce_entries": len(pronounce_map),
                "voice_map_config": cfg["voice_map_config"],
                "voice_map_entries": len(voice_map),
                "voice_map_defaults": voice_map_defaults,
                "samples_dir": cfg["samples_dir"],
            },
            ensure_ascii=False,
        )
    )
    return cfg


def build_upstream_payload(
    incoming: dict[str, Any],
    cfg: dict[str, Any],
) -> tuple[dict[str, Any], str, str | None]:
    if "input" not in incoming:
        raise BridgeRequestError(400, "input_validation", "missing required field: input")
    if not isinstance(incoming["input"], str):
        raise BridgeRequestError(400, "input_validation", "field 'input' must be a string")

    try:
        processed_input, replacements = _apply_pronounce_map(
            incoming["input"], cfg["pronounce_map"]
        )
    except Exception as exc:  # noqa: BLE001
        raise BridgeRequestError(
            500, "input_preprocessing", f"failed to preprocess input text: {exc}"
        ) from exc
    if replacements > 0:
        _log(f"input preprocessing applied {replacements} replacement(s)")
    else:
        _log("input preprocessing skipped: no replacements applied")

    output: dict[str, Any] = {"input": processed_input}

    requested_format = incoming.get("response_format", cfg.get("response_format", "wav"))
    response_format, downgraded_from = _normalize_response_format(
        str(requested_format), str(cfg.get("response_format", "wav"))
    )
    output["response_format"] = response_format

    model = cfg.get("model") or incoming.get("model", "")
    if model:
        output["model"] = model

    if cfg.get("prefer_incoming_voice"):
        selected_voice = incoming.get("voice") or cfg.get("voice")
    else:
        selected_voice = cfg.get("voice") or incoming.get("voice")

    alias = _find_voice_alias(str(selected_voice or ""), cfg["voice_map"])
    defaults = cfg.get("voice_map_defaults", {})
    alias_sample_path: Path | None = None
    alias_ref_text_path: Path | None = None
    default_sample_path: Path | None = None
    default_ref_text_path: Path | None = None

    if alias:
        _log(f"voice alias matched: '{selected_voice}' -> '{alias['alias']}'")
        alias_voice = _normalize_custom_voice(str(alias["speaker"]))
        if alias_voice:
            output["voice"] = alias_voice
        alias_sample_path, alias_ref_text_path = _build_ref_paths_for_alias(
            alias, _resolve_sample_root(cfg, alias)
        )
    else:
        _log(f"voice alias skipped: '{selected_voice or ''}'")
        fallback_voice = str(selected_voice or defaults.get("speaker", "") or "")
        normalized_fallback_voice = _normalize_custom_voice(fallback_voice)
        if normalized_fallback_voice:
            output["voice"] = normalized_fallback_voice
        if "sample" in defaults:
            default_mapping = {
                "sample": defaults["sample"],
                "ref_text": defaults.get("ref_text", ""),
            }
            default_sample_path, default_ref_text_path = _build_ref_paths_for_alias(
                default_mapping,
                _resolve_sample_root(cfg, defaults),
            )
            _log("voice-map defaults applied for fallback clone refs")

    explicit_ref_audio = incoming.get("ref_audio")
    explicit_ref_text = incoming.get("ref_text")

    if explicit_ref_audio:
        output["ref_audio"] = explicit_ref_audio
    elif alias_sample_path is not None:
        if not alias_sample_path.is_file():
            raise BridgeRequestError(
                500,
                "alias_resolution",
                f"voice alias '{alias['alias']}' resolved sample missing: {alias_sample_path}",
            )
        output["ref_audio"] = str(alias_sample_path)
    elif default_sample_path is not None:
        if not default_sample_path.is_file():
            raise BridgeRequestError(
                500,
                "alias_resolution",
                f"voice-map defaults resolved sample missing: {default_sample_path}",
            )
        output["ref_audio"] = str(default_sample_path)
    elif cfg.get("ref_audio"):
        output["ref_audio"] = cfg["ref_audio"]

    if explicit_ref_text:
        output["ref_text"] = explicit_ref_text
    elif alias_ref_text_path is not None:
        if not alias_ref_text_path.is_file():
            raise BridgeRequestError(
                500,
                "alias_resolution",
                f"voice alias '{alias['alias']}' resolved transcript missing: {alias_ref_text_path}",
            )
        output["ref_text"] = str(alias_ref_text_path)
    elif default_ref_text_path is not None:
        if not default_ref_text_path.is_file():
            raise BridgeRequestError(
                500,
                "alias_resolution",
                f"voice-map defaults resolved transcript missing: {default_ref_text_path}",
            )
        output["ref_text"] = str(default_ref_text_path)
    elif cfg.get("ref_text"):
        output["ref_text"] = cfg["ref_text"]

    if alias:
        for key in ("speed", "language"):
            if key in incoming:
                output[key] = incoming[key]
            elif key in alias:
                output[key] = alias[key]
        if "response_format" not in incoming and "response_format" in alias:
            output["response_format"], downgraded_from = _normalize_response_format(
                str(alias["response_format"]), str(cfg.get("response_format", "wav"))
            )
    else:
        for key in ("speed", "language", "verbose"):
            if key in incoming:
                output[key] = incoming[key]

    if "verbose" in incoming:
        output["verbose"] = incoming["verbose"]

    return output, output["response_format"], downgraded_from


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "tts-bridge/1.0"

    def _client_gone(self, exc: BaseException) -> bool:
        return isinstance(exc, (BrokenPipeError, ConnectionResetError))

    def _write_bytes(self, payload: bytes) -> bool:
        try:
            self.wfile.write(payload)
            return True
        except Exception as exc:  # noqa: BLE001
            if self._client_gone(exc):
                return False
            raise

    def _json(self, code: int, obj: dict[str, Any]) -> None:
        payload = json.dumps(obj).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
        except Exception as exc:  # noqa: BLE001
            if self._client_gone(exc):
                return
            raise
        self._write_bytes(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/v1/health"):
            cfg = self.server.bridge_config  # type: ignore[attr-defined]
            self._json(200, _build_health_payload(cfg))
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
        try:
            output, response_format, downgraded_from = build_upstream_payload(incoming, cfg)
        except BridgeRequestError as exc:
            _log(f"request rejected [{exc.domain}]: {exc.message}")
            self._json(exc.status, {"error": f"{exc.domain}: {exc.message}"})
            return

        upstream_url = _mlx_speech_url(cfg["upstream_base"])
        debug_output = dict(output)
        if "input" in debug_output:
            debug_output["input"] = "<redacted input text>"
        _log("upstream payload: " + json.dumps(debug_output, ensure_ascii=False))
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
                try:
                    self.send_response(resp.status)
                    self.send_header("Content-Type", _content_type_for_format(response_format))
                    self.send_header("Content-Length", str(len(response_body)))
                    if downgraded_from:
                        self.send_header("X-TTS-Bridge-Requested-Format", downgraded_from)
                        self.send_header("X-TTS-Bridge-Delivered-Format", response_format)
                    self.end_headers()
                except Exception as exc:  # noqa: BLE001
                    if self._client_gone(exc):
                        return
                    raise BridgeRequestError(
                        502, "response_writeback", f"failed to write upstream response: {exc}"
                    ) from exc
                self._write_bytes(response_body)
        except error.HTTPError as exc:
            err_body = exc.read()
            err_text = err_body.decode("utf-8", errors="replace").strip()
            _log(f"upstream request failed: HTTP {exc.code}: {err_text}")
            self._json(
                exc.code,
                {
                    "error": f"upstream_request: HTTP {exc.code}: {exc.reason}",
                    "upstream_body": err_text,
                },
            )
        except BridgeRequestError as exc:
            _log(f"request failed [{exc.domain}]: {exc.message}")
            self._json(exc.status, {"error": f"{exc.domain}: {exc.message}"})
        except Exception as exc:  # noqa: BLE001
            if self._client_gone(exc):
                return
            _log(f"upstream request transport failure: {exc}")
            self._json(502, {"error": f"upstream_request: {exc}"})

    def log_message(self, fmt: str, *args: Any) -> None:
        _log("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), fmt % args))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpenAI TTS -> MLX bridge")
    p.add_argument("--listen-host", default=_env("TTS_BRIDGE_HOST", "127.0.0.1"))
    p.add_argument("--listen-port", type=int, default=int(_env("TTS_BRIDGE_PORT", "11440")))
    p.add_argument(
        "--upstream-base", default=_env("TTS_BRIDGE_UPSTREAM_BASE", "http://127.0.0.1:11439/v1")
    )
    p.add_argument("--model", default=_env("TTS_BRIDGE_MODEL", ""))
    p.add_argument("--voice", default=_env("TTS_BRIDGE_VOICE", ""))
    p.add_argument(
        "--prefer-incoming-voice",
        action="store_true",
        default=_env("TTS_BRIDGE_PREFER_INCOMING_VOICE", "0").lower() in ("1", "true", "yes"),
    )
    p.add_argument("--ref-audio", default=_env("TTS_BRIDGE_REF_AUDIO", ""))
    p.add_argument("--ref-text", default=_env("TTS_BRIDGE_REF_TEXT", ""))
    p.add_argument("--response-format", default=_env("TTS_BRIDGE_RESPONSE_FORMAT", "wav"))
    p.add_argument(
        "--timeout-seconds", type=int, default=int(_env("TTS_BRIDGE_TIMEOUT_SECONDS", "120"))
    )
    p.add_argument("--log-path", default=_env("TTS_BRIDGE_LOG_PATH", DEFAULT_LOG_PATH))
    p.add_argument(
        "--log-rotate-seconds",
        type=int,
        default=int(_env("TTS_BRIDGE_LOG_ROTATE_SECONDS", "86400")),
    )
    p.add_argument(
        "--log-rotate-keep",
        type=int,
        default=int(_env("TTS_BRIDGE_LOG_ROTATE_KEEP", "5")),
    )
    p.add_argument("--config-dir", default=None)
    p.add_argument("--pronounce-config", default=None)
    p.add_argument("--voice-map-config", default=None)
    p.add_argument("--samples-dir", default=None)
    return p.parse_args(argv)


def main() -> int:
    args = parse_args()
    global LOGGER
    LOGGER = RotatingLogWriter(
        Path(os.path.expanduser(args.log_path)),
        rotate_seconds=max(0, int(args.log_rotate_seconds)),
        keep=max(0, int(args.log_rotate_keep)),
        fsync=True,
    )
    try:
        config = build_bridge_config(args)
    except BridgeConfigError as exc:
        _log(f"startup failed: {exc}")
        raise SystemExit(2) from exc
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), BridgeHandler)
    server.bridge_config = config  # type: ignore[attr-defined]
    _log(
        "listening on "
        f"http://{args.listen_host}:{args.listen_port} "
        f"upstream={args.upstream_base}"
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
