"""Exercise the managed wrapper from typed JSON; no models or remote providers."""

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ProfileRuntimeTests(unittest.TestCase):
    def test_external_profile_drives_listener_report_reload_and_local_health(self):
        records = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                records.append((self.path, body))
                response = b'{"object":"response","status":"completed","output":[]}'
                self.send_response(200)
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)
        upstream = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=upstream.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                config = root / 'config'
                (config / 'services').mkdir(parents=True)
                with socket.socket() as probe:
                    probe.bind(('127.0.0.1', 0))
                    port = probe.getsockname()[1]
                routes = root / 'routes.json'
                routes.write_text(json.dumps({'/fixture': 'http://127.0.0.1:' + str(upstream.server_port)}))
                report = root / 'report.jinja'
                report.write_text('FIRST {{ event }} {{ request_id }}')
                exchange = root / 'exchange.log'
                profile = {'schema_version': 2, 'name': 'model-proxy', 'template_id': 'model-proxy',
                    'runtime': {'listen_host': '127.0.0.1', 'listen_port': port, 'routes_file': str(routes),
                                'python_bin': sys.executable, 'route_name': 'fixture/external'},
                    'logging': {'exchange_log': str(exchange)}, 'template': {'report_path': str(report)}}
                (config / 'services/model-proxy.json').write_text(json.dumps(profile))
                env = {key: value for key, value in os.environ.items() if not key.startswith(('LLMOPS_', 'MODEL_PROXY_'))}
                env.update({'HOME': str(root), 'LLMOPS_ROOT': str(ROOT), 'LLMOPS_CONFIG_HOME': str(config),
                            'LLMOPS_STATE_HOME': str(root / 'state'), 'LLMOPS_DATA_HOME': str(root / 'data'),
                            'LLMOPS_CACHE_HOME': str(root / 'cache'), 'LLMOPS_PYTHON_BIN': sys.executable})
                def command(*args):
                    return subprocess.run(['bash', str(ROOT / 'scripts/model-proxy'), *args], env=env,
                                          capture_output=True, text=True, timeout=20)
                def call():
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                    connection.request('POST', '/fixture/v1/responses', b'{ "input":"fixture" }')
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    response.read()
                    connection.close()
                try:
                    started = command('start')
                    self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
                    call()
                    status = command('status')
                    self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
                    self.assertIn('scope=listener-only', status.stdout)
                    report.write_text('SECOND {{ event }} {{ request_id }}')
                    reload = command('reload-template')
                    self.assertEqual(reload.returncode, 0, reload.stdout + reload.stderr)
                    call()
                    for _ in range(40):
                        if exchange.exists() and 'SECOND response' in exchange.read_text():
                            break
                        time.sleep(.05)
                    self.assertIn('FIRST request', exchange.read_text())
                    self.assertIn('SECOND response', exchange.read_text())
                    self.assertEqual(records, [('/v1/responses', b'{ "input":"fixture" }')] * 2)
                finally:
                    command('stop')
        finally:
            upstream.shutdown()
            upstream.server_close()
            worker.join(2)


if __name__ == '__main__':
    unittest.main()
