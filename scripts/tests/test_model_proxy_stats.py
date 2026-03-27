#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
