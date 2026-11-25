"""Service-scoped bootstrap, deployed as sitecustomize.py in a private directory."""

import os
import json
from pathlib import Path
import sys

# Do not instrument arbitrary Python subprocesses inheriting the environment.
# sys.orig_argv is available on all qualified service runtimes (3.14).
original = getattr(sys, "orig_argv", [])
modules = {"hermes_cli.main", "hermes_cli.stderr_timestamp"}
selected = any(original[index] == "-m" and original[index + 1] in modules
               for index in range(len(original) - 1))
if selected and os.environ.get("MODEL_PROXY_TRANSPORT_MAP"):
    try:
        from model_proxy_httpx import install
        install(Path(os.environ["MODEL_PROXY_TRANSPORT_MAP"]))
        receipt = Path(os.environ["MODEL_PROXY_TRANSPORT_MAP"]).parent / "bootstrap-events.ndjson"
        with os.fdopen(os.open(receipt, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600), "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"pid": os.getpid(), "httpx": "0.28.1", "installed": True}) + "\n")
    except Exception as error:
        # Python otherwise silently ignores sitecustomize errors. Never claim
        # capture is active while quietly bypassing it after runtime drift.
        sys.stderr.write("model-proxy bootstrap refused: " + type(error).__name__ + "\n")
        sys.stderr.flush()
        os._exit(78)
