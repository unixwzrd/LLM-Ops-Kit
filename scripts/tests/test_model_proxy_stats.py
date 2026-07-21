#!/usr/bin/env python
from __future__ import annotations

import unittest
from pathlib import Path
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import sys

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import model_proxy_tap


class ModelProxyStatsTests(unittest.TestCase):
    def test_extract_response_stats_collects_usage_and_timings(self) -> None:
        payload = {
            "choices": [{"finish_reason": "stop"}, {"finish_reason": "length"}],
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 7,
                "total_tokens": 22,
                "prompt_tokens_details": {"cached_tokens": 0},
            },
            "timings": {
                "cache_n": 0,
                "prompt_n": 15,
                "prompt_ms": 153.79,
                "prompt_per_second": 97.53,
                "predicted_n": 7,
                "predicted_ms": 159.97,
                "predicted_per_second": 43.75,
            },
        }

        self.assertEqual(
            model_proxy_tap.extract_response_stats(payload),
            {
                "usage": {
                    "prompt_tokens": 15,
                    "completion_tokens": 7,
                    "total_tokens": 22,
                    "cached_prompt_tokens": 0,
                },
                "timings": {
                    "prompt_n": 15,
                    "predicted_n": 7,
                    "cache_n": 0,
                    "prompt_ms": 153.79,
                    "predicted_ms": 159.97,
                    "prompt_per_second": 97.53,
                    "predicted_per_second": 43.75,
                },
                "finish_reasons": ["stop", "length"],
            },
        )

    def test_extract_response_stats_returns_none_for_non_object(self) -> None:
        self.assertIsNone(model_proxy_tap.extract_response_stats("not-json"))

    def test_normalize_payload_for_template_parses_stringified_tool_call_arguments(self) -> None:
        payload = {
            "messages": [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "terminal",
                                "arguments": "{\"command\":\"github\"}",
                            },
                        }
                    ],
                }
            ]
        }

        normalized = model_proxy_tap.normalize_payload_for_template(payload)

        self.assertIsInstance(
            normalized["messages"][0]["tool_calls"][0]["function"]["arguments"], dict
        )
        self.assertEqual(
            normalized["messages"][0]["tool_calls"][0]["function"]["arguments"]["command"],
            "github",
        )
        self.assertIsInstance(
            payload["messages"][0]["tool_calls"][0]["function"]["arguments"], str
        )

    def test_render_prompt_from_payload_uses_normalized_tool_call_arguments(self) -> None:
        payload = {
            "messages": [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "execute_code",
                                "arguments": "{\"code\":\"print('hi')\"}",
                            },
                        }
                    ],
                }
            ],
            "tools": [],
        }

        class FakeRenderer:
            def render(self, **context):
                args = context["messages"][0]["tool_calls"][0]["function"]["arguments"]
                return f"{type(args).__name__}:{args['code']}"

        rendered, error = model_proxy_tap.render_prompt_from_payload(
            payload,
            chat_template_renderer=FakeRenderer(),
            chat_template_path="fake.jinja",
            chat_template_error=None,
            chat_template_max_chars=1000,
        )

        self.assertEqual(rendered, "dict:print('hi')")
        self.assertIsNone(error)

    @unittest.skipIf(model_proxy_tap.jinja2 is None, "Jinja is not installed")
    def test_shipped_qwen_template_supports_raise_exception(self) -> None:
        template_path = SCRIPTS_DIR / "templates" / "Qwen-3_5-stock-template.jinja"
        loaded_path, renderer, load_error = model_proxy_tap.load_chat_template_renderer(
            str(template_path)
        )

        self.assertEqual(loaded_path, str(template_path))
        self.assertIsNotNone(renderer)
        self.assertIsNone(load_error)

        rendered, render_error = model_proxy_tap.render_prompt_from_payload(
            {
                "messages": [{"role": "user", "content": "hello"}],
                "tools": [],
                "add_generation_prompt": True,
            },
            chat_template_renderer=renderer,
            chat_template_path=loaded_path,
            chat_template_error=load_error,
            chat_template_max_chars=10000,
        )

        self.assertIsNone(render_error)
        self.assertIn("<|im_start|>user\nhello<|im_end|>", rendered)

    @unittest.skipIf(model_proxy_tap.jinja2 is None, "Jinja is not installed")
    def test_shipped_qwen_template_reports_its_intended_validation_error(self) -> None:
        template_path = SCRIPTS_DIR / "templates" / "Qwen-3_5-stock-template.jinja"
        loaded_path, renderer, load_error = model_proxy_tap.load_chat_template_renderer(
            str(template_path)
        )

        rendered, render_error = model_proxy_tap.render_prompt_from_payload(
            {"messages": [], "tools": []},
            chat_template_renderer=renderer,
            chat_template_path=loaded_path,
            chat_template_error=load_error,
            chat_template_max_chars=10000,
        )

        self.assertIsNone(rendered)
        self.assertEqual(render_error, "TemplateRenderError: No messages provided.")

    @unittest.skipIf(model_proxy_tap.jinja2 is None, "Jinja is not installed")
    def test_media_history_template_keeps_last_tool_image_and_omits_duplicates(self) -> None:
        template_path = SCRIPTS_DIR / "templates" / "Qwen-3_5-media-history-template.jinja"
        loaded_path, renderer, load_error = model_proxy_tap.load_chat_template_renderer(
            str(template_path)
        )
        old_image = "iVBORw0KGgoOLDPAYLOAD" + ("A" * 5000)
        latest_image = "iVBORw0KGgoLATESTPAYLOAD" + ("B" * 5000)
        payload = {
            "messages": [
                {"role": "user", "content": "make an image"},
                {
                    "role": "assistant",
                    "content": "old image generation call",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "terminal",
                                "arguments": json.dumps({"command": "generate old image"}),
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "content": json.dumps({"images": [old_image]}),
                },
                {
                    "role": "assistant",
                    "content": "old image decode call",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "terminal",
                                "arguments": json.dumps({"command": f"decode {old_image}"}),
                            },
                        }
                    ],
                },
                {"role": "tool", "content": "old image decode result"},
                {
                    "role": "assistant",
                    "content": "generating a newer image",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "terminal",
                                "arguments": json.dumps({"command": "generate again"}),
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "content": json.dumps({"images": [latest_image]}),
                },
                {"role": "user", "content": "continue"},
            ],
            "tools": [],
            "add_generation_prompt": True,
        }

        rendered, render_error = model_proxy_tap.render_prompt_from_payload(
            payload,
            chat_template_renderer=renderer,
            chat_template_path=loaded_path,
            chat_template_error=load_error,
            chat_template_max_chars=0,
        )

        self.assertIsNone(render_error)
        self.assertNotIn("OLDPAYLOAD", rendered)
        self.assertIn("LATESTPAYLOAD", rendered)
        self.assertNotIn("old image generation call", rendered)
        self.assertNotIn("generate old image", rendered)
        self.assertNotIn("old image decode call", rendered)
        self.assertNotIn("old image decode result", rendered)
        self.assertIn("generating a newer image", rendered)
        self.assertIn("generate again", rendered)

    @unittest.skipIf(model_proxy_tap.jinja2 is None, "Jinja is not installed")
    def test_media_history_template_preserves_structured_images(self) -> None:
        template_path = SCRIPTS_DIR / "templates" / "Qwen-3_5-media-history-template.jinja"
        loaded_path, renderer, load_error = model_proxy_tap.load_chat_template_renderer(
            str(template_path)
        )
        rendered, render_error = model_proxy_tap.render_prompt_from_payload(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "first"},
                            {"type": "image_url", "image_url": {"url": "one"}},
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "second"},
                            {"type": "image_url", "image_url": {"url": "two"}},
                        ],
                    },
                ],
                "tools": [],
                "add_generation_prompt": True,
            },
            chat_template_renderer=renderer,
            chat_template_path=loaded_path,
            chat_template_error=load_error,
            chat_template_max_chars=10000,
        )

        self.assertIsNone(render_error)
        self.assertEqual(rendered.count("<|image_pad|>"), 2)
        self.assertNotIn("[Earlier image omitted]", rendered)

    @unittest.skipIf(model_proxy_tap.jinja2 is None, "Jinja is not installed")
    def test_media_history_template_keeps_only_latest_explicit_audio_and_video_results(self) -> None:
        template_path = SCRIPTS_DIR / "templates" / "Qwen-3_5-media-history-template.jinja"
        loaded_path, renderer, load_error = model_proxy_tap.load_chat_template_renderer(
            str(template_path)
        )
        old_audio = "data:audio/wav;base64,OLDV0FWRQ" + ("A" * 5000)
        latest_audio = "data:audio/wav;base64,LATESTV0FWRQ" + ("B" * 5000)
        old_video = "data:video/mp4;base64,OLDVIDEO" + ("C" * 5000)
        latest_video = "data:video/mp4;base64,LATESTVIDEO" + ("D" * 5000)
        messages = [{"role": "user", "content": "make media"}]
        for label, payload in (
            ("old audio", old_audio),
            ("latest audio", latest_audio),
            ("old video", old_video),
            ("latest video", latest_video),
        ):
            messages.extend(
                [
                    {
                        "role": "assistant",
                        "content": f"{label} generation call",
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "terminal",
                                    "arguments": json.dumps({"command": f"generate {label}"}),
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "content": json.dumps(
                            {"audio" if "audio" in label else "video": payload}
                        ),
                    },
                ]
            )
        messages.append({"role": "user", "content": "continue"})
        rendered, render_error = model_proxy_tap.render_prompt_from_payload(
            {"messages": messages, "tools": [], "add_generation_prompt": True},
            chat_template_renderer=renderer,
            chat_template_path=loaded_path,
            chat_template_error=load_error,
            chat_template_max_chars=0,
        )

        self.assertIsNone(render_error)
        self.assertNotIn("OLDV0FWRQ", rendered)
        self.assertIn("LATESTV0FWRQ", rendered)
        self.assertNotIn("OLDVIDEO", rendered)
        self.assertIn("LATESTVIDEO", rendered)
        self.assertNotIn("old audio generation call", rendered)
        self.assertNotIn("old video generation call", rendered)
        self.assertIn("latest audio generation call", rendered)
        self.assertIn("latest video generation call", rendered)

    @unittest.skipIf(model_proxy_tap.jinja2 is None, "Jinja is not installed")
    def test_media_history_template_preserves_structured_video(self) -> None:
        template_path = SCRIPTS_DIR / "templates" / "Qwen-3_5-media-history-template.jinja"
        loaded_path, renderer, load_error = model_proxy_tap.load_chat_template_renderer(
            str(template_path)
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "first video"},
                    {"type": "video", "video": "old-video.mp4"},
                ],
            },
            {"role": "assistant", "content": "first response"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "latest video"},
                    {"type": "video", "video": "latest-video.mp4"},
                ],
            },
        ]
        rendered, render_error = model_proxy_tap.render_prompt_from_payload(
            {"messages": messages, "tools": [], "add_generation_prompt": True},
            chat_template_renderer=renderer,
            chat_template_path=loaded_path,
            chat_template_error=load_error,
            chat_template_max_chars=0,
        )

        self.assertIsNone(render_error)
        self.assertEqual(rendered.count("<|video_pad|>"), 2)
        self.assertIn("first video", rendered)
        self.assertIn("latest video", rendered)

    @unittest.skipIf(model_proxy_tap.jinja2 is None, "Jinja is not installed")
    def test_media_history_template_handles_truncated_real_request_shape(self) -> None:
        template_path = SCRIPTS_DIR / "templates" / "Qwen-3_5-media-history-template.jinja"
        loaded_path, renderer, load_error = model_proxy_tap.load_chat_template_renderer(
            str(template_path)
        )
        old_image = (
            'iVBORw0KGgoOLD\\n\\n... [OUTPUT TRUNCATED - 1099865 chars omitted '
            'out of 1149865 total] ...\\n\\nSUQz' + ("A" * 5000)
        )
        latest_image = (
            'iVBORw0KGgoLATEST\\n\\n... [OUTPUT TRUNCATED - 1099865 chars omitted '
            'out of 1149865 total] ...\\n\\nTAIL' + ("B" * 5000)
        )
        payload = {
            "messages": [
                {"role": "user", "content": "generate images"},
                {
                    "role": "assistant",
                    "content": "first generation",
                    "tool_calls": [{"type": "function", "function": {"name": "terminal", "arguments": json.dumps({"command": "first"})}}],
                },
                {"role": "tool", "content": json.dumps({"output": json.dumps({"images": [old_image]})})},
                {
                    "role": "assistant",
                    "content": "second generation",
                    "tool_calls": [{"type": "function", "function": {"name": "terminal", "arguments": json.dumps({"command": "second"})}}],
                },
                {"role": "tool", "content": json.dumps({"output": json.dumps({"images": [latest_image]})})},
                {"role": "user", "content": "continue"},
            ],
            "tools": [],
            "add_generation_prompt": True,
        }

        rendered, render_error = model_proxy_tap.render_prompt_from_payload(
            payload,
            chat_template_renderer=renderer,
            chat_template_path=loaded_path,
            chat_template_error=load_error,
            chat_template_max_chars=0,
        )

        self.assertIsNone(render_error)
        self.assertNotIn("iVBORw0KGgoOLD", rendered)
        self.assertNotIn("first generation", rendered)
        self.assertIn("iVBORw0KGgoLATEST", rendered)
        self.assertIn("second generation", rendered)
        self.assertEqual(rendered.count("[OUTPUT TRUNCATED"), 1)

