"""Operator-scoped, allowlisted HTTPX transport diversion; no provider/config mutation.

Installed only in explicitly selected service environments via sitecustomize.
Wraps HTTPX 0.28.1's public transport methods, after SDK auth and request hooks.
The original Request, streaming body, headers and client base URL are retained.
"""

from __future__ import annotations

from functools import wraps
import json
import os
from pathlib import Path
import stat


def load_routes(path: Path) -> list[tuple[str, str]]:
    """Accept only owner-private maps from known HTTPS providers to loopback."""
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("transport map must be an owner-private regular file")
    import httpx
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError("nonempty route map required")
    allowed = {"https://chatgpt.com/backend-api/codex", "https://api.openai.com/v1", "https://openrouter.ai/api/v1"}
    for source, target in raw.items():
        if source not in allowed or not isinstance(target, str):
            raise ValueError("unapproved provider origin/path")
        url = httpx.URL(target)
        if (url.scheme != "http" or url.host != "127.0.0.1" or not url.port
                or url.username or url.password or url.query or url.fragment
                or url.path not in {"/codex", "/openai/v1", "/openrouter/v1"}):
            raise ValueError("fixed loopback tap route required")
    return sorted(raw.items(), key=lambda item: len(item[0]), reverse=True)


def install(path: Path) -> None:
    """Divert only matching physical HTTP attempts, without replay or fallback."""
    import httpx
    if httpx.__version__ != "0.28.1":
        raise RuntimeError("transport shim requires qualified HTTPX 0.28.1")
    if getattr(httpx.HTTPTransport.handle_request, "_model_proxy_map", None):
        if httpx.HTTPTransport.handle_request._model_proxy_map != str(path):
            raise RuntimeError("a different transport map is already installed")
        return
    routes = load_routes(path)

    def routed(request):
        raw = str(request.url)
        for source, target in routes:
            if raw == source or raw.startswith(source + "/") or raw.startswith(source + "?"):
                # Reuse the original byte stream. Do not parse/reserialize, add
                # correlation headers, or change auth/account/identity headers.
                return httpx.Request(request.method, target + raw[len(source):],
                                     headers=request.headers, stream=request.stream,
                                     extensions=request.extensions)
        return request

    sync = httpx.HTTPTransport.handle_request
    asynchronous = httpx.AsyncHTTPTransport.handle_async_request

    @wraps(sync)
    def send(transport, request):
        return sync(transport, routed(request))

    @wraps(asynchronous)
    async def send_async(transport, request):
        return await asynchronous(transport, routed(request))

    send._model_proxy_map = str(path)
    send_async._model_proxy_map = str(path)
    httpx.HTTPTransport.handle_request = send
    httpx.AsyncHTTPTransport.handle_async_request = send_async
