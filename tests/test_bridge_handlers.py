"""Tests for the new bridge slots: cancel_agent, agent_is_active, list_sessions,
load_session, delete_session, redact_text.

The bridge is a ``QObject`` that uses ``QWebChannel``. To exercise the
slots we instantiate it without a main window and a stub agent
runtime. The QApplication requirement is satisfied by spinning up a
minimal one in setUp.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock


def _ensure_qapp():
    """Create a single QApplication for the test class."""
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class BridgeSlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _ensure_qapp()

    def setUp(self) -> None:
        # Import here so the QApplication exists before the bridge
        # class is loaded.
        from nexcoder.bridge import Bridge
        from nexcoder.agent.session import AgentSessionStore
        from nexcoder.agent.redaction import SecretRedactor

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

        # Stub the agent runtime with a thin object that exposes the
        # few methods the bridge calls. We don't use a MagicMock here
        # because the session-related methods need real behaviour.
        class _StubAgent:
            def __init__(self) -> None:
                self._redactor = SecretRedactor()
                self._project = MagicMock()
                self._project.get_recent_projects.return_value = []
                self._session_stores: dict[str, AgentSessionStore] = {}

            def is_active(self) -> bool:
                return False

            def cancel_active_run(self, reason: str = "") -> bool:
                return False

            def get_session_store(self, project_root: str) -> AgentSessionStore:
                if project_root in self._session_stores:
                    return self._session_stores[project_root]
                store = AgentSessionStore(project_root)
                self._session_stores[project_root] = store
                return store

            def approve_patchset(self, diff_ids: list[str], project_root: str) -> dict:
                return {
                    "checkpoint_id": "checkpoint-test",
                    "files": ["index.html"],
                    "validation": {"success": True, "files_checked": 1},
                }

        self.agent = _StubAgent()

        bridge = Bridge(None)
        bridge._agent = self.agent
        bridge._project = self.agent._project
        bridge._current_project_path = self.root
        self.bridge = bridge

    # ── cancel_agent ─────────────────────────────────────────────────

    def test_cancel_agent_when_idle(self):
        out = json.loads(self.bridge.cancel_agent())
        self.assertTrue(out["success"])
        self.assertFalse(out["cancelled"])

    def test_cancel_agent_when_active(self):
        # Override the stub to report an active run.
        original = self.agent.cancel_active_run
        self.agent.cancel_active_run = lambda reason="": True
        try:
            out = json.loads(self.bridge.cancel_agent())
        finally:
            self.agent.cancel_active_run = original
        self.assertTrue(out["success"])
        self.assertTrue(out["cancelled"])

    def test_agent_is_active(self):
        # Override the stub to report an active run.
        self.agent.is_active = lambda: True
        out = json.loads(self.bridge.agent_is_active())
        self.assertTrue(out["success"])
        self.assertTrue(out["active"])

    # ── list_sessions ────────────────────────────────────────────────

    def test_list_sessions_empty(self):
        out = json.loads(self.bridge.list_sessions(self.root))
        self.assertTrue(out["success"])
        self.assertEqual(out["sessions"], [])

    def test_list_sessions_with_data(self):
        from nexcoder.agent.session import AgentSessionStore
        store = AgentSessionStore(self.root)
        meta = store.create_session(title="hi", mode="ask")
        store.append_message(meta.session_id, "user", "hello")
        out = json.loads(self.bridge.list_sessions(self.root))
        self.assertTrue(out["success"])
        self.assertEqual(len(out["sessions"]), 1)
        self.assertEqual(out["sessions"][0]["title"], "hi")

    # ── load_session ─────────────────────────────────────────────────

    def test_load_session_round_trip(self):
        from nexcoder.agent.session import AgentSessionStore
        store = AgentSessionStore(self.root)
        meta = store.create_session(title="t", mode="ask")
        store.append_message(meta.session_id, "user", "hi")
        store.append_message(meta.session_id, "assistant", "hello")
        out = json.loads(self.bridge.load_session(self.root, meta.session_id))
        self.assertTrue(out["success"])
        self.assertEqual(out["metadata"]["title"], "t")
        self.assertEqual(len(out["messages"]), 2)

    def test_load_session_missing_returns_envelope(self):
        from nexcoder.agent.session import AgentSessionStore
        AgentSessionStore(self.root)  # creates the dir
        out = json.loads(self.bridge.load_session(self.root, "nonexistent"))
        self.assertFalse(out["success"])
        self.assertEqual(out["error_envelope"]["code"], "session_not_found")
        self.assertEqual(out["error_envelope"]["category"], "user_recoverable")

    # ── delete_session ───────────────────────────────────────────────

    def test_delete_session_existing(self):
        from nexcoder.agent.session import AgentSessionStore
        store = AgentSessionStore(self.root)
        meta = store.create_session()
        out = json.loads(self.bridge.delete_session(self.root, meta.session_id))
        self.assertTrue(out["success"])
        self.assertTrue(out["removed"])

    def test_delete_session_missing(self):
        from nexcoder.agent.session import AgentSessionStore
        AgentSessionStore(self.root)
        out = json.loads(self.bridge.delete_session(self.root, "nonexistent"))
        self.assertTrue(out["success"])
        self.assertFalse(out["removed"])

    def test_create_session_slot(self):
        out = json.loads(self.bridge.create_session(self.root, "Fresh chat", "agent"))
        self.assertTrue(out["success"])
        self.assertEqual(out["metadata"]["title"], "Fresh chat")
        self.assertEqual(out["metadata"]["mode"], "agent")
        self.assertFalse(out["metadata"]["archived"])

    def test_archive_session_slot(self):
        from nexcoder.agent.session import AgentSessionStore
        store = AgentSessionStore(self.root)
        meta = store.create_session(title="old")
        out = json.loads(self.bridge.archive_session(self.root, meta.session_id, "true"))
        self.assertTrue(out["success"])
        self.assertTrue(out["metadata"]["archived"])

    def test_approve_patchset_slot_returns_validation(self):
        out = json.loads(self.bridge.agent_approve_patchset(json.dumps(["diff-a", "diff-b"])))
        self.assertTrue(out["success"])
        self.assertEqual(out["checkpoint_id"], "checkpoint-test")
        self.assertTrue(out["validation"]["success"])

    # ── redact_text ──────────────────────────────────────────────────

    def test_redact_text_with_secret(self):
        out = json.loads(self.bridge.redact_text("key: sk-abcdefghijklmnopqrstuvwxyz"))
        self.assertTrue(out["success"])
        self.assertIn("openai_api_key", out["labels"])
        self.assertNotIn("sk-abc", out["text"])

    def test_redact_text_clean(self):
        out = json.loads(self.bridge.redact_text("hello world"))
        self.assertTrue(out["success"])
        self.assertEqual(out["count"], 0)
        self.assertEqual(out["text"], "hello world")

    def test_redact_text_empty(self):
        out = json.loads(self.bridge.redact_text(""))
        self.assertTrue(out["success"])
        self.assertEqual(out["count"], 0)
        self.assertEqual(out["text"], "")


class SlotErrorResponseTests(unittest.TestCase):
    """``slot_error_response`` returns an envelope with stable shape."""

    def test_envelope_shape_is_stable(self):
        from nexcoder.bridge import slot_error_response

        try:
            raise ValueError("boom")
        except ValueError as exc:
            out = json.loads(slot_error_response(exc))

        self.assertFalse(out["success"])
        self.assertIn("error", out)
        envelope = out["error_envelope"]
        self.assertIn("code", envelope)
        self.assertIn("message", envelope)
        self.assertIn("category", envelope)
        self.assertIn("details", envelope)
        self.assertIn("retryable", envelope)

    def test_explicit_code_overrides_default(self):
        from nexcoder.bridge import slot_error_response

        out = json.loads(slot_error_response(
            ValueError("x"),
            code="custom_thing",
            category="safety",
            details={"k": "v"},
        ))
        self.assertEqual(out["error_envelope"]["code"], "custom_thing")
        self.assertEqual(out["error_envelope"]["category"], "safety")
        self.assertEqual(out["error_envelope"]["details"], {"k": "v"})


if __name__ == "__main__":
    unittest.main()