class _CaptureHandler(BaseHTTPRequestHandler):
    received_bodies: list[bytes] = []
    response_body: bytes = json.dumps({"ok": True}).encode("utf-8")

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        type(self).received_bodies.append(body)
        response_body = type(self).response_body
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)


class ProxyTapPassthroughTests(unittest.TestCase):
    def _start_server(self, handler_class):
        server = HTTPServer(("127.0.0.1", 0), handler_class)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def _make_proxy_handler(self, log_dir: Path, upstream_url: str, renderer):
        class Handler(model_proxy_tap.ProxyTapHandler):
            pass

        Handler.upstream_base = upstream_url
        Handler.log_path = log_dir / "proxy.ndjson"
        Handler.timeout_sec = 5.0
        Handler.log_fsync = False
        Handler.log_rotate_seconds = 0
        Handler.log_rotate_keep = 0
        Handler._log_writers = {}
        Handler.stream_chunk_size = 65536
        Handler.chat_template_path = "fake.jinja"
        Handler.chat_template_max_chars = 200000
        Handler.chat_template_renderer = renderer
        Handler.chat_template_error = None
        Handler.raw_request_log_path = log_dir / "proxy.raw.log"
        Handler.rendered_prompt_log_path = log_dir / "proxy.rendered.log"
        Handler.raw_response_log_path = log_dir / "proxy.raw.log"
        return Handler

    def test_chat_template_logging_does_not_change_forwarded_request_body(self) -> None:
        _CaptureHandler.received_bodies = []
        _CaptureHandler.response_body = json.dumps({"ok": True}).encode("utf-8")
        upstream, upstream_thread = self._start_server(_CaptureHandler)
        self.addCleanup(upstream.shutdown)
        self.addCleanup(upstream.server_close)
        self.addCleanup(upstream_thread.join, 1)
        import tempfile
        from urllib.request import Request, urlopen

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            class FakeRenderer:
                def render(self, **context):
                    args = context["messages"][0]["tool_calls"][0]["function"]["arguments"]
                    return f"rendered:{type(args).__name__}:{args['code']}"

            proxy_handler = self._make_proxy_handler(
                log_dir,
                f"http://127.0.0.1:{upstream.server_port}",
                FakeRenderer(),
            )
            proxy, proxy_thread = self._start_server(proxy_handler)
            self.addCleanup(proxy.shutdown)
            self.addCleanup(proxy.server_close)
            self.addCleanup(proxy_thread.join, 1)

            payload = {
                "messages": [
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "execute_code",
                                    "arguments": "{\"code\":\"print('hi')\"}",
                                },
                            }
                        ],
                    }
                ],
                "tools": [],
            }
            request_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            request = Request(
                f"http://127.0.0.1:{proxy.server_port}/v1/chat/completions",
                data=request_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read().decode("utf-8")), {"ok": True})

            self.assertEqual(_CaptureHandler.received_bodies, [request_body])

            ndjson = (log_dir / "proxy.ndjson").read_text(encoding="utf-8").splitlines()
            request_start = json.loads(ndjson[0])
            self.assertEqual(request_start["event"], "request_start")
            self.assertEqual(request_start["request_text"], request_body.decode("utf-8"))
            self.assertNotIn("request_rewrite", request_start)
            self.assertNotIn("rendered_prompt", request_start)
            self.assertNotIn("rendered_prompt_error", request_start)

            rendered_log = (log_dir / "proxy.rendered.log").read_text(encoding="utf-8")
            self.assertIn("rendered:dict:print('hi')", rendered_log)

    def test_response_body_passes_through_unchanged_and_jsonl_stays_raw(self) -> None:
        _CaptureHandler.received_bodies = []
        upstream_response = json.dumps(
            {
                "id": "resp-1",
                "object": "chat.completion",
                "choices": [{"message": {"role": "assistant", "content": "plain upstream response"}}],
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        _CaptureHandler.response_body = upstream_response
        upstream, upstream_thread = self._start_server(_CaptureHandler)
        self.addCleanup(upstream.shutdown)
        self.addCleanup(upstream.server_close)
        self.addCleanup(upstream_thread.join, 1)
        import tempfile
        from urllib.request import Request, urlopen

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            class FakeRenderer:
                def render(self, **context):
                    return "rendered only"

            proxy_handler = self._make_proxy_handler(
                log_dir,
                f"http://127.0.0.1:{upstream.server_port}",
                FakeRenderer(),
            )
            proxy, proxy_thread = self._start_server(proxy_handler)
            self.addCleanup(proxy.shutdown)
            self.addCleanup(proxy.server_close)
            self.addCleanup(proxy_thread.join, 1)

            request_body = b'{"messages":[{"role":"user","content":"hello"}]}'
            request = Request(
                f"http://127.0.0.1:{proxy.server_port}/v1/chat/completions",
                data=request_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), upstream_response)

            ndjson = [json.loads(line) for line in (log_dir / "proxy.ndjson").read_text(encoding="utf-8").splitlines()]
            request_end = ndjson[1]
            self.assertEqual(request_end["event"], "request_end")
            self.assertEqual(request_end["response_text"], upstream_response.decode("utf-8"))
            self.assertNotIn("rendered_prompt", request_end)
            self.assertNotIn("rendered_prompt_error", request_end)

            raw_log = (log_dir / "proxy.raw.log").read_text(encoding="utf-8")
            self.assertIn(request_body.decode("utf-8"), raw_log)
            self.assertIn(upstream_response.decode("utf-8"), raw_log)

    def test_no_proxy_added_truncation_markers_in_logs(self) -> None:
        _CaptureHandler.received_bodies = []
        upstream_response = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "x" * 5000,
                        }
                    }
                ]
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        _CaptureHandler.response_body = upstream_response
        upstream, upstream_thread = self._start_server(_CaptureHandler)
        self.addCleanup(upstream.shutdown)
        self.addCleanup(upstream.server_close)
        self.addCleanup(upstream_thread.join, 1)
        import tempfile
        from urllib.request import Request, urlopen

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            class FakeRenderer:
                def render(self, **context):
                    return "y" * 5000

            proxy_handler = self._make_proxy_handler(
                log_dir,
                f"http://127.0.0.1:{upstream.server_port}",
                FakeRenderer(),
            )
            proxy_handler.chat_template_max_chars = 10
            proxy, proxy_thread = self._start_server(proxy_handler)
            self.addCleanup(proxy.shutdown)
            self.addCleanup(proxy.server_close)
            self.addCleanup(proxy_thread.join, 1)

            request_body = b'{"messages":[{"role":"user","content":"hello"}]}'
            request = Request(
                f"http://127.0.0.1:{proxy.server_port}/v1/chat/completions",
                data=request_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), upstream_response)

            ndjson_text = (log_dir / "proxy.ndjson").read_text(encoding="utf-8")
            raw_log = (log_dir / "proxy.raw.log").read_text(encoding="utf-8")
            rendered_log = (log_dir / "proxy.rendered.log").read_text(encoding="utf-8")

            self.assertNotIn("<truncated>", ndjson_text)
            self.assertNotIn("<truncated>", raw_log)
            self.assertNotIn("<truncated>", rendered_log)


if __name__ == "__main__":
    unittest.main()
