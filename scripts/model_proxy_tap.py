#!/usr/bin/env python
"""Small reverse proxy tap for OpenAI-compatible APIs.

Logs request/response metadata and JSON bodies to NDJSON while proxying traffic.

This module is an internal driver. Operators configure and invoke it through
the ``llmops`` component interface or the managed ``model-proxy`` service.

Then point an OpenAI-compatible client base URL to:
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


CHAT_COMPLETION_PATHS = frozenset(
    {
        "/api/chat",
        "/chat/completions",
        "/v1/chat/completions",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_human_utc_timestamp(value: str) -> str:
    """Render an ISO timestamp consistently for human-readable log frames."""

    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        rendered = parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        return f"{rendered[:-3]} UTC"
    except (TypeError, ValueError):
        return value


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


def _raise_template_exception(message: str) -> None:
    raise jinja2.TemplateError(message)


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
        env.globals["raise_exception"] = _raise_template_exception
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
            if chat_template_max_chars > 0 and len(rendered_prompt) > chat_template_max_chars:
                rendered_prompt = rendered_prompt[:chat_template_max_chars]
        except Exception as e:
            rendered_prompt_error = f"TemplateRenderError: {e}"
    elif chat_template_path and chat_template_error:
        rendered_prompt_error = chat_template_error

    return rendered_prompt, rendered_prompt_error


def classify_chat_render_request(method: str, path: str, payload: Any) -> tuple[bool, str]:
    """Return whether a proxied request is eligible for chat-template diagnostics."""

    request_path = path.split("?", 1)[0]
    if method.upper() != "POST" or request_path not in CHAT_COMPLETION_PATHS:
        return False, "non-chat request"
    if not isinstance(payload, dict):
        return False, "chat request has no JSON object body"
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return False, "chat request has no messages"
    return True, "chat request"


def _response_events(response_text: str | None, response_json: Any) -> tuple[list[dict[str, Any]], str]:
    if isinstance(response_json, dict):
        return [response_json], "json"
    if not response_text:
        return [], "empty"

    events: list[dict[str, Any]] = []
    saw_sse = False
    for line in response_text.splitlines():
        if not line.startswith("data:"):
            continue
        saw_sse = True
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except Exception:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events, "stream" if saw_sse else "text"


def _append_tool_call_fragment(
    tool_calls: dict[int, dict[str, str]],
    fragment: dict[str, Any],
    fallback_index: int,
) -> None:
    index = fragment.get("index", fallback_index)
    if not isinstance(index, int):
        index = fallback_index
    target = tool_calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
    call_id = fragment.get("id")
    if isinstance(call_id, str):
        target["id"] += call_id
    function = fragment.get("function")
    if not isinstance(function, dict):
        function = fragment
    name = function.get("name")
    if isinstance(name, str):
        target["name"] += name
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        target["arguments"] += arguments
    elif arguments is not None:
        target["arguments"] += json.dumps(arguments, ensure_ascii=False)


def _pretty_tool_arguments(arguments: str) -> str:
    try:
        parsed = json.loads(arguments)
    except Exception:
        return arguments
    return json.dumps(parsed, ensure_ascii=False, indent=2)


def format_model_response_for_diagnostics(
    response_text: str | None,
    response_json: Any,
    *,
    transport_complete: bool = True,
) -> str:
    """Render OpenAI JSON or SSE as a compact, human-readable model exchange."""

    events, mode = _response_events(response_text, response_json)
    if not events:
        return response_text or "[empty model response]"

    choices: dict[int, dict[str, Any]] = {}
    usage: dict[str, Any] | None = None
    timings: dict[str, Any] | None = None
    for event in events:
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
        if isinstance(event.get("timings"), dict):
            timings = event["timings"]
        event_choices = event.get("choices")
        if not isinstance(event_choices, list):
            continue
        for fallback_index, choice in enumerate(event_choices):
            if not isinstance(choice, dict):
                continue
            index = choice.get("index", fallback_index)
            if not isinstance(index, int):
                index = fallback_index
            target = choices.setdefault(
                index,
                {"reasoning": [], "content": [], "tool_calls": {}, "finish_reason": None},
            )
            message = choice.get("delta") if isinstance(choice.get("delta"), dict) else choice.get("message")
            if not isinstance(message, dict):
                message = choice
            for key in ("reasoning_content", "reasoning", "analysis"):
                value = message.get(key)
                if isinstance(value, str) and value:
                    target["reasoning"].append(value)
                    break
            content = message.get("content")
            if isinstance(content, str) and content:
                target["content"].append(content)
            elif isinstance(choice.get("text"), str) and choice["text"]:
                target["content"].append(choice["text"])
            fragments = message.get("tool_calls")
            if isinstance(fragments, list):
                for tool_index, fragment in enumerate(fragments):
                    if isinstance(fragment, dict):
                        _append_tool_call_fragment(target["tool_calls"], fragment, tool_index)
            function_call = message.get("function_call")
            if isinstance(function_call, dict):
                _append_tool_call_fragment(target["tool_calls"], function_call, 0)
            finish_reason = choice.get("finish_reason")
            if isinstance(finish_reason, str) and finish_reason:
                target["finish_reason"] = finish_reason

    if not choices:
        return response_text or json.dumps(response_json, ensure_ascii=False, indent=2)

    if not transport_complete:
        boundary = "incomplete transport"
    elif mode == "stream" and response_text and any(
        line.strip() == "data: [DONE]" for line in response_text.splitlines()
    ):
        boundary = "SSE [DONE]"
    else:
        boundary = "HTTP response complete"
    lines = [f"[model response: {mode}]", f"[response boundary: {boundary}]", ""]
    multiple_choices = len(choices) > 1
    for index in sorted(choices):
        choice = choices[index]
        if multiple_choices:
            lines.extend([f"[choice {index}]", ""])
        reasoning = "".join(choice["reasoning"])
        if reasoning:
            lines.extend(
                [
                    "[model reasoning: returned by upstream]",
                    "<think>",
                    reasoning,
                    "</think>",
                    "",
                ]
            )
        content = "".join(choice["content"])
        if content:
            lines.extend([content, ""])
        for tool_index in sorted(choice["tool_calls"]):
            tool_call = choice["tool_calls"][tool_index]
            name = tool_call["name"] or "unknown"
            call_id = f' id="{tool_call["id"]}"' if tool_call["id"] else ""
            lines.append(f'<tool_call name="{name}"{call_id}>')
            if tool_call["arguments"]:
                lines.append(_pretty_tool_arguments(tool_call["arguments"]))
            lines.extend(["</tool_call>", ""])
        if choice["finish_reason"]:
            lines.extend([f'[finish_reason: {choice["finish_reason"]}]', ""])
    if usage is not None:
        lines.extend(["[usage]", json.dumps(usage, ensure_ascii=False, indent=2), ""])
    if timings is not None:
        lines.extend(["[timings]", json.dumps(timings, ensure_ascii=False, indent=2), ""])
    return "\n".join(lines).rstrip()


def format_source_reasoning_for_diagnostics(
    payload: Any,
    rendered_prompt: str | None,
) -> str | None:
    """Describe request-history reasoning without changing the rendered prompt."""

    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        return None

    sections: list[str] = [
        "[source reasoning diagnostic: not sent upstream by this diagnostic]",
        "[the selected chat template controls whether each source appears in the rendered prompt]",
        "",
    ]
    found = False
    for index, message in enumerate(payload["messages"]):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        reasoning = ""
        source = ""
        for key in ("reasoning_content", "reasoning", "analysis"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                reasoning = value.strip()
                source = key
                break
        if not reasoning:
            content = message.get("content")
            if isinstance(content, str) and "<think>" in content and "</think>" in content:
                reasoning = content.split("<think>", 1)[1].split("</think>", 1)[0].strip()
                source = "content:<think>"
        if not reasoning:
            continue
        found = True
        visibility = (
            "present" if rendered_prompt is not None and reasoning in rendered_prompt else "omitted"
        )
        sections.extend(
            [
                f"[assistant message {index}; source={source}; rendered_prompt={visibility}]",
                reasoning,
                "",
            ]
        )
    return "\n".join(sections).rstrip() if found else None


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
    default_log_dir = os.path.expanduser("~/.local/state/llm-ops/logs")
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
            if args.show_source_reasoning:
                source_reasoning = format_source_reasoning_for_diagnostics(
                    payload,
                    rendered_prompt,
                )
                if source_reasoning:
                    helper._write_framed_log(
                        rendered_prompt_log_path,
                        ts,
                        request_id,
                        f"SOURCE_REASONING_DIAGNOSTIC request_id={request_id}",
                        source_reasoning,
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
    timeout_sec: float = 120.0
    log_fsync: bool = True
    stream_chunk_size: int = 65536
    chat_template_path: str | None = None
    chat_template_max_chars: int = 200000
    chat_template_renderer: Any = None
    chat_template_error: str | None = None
    raw_request_log_path: Path | None = None
    rendered_prompt_log_path: Path | None = None
    raw_response_log_path: Path | None = None
    show_source_reasoning: bool = False
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
            f"=== {label} START {format_human_utc_timestamp(ts_start)} ===\n",
            text,
        ]
        if not text.endswith("\n"):
            payload.append("\n")
        payload.append(
            f"=== {label} END {format_human_utc_timestamp(end_ts)} ===\n\n"
        )
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

        req_summary = summarize_request(req_json)
        upstream_url = urljoin(self.upstream_base.rstrip("/") + "/", self.path.lstrip("/"))
        rendered_prompt: str | None = None
        rendered_prompt_error: str | None = None
        source_reasoning: str | None = None

        render_eligible, render_reason = classify_chat_render_request(
            self.command,
            self.path,
            req_json,
        )
        if render_eligible:
            rendered_prompt, rendered_prompt_error = render_prompt_from_payload(
                req_json,
                chat_template_renderer=self.chat_template_renderer,
                chat_template_path=self.chat_template_path,
                chat_template_error=self.chat_template_error,
                chat_template_max_chars=self.chat_template_max_chars,
            )
            if self.show_source_reasoning and rendered_prompt is not None:
                source_reasoning = format_source_reasoning_for_diagnostics(
                    req_json,
                    rendered_prompt,
                )

        request_text_log = req_text

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
            }
        )

        self._write_framed_log(
            self.raw_request_log_path,
            request_start_ts,
            request_id,
            "RAW_REQUEST",
            request_text_log,
        )
        if self.chat_template_path and rendered_prompt_error:
            self._write_framed_log(
                self.rendered_prompt_log_path,
                request_start_ts,
                request_id,
                "TEMPLATE_ERROR",
                rendered_prompt_error,
            )
        elif self.chat_template_path and render_eligible:
            request_parts = [
                "[rendered prompt: exact template output]",
                rendered_prompt or "[rendered prompt unavailable]",
            ]
            if source_reasoning:
                request_parts.extend(["", source_reasoning])
            self._write_framed_log(
                self.rendered_prompt_log_path,
                request_start_ts,
                request_id,
                f"MODEL_EXCHANGE_REQUEST request_id={request_id}",
                "\n".join(request_parts),
            )
        elif self.chat_template_path and request_body and not render_eligible:
            self._write_framed_log(
                self.rendered_prompt_log_path,
                request_start_ts,
                request_id,
                f"RENDER_SKIPPED method={self.command} path={self.path}",
                render_reason,
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
        upstream_eof = False
        resp_capture = bytearray()

        def _capture_chunk(chunk: bytes) -> None:
            resp_capture.extend(chunk)

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
                        upstream_eof = True
                        break
                    _capture_chunk(chunk)
                    try:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        client_disconnected = True
                        error_text = (error_text + " | " if error_text else "") + "ClientDisconnected"
                        break

        except (BrokenPipeError, ConnectionResetError):
            # The client may cancel while the upstream is still preparing its
            # response. Treat a failed header write like a failed body write:
            # close the upstream response and record cancellation, not a proxy
            # or model failure.
            client_disconnected = True
            error_text = "ClientDisconnected"

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

        response_end_ts = utc_now()
        self._write_framed_log(
            self.raw_response_log_path,
            request_start_ts,
            request_id,
            f"RAW_RESPONSE status={status}",
            resp_text,
            ts_end=response_end_ts,
        )
        if self.chat_template_path and render_eligible:
            diagnostic_response = format_model_response_for_diagnostics(
                resp_text,
                resp_json,
                transport_complete=upstream_eof and not client_disconnected,
            )
            if client_disconnected:
                diagnostic_response += "\n\n[client disconnected; upstream response abandoned]"
            self._write_framed_log(
                self.rendered_prompt_log_path,
                request_start_ts,
                request_id,
                f"MODEL_EXCHANGE_RESPONSE request_id={request_id} status={status}",
                "\n".join(["[upstream model response]", diagnostic_response]),
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
    default_log_dir = os.path.expanduser("~/.local/state/llm-ops/logs")
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
    p.add_argument("--stream-chunk-size", type=int, default=65536)
    p.add_argument("--chat-template", help="Optional Jinja chat template path to render/log final prompt text.")
    p.add_argument("--chat-template-max-chars", type=int, default=0, help="Optional rendered-log character cap; 0 means unlimited.")
    p.add_argument("--raw-log", help="Optional combined plain-text framed log path (request + response in sequence).")
    p.add_argument("--raw-request-log", help="Optional plain-text framed log path for raw request_text per request_start")
    p.add_argument("--rendered-prompt-log", default=f"{default_log_dir}/model-proxy.rendered.log", help="Optional plain-text framed log path for rendered_prompt per request_start")
    p.add_argument("--raw-response-log", help="Optional plain-text framed log path for response body per request_end")
    p.add_argument(
        "-t",
        "--show-reasoning",
        "--show-source-reasoning",
        dest="show_source_reasoning",
        action="store_true",
        help="Log assistant reasoning from request history in a separate diagnostic-only frame",
    )
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
    return p.parse_args()


def main() -> int:
    default_log_dir = os.path.expanduser("~/.local/state/llm-ops/logs")
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
    ProxyTapHandler.timeout_sec = float(args.timeout)
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
    ProxyTapHandler.show_source_reasoning = bool(args.show_source_reasoning)

    if args.chat_template:
        (
            ProxyTapHandler.chat_template_path,
            ProxyTapHandler.chat_template_renderer,
            ProxyTapHandler.chat_template_error,
        ) = load_chat_template_renderer(args.chat_template)

    server = ThreadingHTTPServer((args.listen_host, listen_port), ProxyTapHandler)
    print(
        f"model-proxy-tap listening on http://{args.listen_host}:{listen_port} "
        f"-> {upstream_base} (threading, log: {ProxyTapHandler.log_path}, raw_log={ProxyTapHandler.raw_request_log_path}, rendered_log={ProxyTapHandler.rendered_prompt_log_path}, raw_response_log={ProxyTapHandler.raw_response_log_path}, log_fsync={ProxyTapHandler.log_fsync}, log_rotate_seconds={ProxyTapHandler.log_rotate_seconds}, log_rotate_keep={ProxyTapHandler.log_rotate_keep}, stream_chunk_size={ProxyTapHandler.stream_chunk_size}, chat_template={ProxyTapHandler.chat_template_path})",
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
