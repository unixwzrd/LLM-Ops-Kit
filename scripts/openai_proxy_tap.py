#!/usr/bin/env python
"""Small reverse proxy tap for OpenAI-compatible APIs.

Logs request/response metadata and JSON bodies to NDJSON while proxying traffic.

Typical use:
  openai-proxy-tap --upstream http://10.0.0.67:11434 --listen-port 18080 \
    --log ~/.openclaw/logs/openai-proxy.ndjson

Then point OpenClaw llamacpp baseUrl to:
  http://127.0.0.1:18080/v1
"""

from __future__ import annotations

import argparse
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
from urllib.request import Request, urlopen

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
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", buffering=1) as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            if self.log_fsync:
                os.fsync(f.fileno())

    def _write_framed_log(self, path: Path | None, ts: str, request_id: str, label: str, body: str | None) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        text = body or ""
        with path.open("a", encoding="utf-8", buffering=1) as f:
            f.write(f"{ts}\t{request_id}\t{label}\n")
            f.write("================ REQUEST START ================\n")
            f.write(text)
            if not text.endswith("\n"):
                f.write("\n")
            f.write("================= REQUEST END =================\n\n")
            f.flush()
            if self.log_fsync:
                os.fsync(f.fileno())

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
                context = {
                    "messages": req_json.get("messages", []),
                    "tools": req_json.get("tools", []),
                    "system_prompt": req_json.get("system_prompt"),
                    "add_generation_prompt": req_json.get("add_generation_prompt", True),
                    "bos_token": req_json.get("bos_token", ""),
                    "eos_token": req_json.get("eos_token", ""),
                    "enable_thinking": req_json.get("enable_thinking"),
                    "model": req_json.get("model"),
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
        if self.chat_template_path:
            self._write_framed_log(
                self.rendered_prompt_log_path,
                request_start_ts,
                request_id,
                "RENDERED_PROMPT",
                rendered_prompt if rendered_prompt is not None else rendered_prompt_error,
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
            with urlopen(req, timeout=self.timeout_sec) as resp:
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
        if resp_truncated and resp_text is not None:
            resp_text = resp_text + "\n<truncated>"
            resp_json = None

        self._write_framed_log(
            self.raw_response_log_path,
            utc_now(),
            request_id,
            f"RAW_RESPONSE status={status}",
            resp_text,
        )

        self._write_log(
            {
                "event": "request_end",
                "ts": utc_now(),
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


class ForkingHTTPServer(socketserver.ForkingMixIn, HTTPServer):
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
    p = argparse.ArgumentParser(description="OpenAI-compatible reverse proxy tap")
    p.add_argument("--listen-host", default="127.0.0.1")
    p.add_argument("--listen-port", "--port", dest="listen_port", type=int, help="Listen port (default: upstream port)")
    p.add_argument("--upstream", required=True, help="Upstream host:port or URL, e.g. 10.0.0.67:11434")
    p.add_argument("--log", default="~/.openclaw/logs/openai-proxy.ndjson", help="NDJSON log file path")
    p.add_argument("--timeout", type=float, default=900.0)
    p.add_argument("--max-log-bytes", type=int, default=0, help="Per-request capture cap in bytes; 0 means unlimited")
    p.add_argument("--stream-chunk-size", type=int, default=65536)
    p.add_argument("--chat-template", help="Optional Jinja chat template path to render/log final prompt text.")
    p.add_argument("--chat-template-max-chars", type=int, default=200000)
    p.add_argument("--raw-request-log", default="~/.openclaw/logs/openai-proxy.requests.log", help="Optional plain-text framed log path for raw request_text per request_start")
    p.add_argument("--rendered-prompt-log", default="~/.openclaw/logs/openai-proxy.rendered.log", help="Optional plain-text framed log path for rendered_prompt per request_start")
    p.add_argument("--raw-response-log", help="Optional plain-text framed log path for response body per request_end")
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
    args = parse_args()
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
    ProxyTapHandler.stream_chunk_size = int(args.stream_chunk_size)
    ProxyTapHandler.chat_template_path = args.chat_template
    ProxyTapHandler.chat_template_max_chars = int(args.chat_template_max_chars)
    ProxyTapHandler.chat_template_renderer = None
    ProxyTapHandler.chat_template_error = None
    ProxyTapHandler.raw_request_log_path = Path(os.path.expanduser(args.raw_request_log)) if args.raw_request_log else None
    ProxyTapHandler.rendered_prompt_log_path = Path(os.path.expanduser(args.rendered_prompt_log)) if args.rendered_prompt_log else None
    ProxyTapHandler.raw_response_log_path = Path(os.path.expanduser(args.raw_response_log)) if args.raw_response_log else None

    if args.chat_template:
        if jinja2 is None:
            ProxyTapHandler.chat_template_error = "jinja2 not available in this Python environment"
        else:
            try:
                template_path = Path(os.path.expanduser(args.chat_template))
                template_text = template_path.read_text(encoding="utf-8")
                env = jinja2.Environment(
                    undefined=jinja2.ChainableUndefined,
                    trim_blocks=False,
                    lstrip_blocks=False,
                    autoescape=False,
                )
                ProxyTapHandler.chat_template_renderer = env.from_string(template_text)
            except Exception as e:
                ProxyTapHandler.chat_template_error = f"TemplateLoadError: {e}"

    server = ForkingHTTPServer((args.listen_host, listen_port), ProxyTapHandler)
    print(
        f"openai-proxy-tap listening on http://{args.listen_host}:{listen_port} "
        f"-> {upstream_base} (forking, log: {ProxyTapHandler.log_path}, raw_log={ProxyTapHandler.raw_request_log_path}, rendered_log={ProxyTapHandler.rendered_prompt_log_path}, raw_response_log={ProxyTapHandler.raw_response_log_path}, latest_image_only={ProxyTapHandler.latest_image_only}, log_fsync={ProxyTapHandler.log_fsync}, stream_chunk_size={ProxyTapHandler.stream_chunk_size}, max_log_bytes={ProxyTapHandler.max_log_bytes}, chat_template={ProxyTapHandler.chat_template_path})",
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
