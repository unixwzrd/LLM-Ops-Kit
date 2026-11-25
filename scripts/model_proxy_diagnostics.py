"""Read-only exchange formatting and atomic diagnostic-template reloads."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import threading
from typing import Any

try:
    import jinja2
except ImportError:  # Raw forwarding and the plain-text report still work.
    jinja2 = None


DEFAULT_REPORT = """[{{ event }} | route={{ route }} | request={{ request_id }}]
[protocol={{ protocol }} | model={{ model }} | template_revision={{ template_revision }}]
{% if correlation %}[client correlation]\n{{ correlation | pretty }}\n{% endif %}
{% if event == 'request' %}{% if previous_response_id %}[server-side history reference: {{ previous_response_id }}; earlier context is not necessarily present here]\n{% endif %}
[instructions]\n{{ instructions | pretty }}
[tool definitions: {{ tools | length }}]\n{{ tools | pretty }}
[conversation / input items: {{ messages | length }}]\n{% for message in messages %}
--- {{ loop.index }}: {{ message.get('role', message.get('type', 'item')) }} ---
{{ message | pretty }}
{% endfor %}
[request settings]\n{{ settings | pretty }}
[sizes: wire_bytes={{ request_bytes }}; instruction_chars={{ instruction_chars }}; tool_definition_chars={{ tool_chars }}; input_chars={{ input_chars }}; counts are not billed tokens]
{% else %}[http_status={{ status }} | transport_complete={{ transport_complete }}]
[provider_response_id={{ provider_response_id }}]\n{{ response_text }}
[usage returned by provider]\n{{ usage | pretty }}
{% endif %}"""


def pretty(value: Any) -> str:
    """Format the diagnostic copy only; avoid megabytes of inline media."""
    def bounded(item: Any) -> Any:
        if isinstance(item, str) and item.startswith("data:") and len(item) > 256:
            return item.split(",", 1)[0] + ",[inline media omitted in readable view; chars=" + str(len(item)) + "]"
        if isinstance(item, dict):
            return {key: bounded(val) for key, val in item.items()}
        if isinstance(item, list):
            return [bounded(val) for val in item]
        return item
    if value is None:
        return "[not supplied]"
    if isinstance(value, str):
        return value
    return json.dumps(bounded(value), ensure_ascii=False, indent=2)


def json_value(value: Any) -> Any:
    """Decode structured JSON for display; never interpret text as a template."""
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            parsed = json.loads(value)
        except (ValueError, RecursionError):
            return value
        if isinstance(parsed, (dict, list)):
            return parsed
    return value


def display_text(value: Any) -> str:
    """Keep actual paragraphs, escaping terminal control characters only."""
    text = value if isinstance(value, str) else str(value)
    return "".join(char if char in "\n\t" or ord(char) >= 32 and ord(char) != 127
                   else "\\x" + format(ord(char), "02x") for char in text)


def readable(value: Any, *, _depth: int = 0) -> str:
    """Indented diagnostic structure with literal multiline values, not JSON escapes.

    This is a reading aid, not a round-trippable serialization. Original body
    text remains in the separate raw-body/NDJSON captures. Opaque reasoning and
    inline media stay labelled instead of dumping unusable base64 into the view.
    """
    if _depth > 40:
        return "[display nesting limit; see raw capture]"
    if isinstance(value, str):
        if value.startswith("data:") and len(value) > 256:
            return value.split(",", 1)[0] + ",[inline media: " + str(len(value)) + " chars; see raw capture]"
        return display_text(value)
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = []
        for key, item in value.items():
            label = display_text(key)
            if key == "encrypted_content" and isinstance(item, str):
                lines.append(label + ": [opaque encrypted content: " + str(len(item)) + " chars; see raw capture]")
                continue
            rendered = readable(item, _depth=_depth + 1)
            if isinstance(item, (dict, list)) and item or "\n" in rendered:
                lines.append(label + ":\n" + "\n".join("  " + line for line in rendered.split("\n")))
            else:
                lines.append(label + ": " + rendered)
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return "[]"
        return "\n".join("- " + readable(item, _depth=_depth + 1).replace("\n", "\n  ") for item in value)
    return json.dumps(value, ensure_ascii=False, default=str)


def request_view(payload: Any, *, path: str) -> dict[str, Any]:
    """Normalize Chat Completions and Responses without inventing hidden context."""
    value = payload if isinstance(payload, dict) else {}
    protocol = "responses" if path.split("?", 1)[0].rstrip("/").endswith("/responses") else "chat_completions" if isinstance(value.get("messages"), list) else "other"
    raw = value.get("input", []) if protocol == "responses" else value.get("messages", [])
    messages = [{"role": "user", "content": raw}] if isinstance(raw, str) else copy.deepcopy(raw) if isinstance(raw, list) else [{"type": "unrecognized_input", "value": raw}]
    instructions = []
    if "instructions" in value:
        instructions.append({"source": "top_level_instructions", "content": value["instructions"]})
    for message in messages:
        if isinstance(message, dict) and message.get("role") in ("system", "developer"):
            instructions.append(message)
    tools = value.get("tools", [])
    tools = copy.deepcopy(tools) if isinstance(tools, list) else []
    settings = {key: copy.deepcopy(val) for key, val in value.items() if key not in {"input", "messages", "instructions", "tools"}}
    return {"protocol": protocol, "model": value.get("model", "[not supplied]"),
            "instructions": instructions, "messages": messages, "tools": tools, "settings": settings,
            "previous_response_id": value.get("previous_response_id"),
            "instruction_chars": len(pretty(instructions)), "tool_chars": len(pretty(tools)), "input_chars": len(pretty(messages))}


def response_view(text: str | None, payload: Any, *, transport_complete: bool) -> dict[str, Any]:
    """Reassemble Responses events, retaining unknown events in the raw capture."""
    events = [payload] if isinstance(payload, dict) else []
    if not events and text:
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    item = json.loads(line[5:])
                except (ValueError, TypeError):
                    continue
                if isinstance(item, dict):
                    events.append(item)
    response = None
    fragments = []
    tool_fragments: dict[str, list[str]] = {}
    usage = None
    complete = False
    for event in events:
        kind = event.get("type", "")
        if event.get("object") == "response":
            response = event
            complete = event.get("status") == "completed"
        if isinstance(event.get("response"), dict):
            response = event["response"]
        if kind == "response.completed":
            complete = True
        if kind == "response.output_text.delta":
            fragments.append(str(event.get("delta", "")))
        if kind == "response.function_call_arguments.delta":
            identifier = str(event.get("item_id", event.get("output_index", "unknown")))
            tool_fragments.setdefault(identifier, []).append(str(event.get("delta", "")))
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
    response = response or {}
    usage = response.get("usage", usage)
    if response.get("output"):
        rendered = pretty(response["output"])
    elif fragments or tool_fragments:
        rendered = "".join(fragments)
        if tool_fragments:
            rendered += "\n[tool argument fragments]\n" + pretty({key: "".join(val) for key, val in tool_fragments.items()})
    else:
        rendered = text or pretty(payload)
    return {"response_text": rendered, "provider_response_id": response.get("id", "[not returned]"),
            "usage": usage, "api_complete": complete, "transport_complete": transport_complete}


class TemplateSnapshot:
    """Immutable references held by one exchange, including its response."""

    def __init__(self, *, chat: Any, report: Any, revision: str, chat_error: str | None = None):
        self.chat = chat
        self.report = report
        self.revision = revision
        self.chat_error = chat_error

    def render_report(self, context: dict[str, Any]) -> str:
        """Render a trusted operator template; never evaluate captured text as Jinja."""
        if self.report is None:
            return pretty(context)
        return self.report.render(**context, template_revision=self.revision)


class ReloadableTemplates:
    """SIGHUP requests a reload; request workers compile and publish atomically."""

    def __init__(self, *, chat_path: str | None, report_path: str | None):
        self.chat_path = chat_path
        self.report_path = report_path
        self.pending = True
        self.lock = threading.RLock()
        self.current = TemplateSnapshot(chat=None, report=None, revision="unloaded")
        self.last_error: str | None = None
        self.reloads = 0

    def request_reload(self, _signum: int = 0, _frame: Any = None) -> None:
        """Signal handler: defer disk I/O, compilation, and locks to a worker."""
        self.pending = True

    def snapshot(self) -> TemplateSnapshot:
        with self.lock:
            if not self.pending:
                return self.current
            self.pending = False
            try:
                chat_text = Path(self.chat_path).expanduser().read_text(encoding="utf-8") if self.chat_path else ""
                report_text = Path(self.report_path).expanduser().read_text(encoding="utf-8") if self.report_path else DEFAULT_REPORT
                chat = report = None
                if jinja2 is None and (self.chat_path or self.report_path):
                    raise RuntimeError("Jinja2 is not available")
                if jinja2 is not None:
                    env = jinja2.Environment(undefined=jinja2.ChainableUndefined, autoescape=False)
                    env.filters["pretty"] = pretty
                    env.filters["json_value"] = json_value
                    env.filters["readable"] = readable
                    env.filters["display_text"] = display_text
                    def raise_exception(message: str) -> None:
                        raise jinja2.TemplateError(message)
                    env.globals["raise_exception"] = raise_exception
                    chat = env.from_string(chat_text) if self.chat_path else None
                    report = env.from_string(report_text)
                revision = hashlib.sha256((chat_text + "\0" + report_text).encode()).hexdigest()[:16]
                self.current = TemplateSnapshot(chat=chat, report=report, revision=revision)
                self.last_error = None
                self.reloads += 1
            except Exception as exc:
                # Keep the previous pair; a broken edit must not break forwarding.
                self.last_error = type(exc).__name__
            return self.current
