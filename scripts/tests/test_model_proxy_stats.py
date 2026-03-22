#!/usr/bin/env python3
from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
