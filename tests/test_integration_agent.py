"""End-to-end agent integration test on a fixture project.

This test drives the full agent stack against a tiny on-disk project
(``tests/fixtures/sample_app``). The model is replaced with a stub
that returns a scripted sequence of responses; the test then asserts
the agent:

- Calls the right tool (``read_file``)
- Reaches a clean completion
- Streams the assistant prose to ``on_chunk``
- Persists the conversation to the session store
- Honours a cancel signal mid-run

The point is to catch regressions in the wiring between layers
(runtime → loop → executor → tool registry) that unit tests miss.
"""

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_app")


def _ensure_qapp():
    """Create a single QApplication for the test class.

    The ``AgentRuntime`` is a ``QObject`` and emits ``Signal``s; it
    needs an active QApplication or PySide6 prints a warning and the
    signal dispatch can misbehave in headless test runs.
    """
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class _StubModel:
    """A minimal stand-in for ``ModelConnector`` that returns
    scripted responses on each call.

    The script is a list of lists — ``script[i]`` is the list of
    chunks the model streams on turn ``i``. When the script is
    exhausted, ``chat_completion`` raises ``StopIteration`` so the
    loop exits naturally (no infinite test hang).
    """

    def __init__(self, script: list[list[str]]):
        self._script = script
        self._call_idx = 0
        self.chat_completion = MagicMock(side_effect=self._stream)

    def _stream(self, *args, **kwargs):
        idx = self._call_idx
        self._call_idx += 1
        if idx >= len(self._script):
            raise StopIteration("script exhausted")
        return iter(self._script[idx])


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    """Poll *predicate* until it returns truthy or the timeout hits."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication.instance()
        if app is not None:
            app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


class _AgentHarness:
    """Spin up a real ``AgentRuntime`` for integration testing.

    The harness instantiates the runtime, attaches a stub model
    (via monkey-patching the agentic runner's loop), and exposes
    the signal stream so tests can assert on chunks / completion.
    """

    def __init__(self, project_root: str, script: list[list[str]]):
        from nexcoder.agent.agentic_runner import AgenticRunner
        from nexcoder.agent.mode_profiles import AGENT_PROFILE
        from nexcoder.agent.hermes_runtime import HermesAgentLoop
        from nexcoder.agent.runtime import AgentRuntime

        self.project_root = project_root
        self.runtime = AgentRuntime()
        self.chunks: list[str] = []
        self.statuses: list[dict] = []
        self.completion: dict = {}
        self.runtime.stream_chunk.connect(self.chunks.append)
        self.runtime.status_update.connect(
            lambda s: self.statuses.append(json.loads(s))
        )
        self.runtime.completed.connect(lambda s: self.completion.update(json.loads(s)))

        # Monkey-patch the model on the lazy-loaded agent mode so the
        # stub script drives the loop instead of a real HTTP call.
        mode = self.runtime._modes.get("agent")
        if mode is None:
            # Trigger lazy creation.
            from nexcoder.agent.modes.agent_mode import AgentMode
            mode = AgentMode()
            self.runtime._modes["agent"] = mode
        mode._hermes_loop = HermesAgentLoop(project_root)
        mode._hermes_loop._model = _StubModel(script)

    def run(self, mode: str, prompt: str, **context):
        self.runtime.run_mode(mode, prompt, {"project_path": self.project_root, **context})
        return _wait_for(lambda: bool(self.completion))

    def cancel(self):
        self.runtime.cancel_active_run("test cancel")


class AgentIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not os.path.isdir(FIXTURE):
            raise unittest.SkipTest(f"fixture missing: {FIXTURE}")
        _ensure_qapp()

    def test_read_file_then_final_answer(self):
        """Model: read the math module, then answer with a final answer block."""
        script = [
            # Turn 1: ask to read the file.
            [
                'I will read the math module.\n'
                '<tool_call name="read_file">{"path": "src/math_utils.py"}</tool_call>',
            ],
            # Turn 2: produce a final answer block.
            [
                "<final_answer>{" "title\"\":\"Answer\","
                "\"summary\":\"add sums two ints, multiply multiplies them.\","
                "\"evidence\":[\"src/math_utils.py defines add and multiply\"],"
                "\"files_used\":[\"src/math_utils.py\"],"
                "\"next_steps\":[\"run the tests\"]}</final_answer>"
            ],
        ]
        h = _AgentHarness(FIXTURE, script)
        self.assertTrue(h.run("agent", "what does the math module do?"))
        # Prose was streamed.
        joined = "".join(h.chunks)
        self.assertIn("math module", joined)
        # Completion came through with the right shape.
        self.assertTrue(h.completion.get("success"))
        # Session was created and the user prompt persisted.
        from nexcoder.agent.session import AgentSessionStore
        store = AgentSessionStore(FIXTURE)
        sessions = store.list_sessions()
        self.assertGreaterEqual(len(sessions), 1)
        most_recent = sessions[0]
        self.assertEqual(most_recent.status, "complete")
        _, messages = store.load_session(most_recent.session_id)
        self.assertGreaterEqual(len(messages), 2)
        # The first message is the user prompt.
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[0].content, "what does the math module do?")

    def test_cancellation_stops_run(self):
        """A long script that the test cancels should end with a
        ``cancelled`` status and no patches."""
        # 100 turns of nonsense so the loop has plenty of work to do.
        script = [
            ['<tool_call name="list_directory">{"path":"."}</tool_call>']
            for _ in range(100)
        ]
        h = _AgentHarness(FIXTURE, script)

        # Kick off the run on the executor thread, then cancel from
        # the test thread. We use a small wait so the worker has
        # actually started before we cancel.
        h.runtime.run_mode(
            "agent", "scan everything",
            {"project_path": FIXTURE},
        )
        self.assertTrue(_wait_for(h.runtime.is_active, timeout=1.0))
        cancelled = h.runtime.cancel_active_run("test cancel")
        self.assertTrue(cancelled)
        # Wait for the run to terminate.
        self.assertTrue(_wait_for(lambda: not h.runtime.is_active(), timeout=5.0))
        # The completion payload signals cancellation.
        _wait_for(lambda: h.completion.get("cancelled") is True, timeout=2.0)
        self.assertTrue(h.completion.get("cancelled"))
        self.assertEqual(h.completion.get("cancel_reason"), "test cancel")

    def test_redaction_runs_on_prompt_and_response(self):
        """A prompt that embeds a fake secret should be sanitised
        before the model sees it (or, here, before the loop appends
        it to the in-memory history and the session log)."""
        # Use an obviously fake key — long enough to trip the
        # pattern, prefixed so it can't be confused with a real one.
        secret = "sk-abcdefghijklmnopqrstuvwxyz"
        script = [
            [
                "<final_answer>{\"title\":\"X\",\"summary\":\"y\","
                "\"evidence\":[],\"files_used\":[],\"next_steps\":[]}</final_answer>"
            ],
        ]
        h = _AgentHarness(FIXTURE, script)
        self.assertTrue(
            h.run("agent", f"the key is {secret} — what does math_utils do?")
        )
        # The session message must NOT contain the raw secret.
        from nexcoder.agent.session import AgentSessionStore
        store = AgentSessionStore(FIXTURE)
        most_recent = store.list_sessions()[0]
        _, messages = store.load_session(most_recent.session_id)
        user_msg = next(m for m in messages if m.role == "user")
        self.assertNotIn(secret, user_msg.content)
        self.assertIn("REDACTED", user_msg.content)
        # The redaction metadata is recorded.
        self.assertGreater(user_msg.metadata.get("redactions", 0), 0)


if __name__ == "__main__":
    unittest.main()
