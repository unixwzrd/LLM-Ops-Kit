"""Offline external-API forwarding, readable exchange, and hot-reload tests."""

from __future__ import annotations

from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from model_proxy_diagnostics import ReloadableTemplates, request_view, response_view
from model_proxy_tap import normalize_upstream, redact_headers


class ProxyExternalTests(unittest.TestCase):
    @contextmanager
    def upstream(self, response=b'{"id":"resp_fixture","object":"response","status":"completed","output":[]}', *, status=200, context=None, block=None):
        records = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                records.append((self.path, dict(self.headers), self.rfile.read(int(self.headers["Content-Length"]))))
                if block and b'"hold"' in records[-1][2]:
                    block[0].set()
                    block[1].wait(5)
                self.send_response(status)
                self.send_header("Content-Length", str(len(response)))
                if status == 302:
                    self.send_header("Location", "/do-not-follow")
                self.end_headers()
                self.wfile.write(response)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        if context:
            server.socket = context.wrap_socket(server.socket, server_side=True)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield server.server_address[1], records
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)

    @contextmanager
    def proxy(self, root, upstream, *extra, env=None, startup_delay=0):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        command = [sys.executable, str(SCRIPTS / "model_proxy_tap.py"), "--listen-port", str(port),
                   "--log", str(root / "proxy.ndjson"), "--raw-log", str(root / "raw.log"),
                   "--rendered-prompt-log", str(root / "rendered.log"), "--exchange-log", str(root / "exchange.log"),
                   "--route-name", "fixture"]
        command += ["--upstream", upstream] if upstream else []
        command += list(extra)
        if startup_delay:
            code = 'import os,sys,time; time.sleep(float(sys.argv.pop(1))); os.execv(sys.executable, [sys.executable, *sys.argv[1:]])'
            command = [sys.executable, '-c', code, str(startup_delay), *command[1:]]
        with (root / "stderr.log").open("wb") as errors:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors, env=env)
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        self.fail((root / "stderr.log").read_text())
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=.1):
                            break
                    except OSError:
                        time.sleep(.05)
                else:
                    self.fail("proxy did not listen within 20 seconds; stderr: " + (root / "stderr.log").read_text())
                yield port, process
            finally:
                process.terminate()
                process.wait(5)

    def call(self, port, payload, path="/v1/responses"):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=6)
        try:
            connection.request("POST", path, payload, {"Authorization": "Bearer FIXTURE_SECRET", "Cookie": "FIXTURE_COOKIE",
                                "X-Agent-Session-ID": "fixture-session", "Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_fixture_waits_for_delayed_listener_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.proxy(Path(temporary), 'http://127.0.0.1:1', startup_delay=3) as (port, _):
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                try:
                    connection.request('GET', '/_model_proxy/health')
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    response.read()
                finally:
                    connection.close()

    def wait_log(self, path, marker):
        for _ in range(100):
            if path.exists() and marker in path.read_text():
                return path.read_text()
            time.sleep(.025)
        self.fail("diagnostic not written: " + marker)

    def test_responses_body_auth_and_response_are_preserved(self):
        payload = b'{ "model":"fixture", "instructions":"Keep exact whitespace", "input":"hello \\u2603", "tools":[] }\n'
        response = b'{ "id":"resp_fixture", "object":"response", "status":"completed", "output":[{"type":"message","content":[{"type":"output_text","text":"Hello"}]}], "usage":{"input_tokens":9} }'
        with tempfile.TemporaryDirectory() as temporary, self.upstream(response) as (upstream, records):
            root = Path(temporary)
            with self.proxy(root, f"http://127.0.0.1:{upstream}") as (port, _):
                self.assertEqual(self.call(port, payload), (200, response))
                readable = self.wait_log(root / "exchange.log", "input_tokens")
                self.assertIn("Keep exact whitespace", readable)
                self.assertIn("resp_fixture", readable)
                self.assertIn("fixture-session", readable)
            self.assertEqual(records[0][2], payload)
            self.assertEqual(records[0][1]["Authorization"], "Bearer FIXTURE_SECRET")
            logs = "".join(p.read_text() for p in root.glob("*.log")) + (root / "proxy.ndjson").read_text()
            self.assertNotIn("FIXTURE_SECRET", logs)
            self.assertNotIn("FIXTURE_COOKIE", logs)

    def test_hot_reload_keeps_inflight_revision_and_bad_edit_keeps_good_pair(self):
        entered, release = threading.Event(), threading.Event()
        with tempfile.TemporaryDirectory() as temporary, self.upstream(block=(entered, release)) as (upstream, _):
            root = Path(temporary)
            report = root / "report.jinja"
            report.write_text("OLD {{ event }} {{ request_id }}")
            with self.proxy(root, f"http://127.0.0.1:{upstream}", "--report-template", str(report)) as (port, process):
                results = []
                thread = threading.Thread(target=lambda: results.append(self.call(port, b'{"input":"hold"}')))
                thread.start()
                self.assertTrue(entered.wait(2))
                report.write_text("NEW {{ event }} {{ request_id }}")
                process.send_signal(signal.SIGHUP)
                time.sleep(.05)
                self.assertEqual(self.call(port, b'{"input":"next"}')[0], 200)
                self.wait_log(root / "exchange.log", "NEW response")
                release.set()
                thread.join(3)
                self.assertEqual(results[0][0], 200)
                readable = self.wait_log(root / "exchange.log", "OLD response")
                self.assertIn("OLD request", readable)
                report.write_text("{% broken syntax")
                process.send_signal(signal.SIGHUP)
                time.sleep(.05)
                self.assertEqual(self.call(port, b'{"input":"after-bad-edit"}')[0], 200)
                time.sleep(.05)
                self.assertIn("TemplateSyntaxError", (root / "proxy.ndjson").read_text())
                self.assertIsNone(process.poll())

    def test_provider_routes_strip_only_prefix_and_refuse_unknown_provider(self):
        with tempfile.TemporaryDirectory() as temporary, self.upstream() as (upstream, records):
            root = Path(temporary)
            routes = root / "routes.json"
            routes.write_text(json.dumps({"/openai": f"http://127.0.0.1:{upstream}", "/openrouter": f"http://127.0.0.1:{upstream}/api"}))
            with self.proxy(root, None, "--routes-file", str(routes)) as (port, _):
                self.assertEqual(self.call(port, b'{"input":"hello"}', "/openai/v1/responses")[0], 200)
                self.assertEqual(self.call(port, b'{"messages":[]}', "/openrouter/v1/chat/completions")[0], 200)
                self.assertEqual(self.call(port, b"{}", "/unknown/v1/responses")[0], 404)
            self.assertEqual([r[0] for r in records], ["/v1/responses", "/api/v1/chat/completions"])

    def test_health_is_local_without_upstream_request(self):
        with tempfile.TemporaryDirectory() as temporary, self.upstream() as (upstream, records):
            with self.proxy(Path(temporary), f"http://127.0.0.1:{upstream}") as (port, _):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                connection.request("GET", "/_model_proxy/health")
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                self.assertEqual(response.status, 200)
                self.assertEqual(payload["scope"], "listener-only")
                self.assertEqual(payload["provider_health"], "not-probed")
                self.assertEqual(records, [])

    def test_redirect_is_returned_without_following_it(self):
        with tempfile.TemporaryDirectory() as temporary, self.upstream(b"redirect", status=302) as (upstream, records):
            with self.proxy(Path(temporary), f"http://127.0.0.1:{upstream}") as (port, _):
                self.assertEqual(self.call(port, b"{}"), (302, b"redirect"))
            self.assertEqual(len(records), 1)

    def test_chunked_request_is_explicitly_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, self.upstream() as (upstream, records):
            with self.proxy(Path(temporary), f"http://127.0.0.1:{upstream}") as (port, _):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                connection.request("POST", "/v1/responses", iter([b"fixture"]), encode_chunked=True)
                response = connection.getresponse()
                self.assertEqual(response.status, 501)
                response.read()
                connection.close()
                self.assertEqual(records, [])

    def test_metadata_mode_suppresses_readable_content(self):
        with tempfile.TemporaryDirectory() as temporary, self.upstream() as (upstream, _):
            root = Path(temporary)
            with self.proxy(root, f"http://127.0.0.1:{upstream}", "--log-mode", "metadata") as (port, _):
                self.assertEqual(self.call(port, b'{"input":"PRIVATE_CANARY"}')[0], 200)
                time.sleep(.05)
            self.assertFalse((root / "exchange.log").exists())
            self.assertNotIn("PRIVATE_CANARY", (root / "proxy.ndjson").read_text())

    def test_normalized_inputs_and_sse_response(self):
        original = {"input": [{"type": "function_call_output", "call_id": "call_a", "output": "done"}], "instructions": "Be precise", "previous_response_id": "resp_previous"}
        normalized = request_view(original, path="/v1/responses")
        self.assertEqual(normalized["previous_response_id"], "resp_previous")
        self.assertEqual(normalized["messages"][0]["call_id"], "call_a")
        sse = 'data: {"type":"response.output_text.delta","delta":"hello"}\n\ndata: {"type":"response.completed","response":{"id":"resp_end","usage":{"input_tokens":7}}}\n\n'
        view = response_view(sse, None, transport_complete=True)
        self.assertEqual(view["response_text"], "hello")
        self.assertEqual(view["provider_response_id"], "resp_end")
        self.assertEqual(view["usage"]["input_tokens"], 7)
        self.assertEqual(original["instructions"], "Be precise")

    def test_https_defaults_and_credential_rejection(self):
        self.assertEqual(normalize_upstream("https://api.openai.com"), ("https://api.openai.com", 443))
        with self.assertRaises(ValueError):
            normalize_upstream("https://user:secret@api.openai.com/v1")
        for key in ("Authorization", "Cookie", "Set-Cookie", "X-Goog-Api-Key"):
            self.assertEqual(redact_headers({key: "secret"})[key], "<redacted>")

    @unittest.skipUnless(shutil.which("openssl"), "openssl required for temporary loopback TLS fixture")
    def test_https_upstream_validates_tls_and_preserves_body(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cert, key = root / "cert.pem", root / "key.pem"
            command = ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
                       "-out", str(cert), "-days", "1", "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1"]
            result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            with self.upstream(context=context) as (upstream, records):
                with self.proxy(root, f"https://127.0.0.1:{upstream}", env=dict(os.environ, SSL_CERT_FILE=str(cert))) as (port, _):
                    self.assertEqual(self.call(port, b'{ "input": "TLS intact" }')[0], 200)
                self.assertEqual(records[0][2], b'{ "input": "TLS intact" }')


if __name__ == "__main__":
    unittest.main()
