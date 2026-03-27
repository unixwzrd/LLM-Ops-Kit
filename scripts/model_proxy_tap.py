#!/usr/bin/env python
"""Small reverse proxy tap for OpenAI-compatible APIs.

Logs request/response metadata and JSON bodies to NDJSON while proxying traffic.

Typical use:
  model-proxy-tap --upstream http://<upstream-host>:<upstream-port> --listen-port 18080 \
    --log ~/.llm-ops/logs/model-proxy.ndjson

Then point OpenClaw llamacpp baseUrl to:
  http://127.0.0.1:18080/v1
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import signal
import socketserver
import time
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import ProxyHandler, Request, build_opener

from log_rotation import RotatingLogWriter

try:
    import jinja2
except Exception:  # pragma: no cover - optional dependency at runtime
    jinja2 = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def decode_body(data: bytes) -> tuple[str | None, Any | None]:
    if not data:
        return None, None
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return None, None
    try:
        return text, json.loads(text)
    except Exception:
        return text, None


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = {}
    for k, v in headers.items():
        if k.lower() in {"authorization", "x-api-key", "api-key"}:
            redacted[k] = "<redacted>"
        else:
            redacted[k] = v
    return redacted


def load_chat_template_renderer(template_path_str: str | None) -> tuple[str | None, Any, str | None]:
    if not template_path_str:
        return None, None, None
    if jinja2 is None:
        return template_path_str, None, "jinja2 not available in this Python environment"
    try:
        template_path = Path(os.path.expanduser(template_path_str))
        template_text = template_path.read_text(encoding="utf-8")
        env = jinja2.Environment(
            undefined=jinja2.ChainableUndefined,
            trim_blocks=False,
            lstrip_blocks=False,
            autoescape=False,
        )
        return str(template_path), env.from_string(template_text), None
    except Exception as e:
        return template_path_str, None, f"TemplateLoadError: {e}"


def render_prompt_from_payload(
    payload: Any,
    chat_template_renderer: Any,
    chat_template_path: str | None,
    chat_template_error: str | None,
    chat_template_max_chars: int,
) -> tuple[str | None, str | None]:
    rendered_prompt: str | None = None
    rendered_prompt_error: str | None = None

    if chat_template_renderer and isinstance(payload, dict):
        try:
            normalized_payload = normalize_payload_for_template(payload)
            context = {
                "messages": normalized_payload.get("messages", []),
                "tools": normalized_payload.get("tools", []),
                "system_prompt": normalized_payload.get("system_prompt"),
                "add_generation_prompt": normalized_payload.get("add_generation_prompt", True),
                "bos_token": normalized_payload.get("bos_token", ""),
                "eos_token": normalized_payload.get("eos_token", ""),
                "enable_thinking": normalized_payload.get("enable_thinking"),
                "model": normalized_payload.get("model"),
            }
            rendered_prompt = chat_template_renderer.render(**context)
            if len(rendered_prompt) > chat_template_max_chars:
                rendered_prompt = rendered_prompt[: chat_template_max_chars] + "\n<truncated>"
        except Exception as e:
            rendered_prompt_error = f"TemplateRenderError: {e}"
    elif chat_template_path and chat_template_error:
        rendered_prompt_error = chat_template_error

    return rendered_prompt, rendered_prompt_error


def _normalize_tool_call_arguments(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped[0] in "[{":
            try:
                return json.loads(stripped)
            except Exception:
                return value
    return value


def normalize_payload_for_template(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(payload)
    messages = normalized.get("messages")
    if not isinstance(messages, list):
        return normalized

    for message in messages:
        if not isinstance(message, dict):
            continue
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function")
            if isinstance(function, dict) and "arguments" in function:
                function["arguments"] = _normalize_tool_call_arguments(function.get("arguments"))
            elif "arguments" in tool_call:
                tool_call["arguments"] = _normalize_tool_call_arguments(tool_call.get("arguments"))
    return normalized


def render_input_payloads(args: argparse.Namespace) -> int:
    default_log_dir = os.path.expanduser("~/.llm-ops/logs")
    log_path = Path(os.path.expanduser(args.log))
    rendered_prompt_log_path = (
        Path(os.path.expanduser(args.rendered_prompt_log)) if args.rendered_prompt_log else None
    )
    raw_log_path = Path(os.path.expanduser(args.raw_log)) if args.raw_log else None
    raw_request_log_path = Path(os.path.expanduser(args.raw_request_log)) if args.raw_request_log else None
    raw_response_log_path = Path(os.path.expanduser(args.raw_response_log)) if args.raw_response_log else None

    if raw_request_log_path is None and raw_response_log_path is None and raw_log_path is None:
        raw_request_log_path = Path(f"{default_log_dir}/model-proxy.raw.log")
    else:
        if raw_log_path is not None and raw_request_log_path is None:
            raw_request_log_path = raw_log_path

    chat_template_path, chat_template_renderer, chat_template_error = load_chat_template_renderer(
        args.chat_template
    )

    ProxyTapHandler.log_rotate_seconds = max(0, int(args.log_rotate_seconds))
    ProxyTapHandler.log_rotate_keep = max(0, int(args.log_rotate_keep))
    ProxyTapHandler.log_fsync = bool(args.log_fsync)
    ProxyTapHandler._log_writers = {}
    ProxyTapHandler.log_path = log_path
    ProxyTapHandler.raw_request_log_path = raw_request_log_path
    ProxyTapHandler.rendered_prompt_log_path = rendered_prompt_log_path
    ProxyTapHandler.raw_response_log_path = raw_response_log_path
    ProxyTapHandler.chat_template_path = chat_template_path
    ProxyTapHandler.chat_template_renderer = chat_template_renderer
    ProxyTapHandler.chat_template_error = chat_template_error
    ProxyTapHandler.chat_template_max_chars = int(args.chat_template_max_chars)

    input_label = args.render_input
    if input_label == "-":
        try:
            import sys

            raw_input_text = sys.stdin.read()
        except Exception as e:
            raise SystemExit(f"Failed to read --render-input from stdin: {e}")
        input_path_str = "<stdin>"
    else:
        input_path = Path(os.path.expanduser(input_label))
        try:
            raw_input_text = input_path.read_text(encoding="utf-8")
        except Exception as e:
            raise SystemExit(f"Failed to read --render-input: {e}")
        input_path_str = str(input_path)

    try:
        parsed = json.loads(raw_input_text)
    except Exception as e:
        raise SystemExit(f"Failed to parse --render-input JSON: {e}")

    payloads = parsed if isinstance(parsed, list) else [parsed]
    if not all(isinstance(item, dict) for item in payloads):
        raise SystemExit("--render-input must contain a JSON object or a list of JSON objects")

    helper = ProxyTapHandler.__new__(ProxyTapHandler)

    for idx, payload in enumerate(payloads, start=1):
        ts = utc_now()
        request_id = f"render-{int(time.time() * 1000)}-{idx}"
        request_text = json.dumps(payload, ensure_ascii=False, indent=2)
        rendered_prompt, rendered_prompt_error = render_prompt_from_payload(
            payload,
            chat_template_renderer=chat_template_renderer,
            chat_template_path=chat_template_path,
            chat_template_error=chat_template_error,
            chat_template_max_chars=int(args.chat_template_max_chars),
        )

        helper._write_log(
            {
                "event": "render_input",
                "ts": ts,
                "request_id": request_id,
                "pid": os.getpid(),
                "request_summary": summarize_request(payload),
                "request_text": request_text,
                "rendered_prompt": rendered_prompt,
                "rendered_prompt_error": rendered_prompt_error,
                "render_only": True,
                "input_path": input_path_str,
                "input_index": idx,
            }
        )
        helper._write_framed_log(
            raw_request_log_path,
            ts,
            request_id,
            "RAW_REQUEST",
            request_text,
        )
        if chat_template_path and rendered_prompt is not None:
            helper._write_framed_log(
                rendered_prompt_log_path,
                ts,
                request_id,
                "RENDERED_PROMPT",
                rendered_prompt,
            )
        elif chat_template_path and rendered_prompt_error:
            helper._write_framed_log(
                rendered_prompt_log_path,
                ts,
                request_id,
                "TEMPLATE_ERROR",
                rendered_prompt_error,
            )

        print(
        f"model-proxy-tap render-only processed {len(payloads)} payload(s) "
        f"(raw_log={raw_request_log_path}, rendered_log={rendered_prompt_log_path})",
        flush=True,
    )
    return 0


def prune_older_image_parts(payload: Any) -> tuple[bool, int, int | None]:
    """Keep image_url parts only on the latest user message that has one.

    Returns:
      changed, removed_count, latest_user_index
    """
    if not isinstance(payload, dict):
        return False, 0, None

    messages = payload.get("messages")
    if not isinstance(messages, list):
        return False, 0, None

    latest_idx: int | None = None
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        if any(isinstance(part, dict) and part.get("type") == "image_url" for part in content):
            latest_idx = i

    if latest_idx is None:
        return False, 0, None

    changed = False
    removed = 0
    for i, msg in enumerate(messages):
        if i >= latest_idx:
            continue
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue

        new_content: list[Any] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                removed += 1
                changed = True
                continue
            new_content.append(part)

        if changed:
            msg["content"] = new_content

    return changed, removed, latest_idx


def _text_preview(content: Any, max_chars: int = 220) -> str:
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
        text = " ".join(chunks)
    else:
        text = ""

    one_line = " ".join(text.split())
    if len(one_line) > max_chars:
        return one_line[:max_chars] + "..."
    return one_line


def summarize_request(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    messages = payload.get("messages")
    if not isinstance(messages, list):
        return None

    role_counts: Counter[str] = Counter()
    tool_call_names: Counter[str] = Counter()
    outline: list[dict[str, Any]] = []
    last_user_preview = ""
    image_parts = 0

    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue

        role = str(msg.get("role", "unknown"))
        role_counts[role] += 1

        content = msg.get("content")
        content_kind = type(content).__name__
        text_preview = _text_preview(content)
        if role == "user" and text_preview:
            last_user_preview = text_preview

        if isinstance(content, list):
            image_parts += sum(1 for p in content if isinstance(p, dict) and p.get("type") == "image_url")

        msg_tool_calls = msg.get("tool_calls")
        tc_names: list[str] = []
        if isinstance(msg_tool_calls, list):
            for tc in msg_tool_calls:
                if isinstance(tc, dict):
                    fn = tc.get("function")
                    if isinstance(fn, dict) and isinstance(fn.get("name"), str):
                        name = fn["name"]
                        tc_names.append(name)
                        tool_call_names[name] += 1

        outline.append(
            {
                "i": i,
                "role": role,
                "content_kind": content_kind,
                "preview": text_preview,
                "tool_calls": tc_names,
            }
        )

    return {
        "messages_total": len(messages),
        "role_counts": dict(role_counts),
        "tool_call_counts": dict(tool_call_names),
        "image_parts": image_parts,
        "last_user_preview": last_user_preview,
        "outline": outline,
    }


def extract_response_stats(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    stats: dict[str, Any] = {}
    usage = payload.get("usage")
    if isinstance(usage, dict):
        usage_summary: dict[str, Any] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                usage_summary[key] = value
        prompt_details = usage.get("prompt_tokens_details")
        if isinstance(prompt_details, dict):
            cached_tokens = prompt_details.get("cached_tokens")
            if isinstance(cached_tokens, int):
                usage_summary["cached_prompt_tokens"] = cached_tokens
        if usage_summary:
            stats["usage"] = usage_summary

    timings = payload.get("timings")
    if isinstance(timings, dict):
        timings_summary: dict[str, Any] = {}
        for key in (
            "prompt_n",
            "predicted_n",
            "cache_n",
            "prompt_ms",
            "predicted_ms",
            "prompt_per_second",
            "predicted_per_second",
        ):
            value = timings.get(key)
            if isinstance(value, (int, float)):
                timings_summary[key] = value
        if timings_summary:
            stats["timings"] = timings_summary

    choices = payload.get("choices")
    if isinstance(choices, list):
        finish_reasons: list[str] = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            finish_reason = choice.get("finish_reason")
            if isinstance(finish_reason, str) and finish_reason:
                finish_reasons.append(finish_reason)
        if finish_reasons:
            stats["finish_reasons"] = finish_reasons

    return stats or None


class ProxyTapHandler(BaseHTTPRequestHandler):
    upstream_base: str = ""
    log_path: Path
    max_log_bytes: int = 200000
    timeout_sec: float = 120.0
    latest_image_only: bool = False
    log_fsync: bool = True
    stream_chunk_size: int = 65536
    chat_template_path: str | None = None
    chat_template_max_chars: int = 200000
    chat_template_renderer: Any = None
    chat_template_error: str | None = None
    raw_request_log_path: Path | None = None
    rendered_prompt_log_path: Path | None = None
    raw_response_log_path: Path | None = None
    log_rotate_seconds: int = 86400
    log_rotate_keep: int = 5
    _log_writers: dict[str, RotatingLogWriter] = {}
    upstream_opener = build_opener(ProxyHandler({}))

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep stdout cleaner; diagnostics go to NDJSON log.
        return

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _write_log(self, record: dict[str, Any]) -> None:
        writer = self._writer_for(self.log_path)
        writer.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _write_framed_log(
        self,
        path: Path | None,
        ts_start: str,
        request_id: str,
        label: str,
        body: str | None,
        ts_end: str | None = None,
    ) -> None:
        if path is None:
            return
        text = body or ""
        end_ts = ts_end or ts_start
        payload = [
            f"=== {label} START {ts_start} ===\n",
            text,
        ]
        if not text.endswith("\n"):
            payload.append("\n")
        payload.append(f"=== {label} END {end_ts} ===\n\n")
        self._writer_for(path).write("".join(payload))

    @classmethod
    def _writer_for(cls, path: Path) -> RotatingLogWriter:
        key = str(path)
        writer = cls._log_writers.get(key)
        if writer is None:
            writer = RotatingLogWriter(
                path,
                rotate_seconds=cls.log_rotate_seconds,
                keep=cls.log_rotate_keep,
                fsync=cls.log_fsync,
            )
            cls._log_writers[key] = writer
        return writer

    def _proxy(self) -> None:
        started = time.time()
        request_id = f"{int(started * 1000)}-{os.getpid()}-{id(self)}"

        request_body = self._read_body()
        req_text, req_json = decode_body(request_body)

        request_rewrite: dict[str, Any] | None = None
        if self.latest_image_only and isinstance(req_json, dict):
            changed, removed_count, latest_idx = prune_older_image_parts(req_json)
            if changed:
                request_body = json.dumps(req_json, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                req_text = request_body.decode("utf-8", errors="replace")
                request_rewrite = {
                    "latest_image_only": True,
                    "removed_image_parts": removed_count,
                    "latest_user_image_message_index": latest_idx,
                }

        req_summary = summarize_request(req_json)
        upstream_url = urljoin(self.upstream_base.rstrip("/") + "/", self.path.lstrip("/"))
        rendered_prompt: str | None = None
        rendered_prompt_error: str | None = None

        if self.chat_template_renderer and isinstance(req_json, dict):
            try:
                normalized_req_json = normalize_payload_for_template(req_json)
                context = {
                    "messages": normalized_req_json.get("messages", []),
                    "tools": normalized_req_json.get("tools", []),
                    "system_prompt": normalized_req_json.get("system_prompt"),
                    "add_generation_prompt": normalized_req_json.get("add_generation_prompt", True),
                    "bos_token": normalized_req_json.get("bos_token", ""),
                    "eos_token": normalized_req_json.get("eos_token", ""),
                    "enable_thinking": normalized_req_json.get("enable_thinking"),
                    "model": normalized_req_json.get("model"),
                }
                rendered_prompt = self.chat_template_renderer.render(**context)
                if len(rendered_prompt) > self.chat_template_max_chars:
                    rendered_prompt = rendered_prompt[: self.chat_template_max_chars] + "\n<truncated>"
            except Exception as e:
                rendered_prompt_error = f"TemplateRenderError: {e}"
        elif self.chat_template_path and self.chat_template_error:
            rendered_prompt_error = self.chat_template_error

        request_text_log = req_text
        if (
            self.max_log_bytes > 0
            and request_text_log is not None
            and len(request_text_log.encode("utf-8", errors="ignore")) > self.max_log_bytes
        ):
            request_text_log = request_text_log[: self.max_log_bytes] + "\n<truncated>"

        # Immediate event so you can see the request while upstream is still processing.
        request_start_ts = utc_now()
        self._write_log(
            {
                "event": "request_start",
                "ts": request_start_ts,
                "request_id": request_id,
                "pid": os.getpid(),
                "client": self.client_address[0],
                "method": self.command,
                "path": self.path,
                "upstream_url": upstream_url,
                "request_headers": redact_headers({k: v for k, v in self.headers.items()}),
                "request_summary": req_summary,
                "request_text": request_text_log,
                "rendered_prompt": rendered_prompt,
                "rendered_prompt_error": rendered_prompt_error,
                "request_rewrite": request_rewrite,
            }
        )

        self._write_framed_log(
            self.raw_request_log_path,
            request_start_ts,
            request_id,
            "RAW_REQUEST",
            request_text_log,
        )
        if self.chat_template_path and rendered_prompt is not None:
            self._write_framed_log(
                self.rendered_prompt_log_path,
                request_start_ts,
                request_id,
                "RENDERED_PROMPT",
                rendered_prompt,
            )
        elif self.chat_template_path and rendered_prompt_error:
            self._write_framed_log(
                self.rendered_prompt_log_path,
                request_start_ts,
                request_id,
                "TEMPLATE_ERROR",
                rendered_prompt_error,
            )

        fwd_headers: dict[str, str] = {}
        for k, v in self.headers.items():
            lk = k.lower()
            if lk in {"host", "content-length", "connection", "accept-encoding"}:
                continue
            fwd_headers[k] = v

        req = Request(
            upstream_url,
            data=request_body if request_body else None,
            headers=fwd_headers,
            method=self.command,
        )

        status = 502
        resp_headers: dict[str, str] = {}
        error_text: str | None = None
        client_disconnected = False
        resp_capture = bytearray()
        resp_truncated = False

        def _capture_chunk(chunk: bytes) -> None:
            nonlocal resp_truncated
            if resp_truncated:
                return
            if self.max_log_bytes <= 0:
                resp_capture.extend(chunk)
                return
            budget = self.max_log_bytes - len(resp_capture)
            if budget <= 0:
                resp_truncated = True
                return
            if len(chunk) <= budget:
                resp_capture.extend(chunk)
                return
            resp_capture.extend(chunk[:budget])
            resp_truncated = True

        try:
            with self.upstream_opener.open(req, timeout=self.timeout_sec) as resp:
                status = int(resp.status)
                resp_headers = dict(resp.headers.items())

                self.send_response(status)
                for k, v in resp_headers.items():
                    lk = k.lower()
                    if lk in {"transfer-encoding", "content-length", "connection"}:
                        continue
                    self.send_header(k, v)
                self.send_header("Connection", "close")
                self.end_headers()

                while True:
                    chunk = resp.read(self.stream_chunk_size)
                    if not chunk:
                        break
                    _capture_chunk(chunk)
                    try:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        client_disconnected = True
                        error_text = (error_text + " | " if error_text else "") + "ClientDisconnected"
                        break

        except HTTPError as e:
            status = int(e.code)
            resp_headers = dict(e.headers.items()) if e.headers else {}
            error_body = e.read() if hasattr(e, "read") else b""
            _capture_chunk(error_body)
            error_text = f"HTTPError {e.code}"
            try:
                self.send_response(status)
                for k, v in resp_headers.items():
                    lk = k.lower()
                    if lk in {"transfer-encoding", "content-length", "connection"}:
                        continue
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(error_body)))
                self.send_header("Connection", "close")
                self.end_headers()
                if error_body:
                    self.wfile.write(error_body)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                client_disconnected = True
                error_text = (error_text + " | " if error_text else "") + "ClientDisconnected"

        except URLError as e:
            status = 502
            error_text = f"URLError: {e}"
            error_body = str(e).encode("utf-8", errors="replace")
            _capture_chunk(error_body)
            try:
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(error_body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(error_body)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                client_disconnected = True
                error_text = (error_text + " | " if error_text else "") + "ClientDisconnected"

        except Exception as e:
            status = 500
            error_text = f"ProxyException: {e}"
            error_body = str(e).encode("utf-8", errors="replace")
            _capture_chunk(error_body)
            try:
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(error_body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(error_body)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                client_disconnected = True
                error_text = (error_text + " | " if error_text else "") + "ClientDisconnected"

        resp_body = bytes(resp_capture)
        resp_text, resp_json = decode_body(resp_body)
        response_stats = extract_response_stats(resp_json)
        if resp_truncated and resp_text is not None:
            resp_text = resp_text + "\n<truncated>"
            resp_json = None
            response_stats = None

        response_end_ts = utc_now()
        self._write_framed_log(
            self.raw_response_log_path,
            request_start_ts,
            request_id,
            f"RAW_RESPONSE status={status}",
            resp_text,
            ts_end=response_end_ts,
        )

        self._write_log(
            {
                "event": "request_end",
                "ts": response_end_ts,
                "duration_ms": int((time.time() - started) * 1000),
                "request_id": request_id,
                "pid": os.getpid(),
                "client": self.client_address[0],
                "method": self.command,
                "path": self.path,
                "upstream_url": upstream_url,
                "request_summary": req_summary,
                "request_rewrite": request_rewrite,
                "response_status": status,
                "response_headers": redact_headers(resp_headers),
                "response_stats": response_stats,
                "response_text": resp_text,
                "response_json": resp_json,
                "error": error_text,
                "client_disconnected": client_disconnected,
            }
        )

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()

    def do_PATCH(self) -> None:
        self._proxy()

    def do_DELETE(self) -> None:
        self._proxy()

    def do_OPTIONS(self) -> None:
        self._proxy()


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def normalize_upstream(raw: str) -> tuple[str, int]:
    value = (raw or "").strip()
    if not value:
        raise ValueError("upstream is required")

    if "://" not in value:
        value = f"http://{value}"

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("upstream scheme must be http or https")
    if not parsed.hostname or parsed.port is None:
        raise ValueError("upstream must include host:port")
    if parsed.query or parsed.fragment:
        raise ValueError("upstream must not include query/fragment")

    path = parsed.path.rstrip("/")
    normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
    return normalized, int(parsed.port)


def parse_args() -> argparse.Namespace:
    default_log_dir = os.path.expanduser("~/.llm-ops/logs")
    p = argparse.ArgumentParser(description="OpenAI-compatible reverse proxy tap")
    p.add_argument("--listen-host", default="127.0.0.1")
    p.add_argument("--listen-port", "--port", dest="listen_port", type=int, help="Listen port (default: upstream port)")
    p.add_argument("--upstream", help="Upstream host:port or URL, e.g. <upstream-host>:<upstream-port>")
    p.add_argument(
        "-i",
        "--render-input",
        dest="render_input",
        help="Render one JSON payload or a list of payloads from a file without starting the proxy. Use '-' to read from stdin.",
    )
    p.add_argument("--log", default=f"{default_log_dir}/model-proxy.ndjson", help="NDJSON log file path")
    p.add_argument("--timeout", type=float, default=900.0)
    p.add_argument("--max-log-bytes", type=int, default=0, help="Per-request capture cap in bytes; 0 means unlimited")
    p.add_argument("--stream-chunk-size", type=int, default=65536)
    p.add_argument("--chat-template", help="Optional Jinja chat template path to render/log final prompt text.")
    p.add_argument("--chat-template-max-chars", type=int, default=200000)
    p.add_argument("--raw-log", help="Optional combined plain-text framed log path (request + response in sequence).")
    p.add_argument("--raw-request-log", help="Optional plain-text framed log path for raw request_text per request_start")
    p.add_argument("--rendered-prompt-log", default=f"{default_log_dir}/model-proxy.rendered.log", help="Optional plain-text framed log path for rendered_prompt per request_start")
    p.add_argument("--raw-response-log", help="Optional plain-text framed log path for response body per request_end")
    p.add_argument(
        "--log-rotate-seconds",
        type=int,
        default=int(os.environ.get("MODEL_PROXY_LOG_ROTATE_SECONDS", "86400")),
        help="Rotate active proxy logs after this many seconds; 0 disables time-based rotation",
    )
    p.add_argument(
        "--log-rotate-keep",
        type=int,
        default=int(os.environ.get("MODEL_PROXY_LOG_ROTATE_KEEP", "5")),
        help="Number of rotated .N.log files to keep per active proxy log",
    )
    p.set_defaults(log_fsync=True)
    p.add_argument("--log-fsync", dest="log_fsync", action="store_true", help="Force fsync after each log line write (default: on)")
    p.add_argument("--no-log-fsync", dest="log_fsync", action="store_false", help="Disable fsync after each log line write")
    p.add_argument(
        "--latest-image-only",
        action="store_true",
        default=True,
        help="Keep image_url parts only on the latest user message that contains one.",
    )
    p.add_argument(
        "--no-latest-image-only",
        dest="latest_image_only",
        action="store_false",
        help="Disable latest-image-only filtering.",
    )
    return p.parse_args()


def main() -> int:
    default_log_dir = os.path.expanduser("~/.llm-ops/logs")
    args = parse_args()
    if args.render_input:
        return render_input_payloads(args)
    if not args.upstream:
        raise SystemExit("--upstream is required unless --render-input is used")
    try:
        upstream_base, upstream_port = normalize_upstream(args.upstream)
    except ValueError as e:
        raise SystemExit(f"Invalid --upstream: {e}")
    listen_port = int(args.listen_port) if args.listen_port is not None else upstream_port

    ProxyTapHandler.upstream_base = upstream_base
    ProxyTapHandler.log_path = Path(os.path.expanduser(args.log))
    ProxyTapHandler.max_log_bytes = int(args.max_log_bytes)
    ProxyTapHandler.timeout_sec = float(args.timeout)
    ProxyTapHandler.latest_image_only = bool(args.latest_image_only)
    ProxyTapHandler.log_fsync = bool(args.log_fsync)
    ProxyTapHandler.log_rotate_seconds = max(0, int(args.log_rotate_seconds))
    ProxyTapHandler.log_rotate_keep = max(0, int(args.log_rotate_keep))
    ProxyTapHandler._log_writers = {}
    ProxyTapHandler.stream_chunk_size = int(args.stream_chunk_size)
    ProxyTapHandler.chat_template_path = args.chat_template
    ProxyTapHandler.chat_template_max_chars = int(args.chat_template_max_chars)
    ProxyTapHandler.chat_template_renderer = None
    ProxyTapHandler.chat_template_error = None
    raw_log_path = Path(os.path.expanduser(args.raw_log)) if args.raw_log else None
    raw_request_log_path = Path(os.path.expanduser(args.raw_request_log)) if args.raw_request_log else None
    raw_response_log_path = Path(os.path.expanduser(args.raw_response_log)) if args.raw_response_log else None

    # Default behavior: keep request/response framed logs together in one sequential file.
    if raw_request_log_path is None and raw_response_log_path is None and raw_log_path is None:
        raw_request_log_path = Path(f"{default_log_dir}/model-proxy.raw.log")
        raw_response_log_path = raw_request_log_path
    else:
        if raw_log_path is not None:
            if raw_request_log_path is None:
                raw_request_log_path = raw_log_path
            if raw_response_log_path is None:
                raw_response_log_path = raw_log_path
        if raw_request_log_path is not None and raw_response_log_path is None:
            raw_response_log_path = raw_request_log_path

    ProxyTapHandler.raw_request_log_path = raw_request_log_path
    ProxyTapHandler.rendered_prompt_log_path = Path(os.path.expanduser(args.rendered_prompt_log)) if args.rendered_prompt_log else None
    ProxyTapHandler.raw_response_log_path = raw_response_log_path

    if args.chat_template:
        (
            ProxyTapHandler.chat_template_path,
            ProxyTapHandler.chat_template_renderer,
            ProxyTapHandler.chat_template_error,
        ) = load_chat_template_renderer(args.chat_template)

    server = ThreadingHTTPServer((args.listen_host, listen_port), ProxyTapHandler)
    print(
        f"model-proxy-tap listening on http://{args.listen_host}:{listen_port} "
        f"-> {upstream_base} (threading, log: {ProxyTapHandler.log_path}, raw_log={ProxyTapHandler.raw_request_log_path}, rendered_log={ProxyTapHandler.rendered_prompt_log_path}, raw_response_log={ProxyTapHandler.raw_response_log_path}, latest_image_only={ProxyTapHandler.latest_image_only}, log_fsync={ProxyTapHandler.log_fsync}, log_rotate_seconds={ProxyTapHandler.log_rotate_seconds}, log_rotate_keep={ProxyTapHandler.log_rotate_keep}, stream_chunk_size={ProxyTapHandler.stream_chunk_size}, max_log_bytes={ProxyTapHandler.max_log_bytes}, chat_template={ProxyTapHandler.chat_template_path})",
        flush=True,
    )

    def _shutdown(_signum: int, _frame: Any) -> None:
        try:
            server.shutdown()
        except Exception:
            pass

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
