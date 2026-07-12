import json
import tempfile
import unittest
from pathlib import Path

from nexcoder.agent.task_plan import TaskPlanTracker


class TaskPlanTrackerTests(unittest.TestCase):
    def test_plan_advances_from_tool_events_and_waits_for_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            updates = []
            tracker = TaskPlanTracker(
                tmp,
                prompt="Create index.html and styles.css",
                task_type="implement",
                session_id="session_001",
                on_update=updates.append,
            )
            tracker.tool_event("tool_started", {"tool": "list_directory"})
            tracker.tool_event("tool_completed", {
                "tool": "list_directory",
                "result": {"success": True, "message": "Listed 2 items"},
            })
            tracker.tool_event("tool_started", {"tool": "write_file"})
            tracker.tool_event("tool_completed", {
                "tool": "write_file",
                "result": {"success": True, "message": "Staged index.html"},
            })
            plan = tracker.finish({"success": True, "patches": 2})

            statuses = {item["phase"]: item["status"] for item in plan["items"]}
            self.assertEqual(statuses, {
                "inspect": "completed",
                "change": "completed",
                "verify": "skipped",
                "review": "approval_required",
            })
            self.assertGreaterEqual(len(updates), 5)
            saved = Path(tmp) / ".nexcoder" / "sessions" / "session_001" / "plan.json"
            self.assertTrue(saved.is_file())
            self.assertEqual(json.loads(saved.read_text(encoding="utf-8"))["id"], plan["id"])

    def test_failed_task_marks_active_phase_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TaskPlanTracker(
                tmp,
                prompt="Fix the build",
                task_type="debug",
            )
            tracker.tool_event("tool_started", {"tool": "run_command"})
            plan = tracker.finish({"success": False, "patches": 0, "error": "Build failed"})

        verify = next(item for item in plan["items"] if item["phase"] == "verify")
        self.assertEqual(verify["status"], "failed")
        self.assertEqual(verify["error"], "Build failed")

    def test_late_read_does_not_regress_plan_after_changes_begin(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TaskPlanTracker(tmp, prompt="Refactor app", task_type="implement")
            tracker.tool_event("tool_started", {"tool": "write_file"})
            tracker.tool_event("tool_started", {"tool": "read_file"})
            plan = tracker.snapshot()

        statuses = {item["phase"]: item["status"] for item in plan["items"]}
        self.assertEqual(statuses["inspect"], "completed")
        self.assertEqual(statuses["change"], "in_progress")


if __name__ == "__main__":
    unittest.main()
