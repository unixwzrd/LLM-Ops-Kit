"""Offline qualification of native-provider transport diversion."""

import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

try:
    import httpx
except ImportError:
    httpx = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_proxy_httpx import install, load_routes
from model_proxy_tap import decode_body


@unittest.skipIf(httpx is None, "optional client integration requires HTTPX")
class TransportTests(unittest.TestCase):
    @contextmanager
    def fixture(self):
        records = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                records.append((self.path, dict(self.headers), self.rfile.read(int(self.headers["Content-Length"])) ))
                body = b'data: {"type":"response.completed"}\n\n'
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                route = Path(folder) / "routes.json"
                route.write_text(json.dumps({"https://chatgpt.com/backend-api/codex": f"http://127.0.0.1:{server.server_port}/codex"}))
                route.chmod(0o600)
                with patch.object(httpx.HTTPTransport, "handle_request", httpx.HTTPTransport.handle_request), patch.object(httpx.AsyncHTTPTransport, "handle_async_request", httpx.AsyncHTTPTransport.handle_async_request):
                    install(route)
                    yield route, records
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)

    def test_native_identity_body_and_stream_survive_without_url_mutation(self):
        with self.fixture() as (route, records):
            body = b'fixture-already-compressed-wire-body'
            def compression_hook(request):
                request.stream = httpx.ByteStream(body)
                request.headers["Content-Length"] = str(len(body))
                request.headers["Content-Encoding"] = "zstd"
            with httpx.Client(base_url="https://chatgpt.com/backend-api/codex", trust_env=False,
                              event_hooks={"request": [compression_hook]}) as client:
                with client.stream("POST", "/responses?fixture=1", content=b'original-json', headers={
                    "Authorization": "Bearer TEST", "ChatGPT-Account-ID": "TEST-ACCOUNT",
                    "originator": "hermes-agent", "User-Agent": "HermesAgent/test"}) as response:
                    self.assertEqual(response.read(), b'data: {"type":"response.completed"}\n\n')
                    self.assertEqual(str(response.request.url), "https://chatgpt.com/backend-api/codex/responses?fixture=1")
                self.assertEqual(str(client.base_url), "https://chatgpt.com/backend-api/codex/")
            self.assertEqual(records[0][0], "/codex/responses?fixture=1")
            self.assertEqual(records[0][2], body)
            for name, value in {"Authorization": "Bearer TEST", "ChatGPT-Account-ID": "TEST-ACCOUNT", "originator": "hermes-agent", "Content-Encoding": "zstd"}.items():
                self.assertEqual(records[0][1][name], value)
            install(route)  # idempotent

    def test_async_native_requests_are_diverted(self):
        with self.fixture() as (_, records):
            async def call():
                async with httpx.AsyncClient(trust_env=False) as client:
                    return await client.post("https://chatgpt.com/backend-api/codex/responses", content=b'async-body')
            self.assertEqual(asyncio.run(call()).status_code, 200)
            self.assertEqual(records[0][2], b'async-body')

    def test_other_paths_and_hosts_use_original_transport(self):
        seen = []
        def original(transport, request):
            seen.append(str(request.url))
            return httpx.Response(200, content=b'fixture')
        with patch.object(httpx.HTTPTransport, "handle_request", original):
            with self.fixture():
                with httpx.Client(trust_env=False) as client:
                    for url in ("https://chatgpt.com/backend-api/codex-not/responses", "https://chatgpt.com.evil.test/backend-api/codex/responses", "https://auth.openai.com/oauth/token"):
                        client.get(url)
                        self.assertEqual(seen[-1], url)

    def test_insecure_maps_refused(self):
        with self.fixture() as (route, _):
            route.chmod(0o644)
            with self.assertRaises(ValueError):
                load_routes(route)
            route.chmod(0o600)
            route.write_text(json.dumps({"https://evil.test": "http://127.0.0.1:123/codex"}))
            with self.assertRaises(ValueError):
                load_routes(route)
            route.unlink()
            route.symlink_to("/dev/null")
            with self.assertRaises(ValueError):
                load_routes(route)

    def test_unsupported_decoder_does_not_misrepresent_garbage_as_prompt(self):
        text, payload = decode_body(b'compressed', encoding="zstd")
        self.assertIsNone(payload)
        self.assertIn("wire body forwarded unchanged", text)

    @unittest.skipUnless(sys.version_info >= (3, 14), "stdlib zstd requires qualified service Python")
    def test_zstd_readable_copy_keeps_wire_input_intact(self):
        from compression import zstd
        original = b'{"model":"fixture","input":"compressed prompt"}'
        wire = zstd.compress(original)
        text, payload = decode_body(wire, encoding="zstd", decoder_python=sys.executable)
        self.assertEqual(text.encode(), original)
        self.assertEqual(payload["input"], "compressed prompt")
        self.assertEqual(zstd.decompress(wire), original)


if __name__ == "__main__":
    unittest.main()
