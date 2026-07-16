import json
import tempfile
import unittest

from nexcoder.agent.tool_guardrails import (
    ToolGuardrailConfig, ToolGuardrailController,
)
from nexcoder.agent.trajectory import AgentTrajectoryRecorder


class ToolGuardrailTests(unittest.TestCase):
    def test_duplicate_exact_tool_call_is_blocked(self):
        guardrails = ToolGuardrailController()
        first = guardrails.before_call("list_directory", {"path": "."})
        guardrails.after_call("list_directory", {"path": "."}, {"success": True})
        second = guardrails.before_call("list_directory", {"path": "."})

        self.assertTrue(first.allows_execution)
        self.assertFalse(second.allows_execution)
        self.assertEqual(second.code, "duplicate_tool_call")

    def test_mutation_resets_failure_tracking(self):
        # A repeat-exempt command (verify -> fix -> re-verify) that failed
        # is blocked until a successful mutation resets failure tracking.
        config = ToolGuardrailConfig(
            exempt_repeat_tools=frozenset({"run_command"}))
        guardrails = ToolGuardrailController(config)
        guardrails.after_call("run_command", {"command": "pytest"},
                              {"success": False})
        blocked = guardrails.before_call("run_command", {"command": "pytest"})
        self.assertFalse(blocked.allows_execution)

        guardrails.note_mutation()
        retried = guardrails.before_call("run_command", {"command": "pytest"})
        self.assertTrue(retried.allows_execution)

    def test_compaction_resets_duplicate_tracking(self):
        guardrails = ToolGuardrailController()
        guardrails.before_call("read_file", {"path": "a.py"})
        guardrails.after_call("read_file", {"path": "a.py"}, {"success": True})
        guardrails.note_context_compacted()
        decision = guardrails.before_call("read_file", {"path": "a.py"})
        self.assertTrue(decision.allows_execution)


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
