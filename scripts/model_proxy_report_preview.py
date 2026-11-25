#!/usr/bin/env python3
"""Render a captured exchange offline, without replaying or contacting a provider.

Accept raw NDJSON records, or a matching request/response pair from the original
JSON-heavy readable template. The latter can recover only fields present in the
pasted reading view; it never claims to reconstruct raw wire bytes or headers.
"""

import argparse
import json
import os
from pathlib import Path
import re

from model_proxy_diagnostics import ReloadableTemplates, request_view, response_view


def json_after(text: str, pattern: str) -> tuple[object, int]:
    """Read one JSON value after an anchored frame heading, not a body substring."""
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise ValueError("missing legacy frame section: " + pattern)
    start = match.end()
    while start < len(text) and text[start].isspace():
        start += 1
    value, length = json.JSONDecoder().raw_decode(text[start:])
    return value, start + length


def legacy_contexts(request_text: str, response_text: str) -> tuple[dict, dict]:
    """Recover normalized presentation contexts from the original report layout."""
    header = re.search(r"^\[request \| route=([^\n|]+) \| request=([^\]\n]+)\]$", request_text, re.MULTILINE)
    if header is None:
        raise ValueError("not an original request report")
    route, identifier = header.groups()
    response_header = re.search(r"^\[response \| route=([^\n|]+) \| request=([^\]\n]+)\]$", response_text, re.MULTILINE)
    if response_header is None or response_header.groups() != (route, identifier):
        raise ValueError("request and response frames do not match")
    meta = re.search(r"^\[protocol=([^|]+) \| model=(.+?) \| template_revision=[^\]]+\]$", request_text, re.MULTILINE)
    if meta is None:
        raise ValueError("missing request metadata")
    protocol, model = meta.groups()
    instructions, _ = json_after(request_text, r"^\[instructions\]\n")
    tools, _ = json_after(request_text, r"^\[tool definitions: \d+\]\n")
    conversation = re.search(r"^\[conversation / input items: (\d+)\]\n", request_text, re.MULTILINE)
    if conversation is None:
        raise ValueError("missing ordered conversation")
    cursor = conversation.end()
    messages = []
    for index in range(int(conversation.group(1))):
        match = re.match(r"\s*--- (\d+): [^\n]+ ---\n", request_text[cursor:])
        if match is None or int(match.group(1)) != index + 1:
            raise ValueError("malformed or unordered input frame")
        start = cursor + match.end()
        while request_text[start].isspace():
            start += 1
        value, length = json.JSONDecoder().raw_decode(request_text[start:])
        messages.append(value)
        cursor = start + length
    settings, _ = json_after(request_text[cursor:], r"^\[request settings\]\n")
    sizes = re.search(r"\[sizes: wire_bytes=(\d+); instruction_chars=(\d+); tool_definition_chars=(\d+); input_chars=(\d+);", request_text)
    if sizes is None:
        raise ValueError("missing original size observations")
    size_values = dict(zip(("request_bytes", "instruction_chars", "tool_chars", "input_chars"), map(int, sizes.groups())))
    correlation = {}
    if re.search(r"^\[client correlation\]$", request_text, re.MULTILINE):
        correlation, _ = json_after(request_text, r"^\[client correlation\]\n")
    common = {"route": route, "request_id": identifier, "model": model.strip(), "correlation": correlation}
    request = {**common, **size_values, "event": "request", "protocol": protocol.strip(),
               "instructions": instructions, "tools": tools, "messages": messages, "settings": settings,
               "previous_response_id": settings.get("previous_response_id")}
    status = re.search(r"^\[http_status=(\d+) \| transport_complete=(True|False)\]$", response_text, re.MULTILINE)
    response_id = re.search(r"^\[provider_response_id=([^\]]+)\]\n", response_text, re.MULTILINE)
    usage, _ = json_after(response_text, r"^\[usage returned by provider\]\n")
    if status is None or response_id is None:
        raise ValueError("missing response status/id")
    body = response_text[response_id.end():re.search(r"^\[usage returned by provider\]$", response_text, re.MULTILINE).start()].strip()
    response = {**common, "event": "response", "protocol": protocol.strip(), "status": int(status.group(1)),
                "transport_complete": status.group(2) == "True", "provider_response_id": response_id.group(1),
                "response_text": body, "usage": usage}
    return request, response


def ndjson_contexts(path: Path, identifier: str) -> tuple[dict, dict]:
    """Select exactly one pair from an existing full-diagnostic capture."""
    selected = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if record.get("request_id") == identifier:
                selected.append(record)
    starts = [record for record in selected if record.get("event") == "request_start"]
    ends = [record for record in selected if record.get("event") == "request_end"]
    if len(starts) != 1 or len(ends) != 1:
        raise ValueError("exactly one captured start and end are required")
    start, end = starts[0], ends[0]
    body = json.loads(start["request_text"])
    common = {"route": start.get("route", "captured"), "request_id": identifier,
              "correlation": start.get("correlation", {}), "model": body.get("model", "[not supplied]")}
    # The route-local URL is enough for normalization; source identity is never
    # rewritten into a replay or sent to any client.
    view = request_view(body, path=start["path"])
    request = {**view, **common, "event": "request", "request_bytes": start.get("request_bytes", 0)}
    response = {**response_view(end.get("response_text"), end.get("response_json"),
                               transport_complete=not end.get("error") and not end.get("client_disconnected")),
                **common, "event": "response", "protocol": view["protocol"], "status": end.get("response_status")}
    return request, response


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-frame", type=Path)
    parser.add_argument("--response-frame", type=Path)
    parser.add_argument("--ndjson", type=Path)
    parser.add_argument("--request-id")
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New owner-private directory; never overwrites")
    args = parser.parse_args()
    os.umask(0o077)
    if args.ndjson and args.request_id and not (args.request_frame or args.response_frame):
        contexts = ndjson_contexts(args.ndjson, args.request_id)
        source = "existing NDJSON diagnostic capture"
    elif args.request_frame and args.response_frame and not (args.ndjson or args.request_id):
        contexts = legacy_contexts(args.request_frame.read_text(encoding="utf-8"), args.response_frame.read_text(encoding="utf-8"))
        source = "pasted original readable frames, not raw wire bytes"
    else:
        parser.error("select --ndjson/--request-id or --request-frame/--response-frame")
    templates = ReloadableTemplates(chat_path=None, report_path=str(args.template))
    snapshot = templates.snapshot()
    if templates.last_error:
        raise ValueError("template compilation failed: " + templates.last_error)
    # Render both before creating a success package. Captured text is never
    # compiled as Jinja and no provider SDK or network module is involved.
    rendered = [snapshot.render_report(context) for context in contexts]
    args.output.mkdir(mode=0o700)
    for name, content in zip(("request.txt", "response.txt"), rendered):
        with (args.output / name).open("x", encoding="utf-8") as stream:
            stream.write(content)
    with (args.output / "preview.json").open("x", encoding="utf-8") as stream:
        json.dump({"request_id": contexts[0]["request_id"], "source": source,
                   "template_revision": snapshot.revision, "network_calls": 0,
                   "input_items": len(contexts[0]["messages"]), "tool_definitions": len(contexts[0]["tools"])}, stream, indent=2)
    print("Offline preview written: " + str(args.output) + "; no request replayed")


if __name__ == "__main__":
    main()
