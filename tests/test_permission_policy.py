import tempfile
import unittest
from pathlib import Path

from nexcoder.agent.executor import AgentExecutor
from nexcoder.agent.permission_policy import PermissionPolicy, PermissionRule
from nexcoder.agent.tool_call_parser import ParsedToolCall
from nexcoder.agent.tool_registry import ToolRegistry


class PermissionPolicyTests(unittest.TestCase):
    def test_read_only_mode_allows_inspection_and_denies_mutation(self):
        policy = PermissionPolicy.for_access_mode("read_only")

        self.assertEqual(policy.evaluate("read_file", "README.md").action, "allow")
        self.assertEqual(policy.evaluate("list_directory", ".").action, "allow")
        self.assertEqual(policy.evaluate("write_file", "index.html").action, "deny")
        self.assertEqual(policy.evaluate("run_command", "npm test").action, "deny")

    def test_full_mode_allows_registered_tools(self):
        policy = PermissionPolicy.for_access_mode("full")

        self.assertEqual(policy.evaluate("write_file", "index.html").action, "allow")
        self.assertEqual(policy.evaluate("run_command", "npm test").action, "allow")

    def test_last_matching_rule_wins(self):
        policy = PermissionPolicy([
            PermissionRule("edit", "deny"),
            PermissionRule("edit", "allow", "docs/*"),
        ])

        self.assertEqual(policy.evaluate("write_file", "src/app.py").action, "deny")
        self.assertEqual(policy.evaluate("write_file", "docs/guide.md").action, "allow")

    def test_executor_emits_blocked_timeline_item_without_staging_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            timeline: list[dict] = []
            registry = ToolRegistry(tmp)
            executor = AgentExecutor(
                registry,
                on_timeline=timeline.append,
                permission_policy=PermissionPolicy.for_access_mode("read_only"),
            )
            call = ParsedToolCall(
                type="tool_call",
                tool="write_file",
                args={"path": "index.html", "content": "<h1>Blocked</h1>"},
                raw="",
            )

            item, observation = executor.execute(call)

            self.assertEqual(item["status"], "blocked")
            self.assertIn("disabled by the active tool policy", observation)
            self.assertFalse(Path(tmp, "index.html").exists())
            self.assertEqual(len(timeline), 1)


if __name__ == "__main__":
    unittest.main()
