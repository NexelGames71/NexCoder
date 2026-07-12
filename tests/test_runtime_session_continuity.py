import json
import tempfile
import unittest

from nexcoder.agent.runtime import AgentRuntime
from nexcoder.agent.session import AgentSessionStore


class RuntimeSessionContinuityTests(unittest.TestCase):
    def test_follow_up_replaces_superseded_pending_file(self):
        runtime = AgentRuntime()
        emitted: list[dict] = []
        runtime.diff_ready.connect(lambda payload: emitted.append(json.loads(payload)))
        try:
            runtime._handle_diff({
                "file": "styles.css",
                "action": "create",
                "content": "body {}",
                "project_root": "C:/project",
            })
            original_id = next(iter(runtime._pending_diffs))
            runtime._handle_diff({
                "file": "assets/css/styles.css",
                "source": "styles.css",
                "action": "create",
                "operation": "move",
                "supersedes": ["styles.css"],
                "content": "body {}",
                "project_root": "C:/project",
            })

            self.assertEqual(len(runtime._pending_diffs), 1)
            replacement = next(iter(runtime._pending_diffs.values()))
            self.assertEqual(replacement["file"], "assets/css/styles.css")
            self.assertEqual(emitted[-1]["replaces_diff_ids"], [original_id])
        finally:
            runtime._executor.shutdown(wait=False)

    def test_selected_session_history_is_passed_to_follow_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AgentSessionStore(tmp)
            session = store.create_session(title="Build a site", mode="agent")
            store.append_message(session.session_id, "user", "Create index.html and styles.css")
            store.append_message(session.session_id, "assistant", "I staged index.html")

            captured_history = []

            class _Mode:
                def execute(self, prompt, context, history, callbacks):
                    captured_history.extend(history)
                    return {
                        "success": True,
                        "response": "Continuing the original task.",
                        "patches": 0,
                        "mode": "agent",
                    }

            runtime = AgentRuntime()
            runtime._get_mode = lambda _name: _Mode()
            try:
                runtime._run_mode_async(
                    "agent",
                    "continue",
                    {"project_path": tmp, "session_id": session.session_id},
                )
            finally:
                runtime._executor.shutdown(wait=False)

            self.assertEqual(
                captured_history,
                [
                    {"role": "user", "content": "Create index.html and styles.css"},
                    {"role": "assistant", "content": "I staged index.html"},
                ],
            )
            _metadata, messages = store.load_session(session.session_id)
            self.assertEqual([message.content for message in messages][-2:], [
                "continue",
                "Continuing the original task.",
            ])


if __name__ == "__main__":
    unittest.main()
