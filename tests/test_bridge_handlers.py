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
from unittest.mock import MagicMock, patch


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

        # The bridge no longer wraps a runtime object; session stores,
        # redaction, and cancellation are bridge-owned (v2 engine).
        _ = (AgentSessionStore, SecretRedactor)  # imports stay exercised

        bridge = Bridge(None)
        project = MagicMock()
        project.get_recent_projects.return_value = []
        bridge._project = project
        bridge._current_project_path = self.root
        self.bridge = bridge

    # ── cancel_agent ─────────────────────────────────────────────────

    def test_cancel_agent_when_idle(self):
        out = json.loads(self.bridge.cancel_agent())
        self.assertTrue(out["success"])
        self.assertFalse(out["cancelled"])

    def test_cancel_agent_when_active(self):
        worker = MagicMock()
        worker.isRunning.return_value = True
        self.bridge._agent_v2_worker = worker
        out = json.loads(self.bridge.cancel_agent())
        self.assertTrue(out["success"])
        self.assertTrue(out["cancelled"])
        worker.cancel.assert_called_once()

    def test_agent_is_active(self):
        worker = MagicMock()
        worker.isRunning.return_value = True
        self.bridge._agent_v2_worker = worker
        out = json.loads(self.bridge.agent_is_active())
        self.assertTrue(out["success"])
        self.assertTrue(out["active"])

    def test_terminal_without_project_uses_home_directory(self):
        self.bridge._current_project_path = None
        terminal = MagicMock()
        terminal.spawn.return_value = "term-home"
        terminal.snapshot.return_value = {
            "sessionId": "term-home",
            "cwd": os.path.expanduser("~"),
            "shell": "powershell.exe",
            "status": "running",
            "exitCode": None,
            "sequence": 0,
            "chunks": [],
        }
        self.bridge._terminal = terminal

        result = json.loads(self.bridge.spawn_terminal(""))

        self.assertTrue(result["success"])
        terminal.spawn.assert_called_once_with(os.path.expanduser("~"))

    def test_terminal_snapshot_reports_missing_session(self):
        self.bridge._terminal = MagicMock()
        self.bridge._terminal.snapshot.return_value = None

        result = json.loads(self.bridge.terminal_snapshot("missing"))

        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "terminal_not_found")

    def test_clone_repository_rejects_unsupported_url(self):
        out = json.loads(self.bridge.clone_repository("javascript:alert(1)", self.root, "repo"))

        self.assertFalse(out["success"])
        self.assertIn("Unsupported repository URL scheme", out["error"])

    def test_clone_repository_derives_safe_directory_name(self):
        name = self.bridge._derive_clone_directory_name(
            "https://github.com/nexa-labs/NexCoder.git", "")

        self.assertEqual(name, "NexCoder")

    def test_clone_repository_rejects_non_empty_destination(self):
        target = os.path.join(self.root, "existing")
        os.makedirs(target)
        with open(os.path.join(target, "file.txt"), "w", encoding="utf-8") as handle:
            handle.write("occupied")

        out = json.loads(self.bridge.clone_repository(
            "https://github.com/nexa-labs/NexCoder.git", self.root, "existing"))

        self.assertFalse(out["success"])
        self.assertIn("Destination folder is not empty", out["error"])

    def test_app_state_persists_under_nexcoder_appdata(self):
        appdata = os.path.join(self.root, "AppData", "Roaming")
        with patch.dict(os.environ, {"APPDATA": appdata}):
            updated = json.loads(self.bridge.app_state_update(json.dumps({
                "onboarding_completed": True,
                "first_run_setup_completed": False,
            })))
            loaded = json.loads(self.bridge.app_state_get())

        expected_path = os.path.join(appdata, "NexCoder", "state.json")
        self.assertTrue(updated["success"])
        self.assertEqual(updated["path"], expected_path)
        self.assertTrue(os.path.exists(expected_path))
        self.assertTrue(loaded["state"]["onboarding_completed"])
        self.assertFalse(loaded["state"]["first_run_setup_completed"])

    def test_app_shell_set_stage_notifies_main_window(self):
        main_window = MagicMock()
        self.bridge._main_window = main_window

        out = json.loads(self.bridge.app_shell_set_stage("ide"))

        self.assertTrue(out["success"])
        self.assertEqual(out["stage"], "ide")
        main_window.set_shell_stage.assert_called_once_with("ide")

    def test_agent_steer_v2_forwards_and_persists_follow_up(self):
        session_id, _ = self.bridge._persist_v2_prompt(
            self.root, None, "start the task", "agent")
        worker = MagicMock()
        worker.isRunning.return_value = True
        self.bridge._agent_v2_worker = worker

        out = json.loads(self.bridge.agent_steer_v2("also update the tests"))

        self.assertTrue(out["success"])
        worker.steer.assert_called_once_with("also update the tests")
        loaded = json.loads(self.bridge.load_session(self.root, session_id))
        self.assertEqual(
            [message["content"] for message in loaded["messages"]],
            ["start the task", "also update the tests"],
        )

    def test_agent_steer_v2_accepts_image_and_persists_only_metadata(self):
        import base64

        session_id, _ = self.bridge._persist_v2_prompt(
            self.root, None, "start the task", "agent")
        worker = MagicMock()
        worker.isRunning.return_value = True
        self.bridge._agent_v2_worker = worker
        data_url = "data:image/png;base64," + base64.b64encode(
            bytes.fromhex("89504e470d0a1a0a")).decode()
        images = [{
            "id": "shot-1", "name": "problem.png",
            "mime_type": "image/png", "data_url": data_url,
        }]

        out = json.loads(self.bridge.agent_steer_v2(
            "fix this", json.dumps(images), "steer-prompt-1"))

        self.assertTrue(out["success"])
        forwarded = worker.steer.call_args.args[1]
        self.assertEqual(forwarded[0]["data_url"], data_url)
        loaded = json.loads(self.bridge.load_session(self.root, session_id))
        metadata = loaded["messages"][-1]["metadata"]["attachments"][0]
        self.assertEqual(metadata["name"], "problem.png")
        self.assertNotIn("data_url", metadata)
        self.assertEqual(
            loaded["messages"][-1]["metadata"]["client_prompt_id"],
            "steer-prompt-1",
        )

    def test_agent_steer_v2_rejects_when_idle(self):
        out = json.loads(self.bridge.agent_steer_v2("follow up"))
        self.assertFalse(out["success"])
        self.assertIn("No agent run active", out["error"])

    def test_binary_preview_returns_mime_size_and_data_url(self):
        import base64

        payload = b"RIFF\x04\x00\x00\x00WAVE"
        path = os.path.join(self.root, "sample.wav")
        with open(path, "wb") as handle:
            handle.write(payload)

        out = json.loads(self.bridge.read_file_base64(path))

        self.assertTrue(out["success"])
        self.assertEqual(out["size"], len(payload))
        self.assertEqual(out["mime_type"], "audio/wav")
        encoded = out["data_url"].split(",", 1)[1]
        self.assertEqual(base64.b64decode(encoded), payload)

    def test_delete_artifact_file_is_limited_to_artifact_folder(self):
        artifact_dir = os.path.join(self.root, ".nexcoder", "artifacts")
        os.makedirs(artifact_dir, exist_ok=True)
        artifact_path = os.path.join(artifact_dir, "run-summary.md")
        outside_path = os.path.join(self.root, "important.md")
        with open(artifact_path, "w", encoding="utf-8") as handle:
            handle.write("# artifact")
        with open(outside_path, "w", encoding="utf-8") as handle:
            handle.write("# important")

        deleted = json.loads(self.bridge.delete_artifact_file(
            ".nexcoder/artifacts/run-summary.md"))
        blocked = json.loads(self.bridge.delete_artifact_file("important.md"))

        self.assertTrue(deleted["success"])
        self.assertFalse(os.path.exists(artifact_path))
        self.assertFalse(blocked["success"])
        self.assertTrue(os.path.exists(outside_path))

    def test_web_auth_callback_accepts_matching_state(self):
        import base64
        import time
        import urllib.parse
        import urllib.request

        received = []
        self.bridge.web_auth_completed.connect(
            lambda payload: received.append(json.loads(payload)))
        appdata = os.path.join(self.root, "AppData", "Roaming")
        session = {
            "accessToken": "access-test",
            "refreshToken": "refresh-test",
            "expiresAt": 2000000000,
            "tokenType": "bearer",
        }
        user = {
            "id": "user_1",
            "email": "dev@nexcoder.test",
            "name": "Dev",
            "session": session,
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(user).encode("utf-8")).decode("ascii").rstrip("=")
        with patch.dict(os.environ, {"APPDATA": appdata}):
            callback_url, state = self.bridge._start_web_auth_callback_server()
            url = callback_url + "?" + urllib.parse.urlencode({
                "state": state,
                "user": encoded,
            })

            with urllib.request.urlopen(url, timeout=5) as response:
                self.assertEqual(response.status, 200)

            deadline = time.time() + 2
            app = _ensure_qapp()
            while not received and time.time() < deadline:
                app.processEvents()
                time.sleep(0.01)

            self.assertEqual(received[-1]["user"]["email"], "dev@nexcoder.test")
            self.assertNotIn("session", received[-1]["user"])
            self.assertTrue(received[-1]["session"]["authenticated"])
            self.assertEqual(
                self.bridge._read_web_auth_session()["refreshToken"],
                "refresh-test",
            )

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

    # ── v2 run persistence → chat history restore ────────────────────

    def test_v2_run_persists_and_restores_as_chat(self):
        # Simulate what agent_run_v2 + _on_agent_v2_finished do around a
        # run, then restore through the same slots the Chats panel uses.
        session_id, history = self.bridge._persist_v2_prompt(
            self.root, None, "add a parser", "agent")
        self.assertIsNotNone(session_id)
        self.assertEqual(history, [])

        result_json = json.dumps({
            "run_id": "run_x", "status": "completed", "success": True,
            "final_text": "Done: parser.py created.", "mutated_files": ["parser.py"],
        })
        enriched = json.loads(self.bridge._persist_v2_result(result_json))
        self.assertEqual(enriched["session_id"], session_id)

        listed = json.loads(self.bridge.list_sessions(self.root))
        self.assertEqual(len(listed["sessions"]), 1)
        self.assertEqual(listed["sessions"][0]["title"], "add a parser")

        loaded = json.loads(self.bridge.load_session(self.root, session_id))
        self.assertTrue(loaded["success"])
        roles = [m["role"] for m in loaded["messages"]]
        self.assertEqual(roles, ["user", "assistant"])
        self.assertIn("parser.py", loaded["messages"][1]["content"])

        # A follow-up prompt in the restored session carries the history.
        session_id2, history2 = self.bridge._persist_v2_prompt(
            self.root, session_id, "now add tests", "agent")
        self.assertEqual(session_id2, session_id)
        self.assertEqual([m["role"] for m in history2], ["user", "assistant"])
        self.assertEqual(history2[1]["metadata"]["run_id"], "run_x")

    def test_follow_up_loads_full_prior_agent_run(self):
        from nexcoder.agent.core.session_store import SessionStore

        session_id, _ = self.bridge._persist_v2_prompt(
            self.root, None, "inspect the project", "agent")
        run_messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "inspect the project"},
            {"role": "assistant", "content": "done"},
        ]
        SessionStore(self.root).save("run_resume", {
            "task": "inspect the project", "status": "completed",
            "messages": run_messages, "todos": [], "turn": 1,
        })
        self.bridge._persist_v2_result(json.dumps({
            "run_id": "run_resume", "status": "completed",
            "final_text": "done", "mutated_files": [],
        }))
        _, history = self.bridge._persist_v2_prompt(
            self.root, session_id, "continue", "agent")

        resumed = self.bridge._resume_v2_messages(self.root, history)

        self.assertEqual(resumed, run_messages)

    def test_v2_result_with_empty_final_text_is_not_blank(self):
        session_id, _ = self.bridge._persist_v2_prompt(
            self.root, None, "do a thing", "agent")
        self.bridge._persist_v2_result(json.dumps({
            "run_id": "r", "status": "cancelled", "final_text": "",
            "mutated_files": [],
        }))
        loaded = json.loads(self.bridge.load_session(self.root, session_id))
        self.assertTrue(loaded["messages"][1]["content"].strip())
        self.assertIn("cancelled", loaded["messages"][1]["content"])

    def test_rewind_to_second_prompt_keeps_first_run_changes(self):
        import time
        from nexcoder.services.checkpoint import CheckpointManager

        path = os.path.join(self.root, "state.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("original")
        manager = CheckpointManager(self.root)

        session_id, _ = self.bridge._persist_v2_prompt(
            self.root, None, "first", "agent", client_prompt_id="prompt-1")
        checkpoint_1 = manager.create([path], "first")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("after first")
        self.bridge._persist_v2_result(json.dumps({
            "run_id": "run-1", "status": "completed", "final_text": "first done",
            "checkpoint_id": checkpoint_1, "mutated_files": ["state.txt"],
        }))

        time.sleep(0.003)
        self.bridge._persist_v2_prompt(
            self.root, session_id, "second", "agent", client_prompt_id="prompt-2")
        checkpoint_2 = manager.create([path], "second")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("after second")
        self.bridge._persist_v2_result(json.dumps({
            "run_id": "run-2", "status": "completed", "final_text": "second done",
            "checkpoint_id": checkpoint_2, "mutated_files": ["state.txt"],
        }))

        result = json.loads(self.bridge.agent_rewind_to_prompt(
            session_id,
            json.dumps({
                "client_prompt_id": "prompt-2",
                "content": "second",
                "user_ordinal": 1,
            }),
        ))

        self.assertTrue(result["success"])
        with open(path, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "after first")
        loaded = json.loads(self.bridge.load_session(self.root, session_id))
        self.assertEqual(
            [message["content"] for message in loaded["messages"]],
            ["first", "first done"],
        )

    def test_rewind_to_first_prompt_restores_original_across_later_runs(self):
        import time
        from nexcoder.services.checkpoint import CheckpointManager

        path = os.path.join(self.root, "state.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("original")
        manager = CheckpointManager(self.root)

        session_id, _ = self.bridge._persist_v2_prompt(
            self.root, None, "first", "agent", client_prompt_id="prompt-1")
        checkpoint_1 = manager.create([path], "first")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("after first")
        self.bridge._persist_v2_result(json.dumps({
            "run_id": "run-1", "status": "completed", "final_text": "first done",
            "checkpoint_id": checkpoint_1, "mutated_files": ["state.txt"],
        }))

        time.sleep(0.003)
        self.bridge._persist_v2_prompt(
            self.root, session_id, "second", "agent", client_prompt_id="prompt-2")
        checkpoint_2 = manager.create([path], "second")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("after second")
        self.bridge._persist_v2_result(json.dumps({
            "run_id": "run-2", "status": "completed", "final_text": "second done",
            "checkpoint_id": checkpoint_2, "mutated_files": ["state.txt"],
        }))

        result = json.loads(self.bridge.agent_rewind_to_prompt(
            session_id,
            json.dumps({
                "client_prompt_id": "prompt-1",
                "content": "first",
                "user_ordinal": 0,
            }),
        ))

        self.assertTrue(result["success"])
        with open(path, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "original")
        loaded = json.loads(self.bridge.load_session(self.root, session_id))
        self.assertEqual(loaded["messages"], [])

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
