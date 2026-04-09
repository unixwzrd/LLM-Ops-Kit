#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen


def warn(msg: str) -> None:
    print(f"modelctl add: warning: {msg}", file=sys.stderr)


def detect_gguf_tool() -> Optional[str]:
    for tool in ("gguf_dump", "llama-gguf"):
        if shutil_which(tool):
            return tool
    return None


def shutil_which(cmd: str) -> Optional[str]:
    for path in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(path) / cmd
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def gguf_metadata(tool: str, model_path: str) -> str:
    if tool.endswith("gguf_dump"):
        cmd = [tool, "--metadata", model_path]
        output = run_cmd(cmd)
        if not output:
            output = run_cmd([tool, model_path])
        return output
    cmd = [tool, "info", model_path]
    output = run_cmd(cmd)
    if not output:
        output = run_cmd([tool, model_path])
    return output


def extract_ctx(text: str) -> Optional[str]:
    patterns = [
        r"n_ctx_train\s*[:=]\s*(\d+)",
        r"context_length\s*[:=]\s*(\d+)",
        r"n_ctx\s*[:=]\s*(\d+)",
    ]
    for pat in patterns:
        match = re.search(pat, text)
        if match:
            return match.group(1)
    return None


def run_cmd(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return ""
    return res.stdout.strip()


def fetch_model_id(upstream: str) -> str:
    url = f"{upstream.rstrip('/')}/v1/models"
    try:
        with urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (URLError, json.JSONDecodeError):
        return ""
    models = data.get("data") or []
    if not models:
        return ""
    return models[0].get("id", "") or ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register a model in OpenClaw models.json")
    parser.add_argument("--model", dest="model_path", default="")
    parser.add_argument("--id", dest="model_id", default="")
    parser.add_argument("--name", dest="model_name", default="")
    parser.add_argument("--provider", default="llama_cpp")
    parser.add_argument("--ctx", dest="ctx", default="")
    parser.add_argument("--max-tokens", dest="max_tokens", default="")
    parser.add_argument("--reasoning", default="true")
    parser.add_argument("--input", dest="input_list", default="text")
    parser.add_argument("--models-json", dest="models_json", default=os.environ.get("OPENCLAW_MODELS_JSON", ""))
    parser.add_argument("--upstream", dest="upstream", default="")
    return parser.parse_args()


def normalize_bool(val: str) -> bool:
    return str(val).strip().lower() in ("1", "true", "yes", "y", "on")


def main() -> int:
    args = parse_args()
    model_path = args.model_path
    model_id = args.model_id
    model_name = args.model_name
    provider = args.provider
    ctx = args.ctx
    max_tokens = args.max_tokens
    reasoning = normalize_bool(args.reasoning)
    input_list = [v.strip() for v in args.input_list.split(",") if v.strip()]
    models_json = args.models_json or os.path.expanduser("~/.openclaw/agents/main/agent/models.json")

    if not model_id and model_path:
        model_id = Path(model_path).name
    if not model_name and model_id:
        model_name = f"{model_id} (llama.cpp)"

    upstream = args.upstream
    if not upstream:
        host = os.environ.get("LLMOPS_UPSTREAM_HOST")
        port = os.environ.get("LLMOPS_UPSTREAM_PORT", "11434")
        upstream = f"http://{host}:{port}" if host else "http://127.0.0.1:11434"

    if not model_id:
        model_id = fetch_model_id(upstream)

    if not model_id:
        print("modelctl add: unable to determine model id (supply --id or --model)", file=sys.stderr)
        return 2

    if not ctx and model_path:
        tool = detect_gguf_tool()
        if tool:
            meta = gguf_metadata(tool, model_path)
            ctx = extract_ctx(meta) or ""
            if not ctx:
                warn("gguf tool found but context length not detected")
        else:
            warn("gguf tool not found; skipping metadata extraction")

    if not ctx:
        ctx = "8192"
        warn(f"context length not set, defaulting to {ctx}")

    if not max_tokens:
        max_tokens = "8192"

    if not model_name:
        model_name = f"{model_id} (llama.cpp)"

    path = Path(models_json).expanduser()
    if not path.exists():
        print(f"modelctl add: models.json not found: {path}", file=sys.stderr)
        return 2

    data = json.loads(path.read_text())
    providers = data.get("providers", {})
    if provider not in providers:
        print(f"modelctl add: provider not found: {provider}", file=sys.stderr)
        return 2

    entry = {
        "id": model_id,
        "name": model_name,
        "api": "openai-completions",
        "reasoning": reasoning,
        "input": input_list or ["text"],
        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        "contextWindow": int(ctx),
        "maxTokens": int(max_tokens),
    }

    models = providers[provider].get("models", [])
    updated = False
    for idx, model in enumerate(models):
        if model.get("id") == entry["id"]:
            models[idx] = {**model, **entry}
            updated = True
            break
    if not updated:
        models.append(entry)

    providers[provider]["models"] = models
    data["providers"] = providers
    path.write_text(json.dumps(data, indent=2) + "\n")

    print(f"modelctl add: registered {provider}/{model_id}")
    print(f"Next: agentctl exec openclaw models set {provider}/{model_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
