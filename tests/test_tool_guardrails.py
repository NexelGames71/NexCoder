import json
import tempfile
import unittest
from pathlib import Path

from nexcoder.agent.executor import AgentExecutor
from nexcoder.agent.tool_call_parser import ParsedToolCall
from nexcoder.agent.tool_guardrails import ToolGuardrailController
from nexcoder.agent.tool_registry import ToolRegistry
from nexcoder.agent.trajectory import AgentTrajectoryRecorder


class ToolGuardrailTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.registry = ToolRegistry(self.root)

    def test_duplicate_exact_tool_call_is_skipped_as_timeline_item(self):
        timeline: list[dict] = []
        executor = AgentExecutor(
            self.registry,
            on_timeline=timeline.append,
            guardrails=ToolGuardrailController(),
        )
        call = ParsedToolCall(
            type="tool_call",
            tool="list_directory",
            args={"path": "."},
            raw="",
        )

        _first_item, first_observation = executor.execute(call)
        second_item, second_observation = executor.execute(call)

        self.assertIn('"success": true', first_observation.lower())
        self.assertEqual(second_item["status"], "skipped")
        self.assertIsNone(second_item["error"])
        self.assertEqual(second_item["guardrail"]["code"], "duplicate_tool_call")
        payload = json.loads(second_observation)
        self.assertEqual(payload["result"]["error_code"], "duplicate_tool_call")

    def test_repeated_same_tool_failures_get_guardrail_metadata(self):
        executor = AgentExecutor(
            self.registry,
            guardrails=ToolGuardrailController(),
        )
        calls = [
            ParsedToolCall("tool_call", "read_file", {"path": "missing_a.py"}, ""),
            ParsedToolCall("tool_call", "read_file", {"path": "missing_b.py"}, ""),
        ]

        executor.execute(calls[0])
        item, observation = executor.execute(calls[1])

        self.assertEqual(item["status"], "failed")
        self.assertEqual(item["guardrail"]["code"], "same_tool_failure_warning")
        payload = json.loads(observation)
        self.assertEqual(payload["result"]["guardrail"]["code"], "same_tool_failure_warning")


class TrajectoryRecorderTests(unittest.TestCase):
    def test_writes_compact_jsonl_trajectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = AgentTrajectoryRecorder(tmp, task="scan the project", mode="agent")
            recorder.record("tool_started", {"tool": "list_directory", "args": {"path": "."}})
            path = recorder.finish(status="complete", result={"success": True})

            self.assertIsNotNone(path)
            self.assertTrue(path.exists())
            entry = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(entry["mode"], "agent")
            self.assertEqual(entry["status"], "complete")
            self.assertEqual(entry["events"][0]["type"], "tool_started")


if __name__ == "__main__":
    unittest.main()
