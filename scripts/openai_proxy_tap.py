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
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


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


class ProxyTapHandler(BaseHTTPRequestHandler):
    upstream_base: str = ""
    log_path: Path
    max_log_bytes: int = 200000
    timeout_sec: float = 120.0
    latest_image_only: bool = False
    log_fsync: bool = True

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

    def _proxy(self) -> None:
        started = time.time()
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

        upstream_url = urljoin(self.upstream_base.rstrip("/") + "/", self.path.lstrip("/"))

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
        resp_body = b""
        error_text: str | None = None

        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                status = int(resp.status)
                resp_headers = dict(resp.headers.items())
                resp_body = resp.read()
        except HTTPError as e:
            status = int(e.code)
            resp_headers = dict(e.headers.items()) if e.headers else {}
            resp_body = e.read() if hasattr(e, "read") else b""
            error_text = f"HTTPError {e.code}"
        except URLError as e:
            status = 502
            error_text = f"URLError: {e}"
            resp_body = str(e).encode("utf-8", errors="replace")
        except Exception as e:
            status = 500
            error_text = f"ProxyException: {e}"
            resp_body = str(e).encode("utf-8", errors="replace")

        self.send_response(status)
        for k, v in resp_headers.items():
            lk = k.lower()
            if lk in {"transfer-encoding", "content-length", "connection"}:
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        if resp_body:
            self.wfile.write(resp_body)

        resp_text, resp_json = decode_body(resp_body)
        if req_text is not None and len(req_text.encode("utf-8", errors="ignore")) > self.max_log_bytes:
            req_text = req_text[: self.max_log_bytes] + "\n<truncated>"
            req_json = None
        if resp_text is not None and len(resp_text.encode("utf-8", errors="ignore")) > self.max_log_bytes:
            resp_text = resp_text[: self.max_log_bytes] + "\n<truncated>"
            resp_json = None

        self._write_log(
            {
                "ts": utc_now(),
                "duration_ms": int((time.time() - started) * 1000),
                "client": self.client_address[0],
                "method": self.command,
                "path": self.path,
                "upstream_url": upstream_url,
                "request_headers": redact_headers({k: v for k, v in self.headers.items()}),
                "request_text": req_text,
                "request_json": req_json,
                "request_rewrite": request_rewrite,
                "response_status": status,
                "response_headers": redact_headers(resp_headers),
                "response_text": resp_text,
                "response_json": resp_json,
                "error": error_text,
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpenAI-compatible reverse proxy tap")
    p.add_argument("--listen-host", default="127.0.0.1")
    p.add_argument("--listen-port", type=int, default=18080)
    p.add_argument("--upstream", required=True, help="Upstream base URL, e.g. http://10.0.0.67:11434")
    p.add_argument("--log", required=True, help="NDJSON log file path")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--max-log-bytes", type=int, default=200000)
    p.set_defaults(log_fsync=True)
    p.add_argument("--log-fsync", dest="log_fsync", action="store_true", help="Force fsync after each log line write (default: on)")
    p.add_argument("--no-log-fsync", dest="log_fsync", action="store_false", help="Disable fsync after each log line write")
    p.add_argument(
        "--latest-image-only",
        action="store_true",
        help="Keep image_url parts only on the latest user message that contains one.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    ProxyTapHandler.upstream_base = args.upstream
    ProxyTapHandler.log_path = Path(os.path.expanduser(args.log))
    ProxyTapHandler.max_log_bytes = int(args.max_log_bytes)
    ProxyTapHandler.timeout_sec = float(args.timeout)
    ProxyTapHandler.latest_image_only = bool(args.latest_image_only)
    ProxyTapHandler.log_fsync = bool(args.log_fsync)

    server = ThreadingHTTPServer((args.listen_host, args.listen_port), ProxyTapHandler)
    print(
        f"openai-proxy-tap listening on http://{args.listen_host}:{args.listen_port} "
        f"-> {args.upstream} (log: {ProxyTapHandler.log_path}, latest_image_only={ProxyTapHandler.latest_image_only}, log_fsync={ProxyTapHandler.log_fsync})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
