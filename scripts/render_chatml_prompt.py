#!/usr/bin/env python
"""Render chatml-tools.jinja with a JSON payload for debugging.

Usage:
  render_chatml_prompt.py --input payload.json [--template /path/to/chatml-tools.jinja]

Input JSON schema (minimal):
{
  "system_prompt": "...",
  "tools": [...],
  "messages": [...],
  "add_generation_prompt": true,
  "bos_token": ""
}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DEFAULT_TEMPLATE = "/Volumes/mps/bin/chatml-tools.jinja"


def _tojson(value):
    return json.dumps(value, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to JSON payload")
    parser.add_argument("--template", default=DEFAULT_TEMPLATE, help="Path to Jinja template")
    parser.add_argument("--output", default="-", help="Output file (default: stdout)")
    args = parser.parse_args()

    try:
        from jinja2 import Environment, FileSystemLoader
    except Exception:
        print("ERROR: jinja2 is required. Install with: pip install jinja2", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    template_path = Path(args.template)

    if not input_path.is_file():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return 1
    if not template_path.is_file():
        print(f"ERROR: template not found: {template_path}", file=sys.stderr)
        return 1

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERROR: failed to parse input JSON: {exc}", file=sys.stderr)
        return 1

    if "messages" not in payload or not isinstance(payload["messages"], list):
        print("ERROR: input JSON must include a 'messages' array", file=sys.stderr)
        return 1

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )
    env.filters["tojson"] = _tojson

    template = env.get_template(template_path.name)
    rendered = template.render(
        bos_token=payload.get("bos_token", ""),
        system_prompt=payload.get("system_prompt"),
        tools=payload.get("tools", []),
        messages=payload.get("messages", []),
        add_generation_prompt=payload.get("add_generation_prompt", True),
        enable_thinking=payload.get("enable_thinking", True),
    )

    if args.output == "-":
        sys.stdout.write(rendered)
    else:
        Path(args.output).write_text(rendered, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
