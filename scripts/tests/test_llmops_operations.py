#!/usr/bin/env python
"""Tests for persistent detached lifecycle operations."""

from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from unittest import mock

from llmops_kit import llmops_operation_worker
from llmops_kit.llmops_operations import dispatch, list_records, load_record, update_record
from llmops_kit.llmops_paths import resolve_paths


class OperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.paths = resolve_paths(
            {
                "HOME": str(root),
                "LLMOPS_CONFIG_HOME": str(root / "config"),
                "LLMOPS_DATA_HOME": str(root / "data"),
                "LLMOPS_STATE_HOME": str(root / "state"),
                "LLMOPS_CACHE_HOME": str(root / "cache"),
            }
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @mock.patch("llmops_kit.llmops_operations.subprocess.Popen")
    def test_dispatch_persists_and_detaches_worker(self, popen: mock.Mock) -> None:
        record = dispatch(
            self.paths,
            argv=["component", "start", "sample:chat"],
            action="start",
            target="sample:chat",
            command="llmops component start sample:chat",
            plan=[{"action": "start", "component": "sample:chat"}],
            host="model-host",
        )
        stored = load_record(self.paths.operations_dir / f"{record['operation_id']}.json")
        self.assertEqual(stored["state"], "queued")
        self.assertEqual(stored["target"], "sample:chat")
        self.assertEqual(stored["host"], "model-host")
        self.assertEqual(stored["result"], {})
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertTrue(popen.call_args.kwargs["close_fds"])

    def test_list_records_and_transactional_update(self) -> None:
        path = self.paths.operations_dir / "20260721T000000Z-abcdef123456.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {"operation_id": "20260721T000000Z-abcdef123456", "state": "queued"}
            ),
            encoding="utf-8",
        )
        update_record(path, state="succeeded", returncode=0)
        records = list_records(self.paths)
        self.assertEqual(records[0]["state"], "succeeded")
        self.assertEqual(records[0]["returncode"], 0)

    def test_worker_persists_completion_and_output(self) -> None:
        path = self.paths.operations_dir / "20260721T000000Z-abcdef123456.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "operation_id": "20260721T000000Z-abcdef123456",
                    "state": "queued",
                    "argv": ["status"],
                }
            ),
            encoding="utf-8",
        )
        with mock.patch(
            "llmops_kit.llmops_operation_worker.entrypoint.main",
            side_effect=lambda argv: print("completed") or 0,
        ):
            self.assertEqual(llmops_operation_worker.main([str(path)]), 0)
        record = load_record(path)
        self.assertEqual(record["state"], "succeeded")
        self.assertEqual(record["returncode"], 0)
        self.assertEqual(record["result"], {"returncode": 0, "ok": True})
        self.assertIn("completed", record["output_summary"])
        self.assertEqual(record["error"], "")
        self.assertIn("completed", record["stdout"])


if __name__ == "__main__":
    unittest.main()
