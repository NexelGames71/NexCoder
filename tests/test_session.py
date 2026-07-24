"""Tests for the AgentSessionStore and on-disk session format."""

import json
import os
import tempfile
import unittest

from nexcoder.agent.session import (
    AgentSessionStore,
    SessionMessage,
    SessionMetadata,
    _atomic_write_json,
)


class AgentSessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.store = AgentSessionStore(self.root)

    # ── create_session ───────────────────────────────────────────────

    def test_create_session_returns_metadata(self):
        meta = self.store.create_session(title="hello", mode="ask")
        self.assertIsInstance(meta, SessionMetadata)
        self.assertEqual(meta.title, "hello")
        self.assertEqual(meta.mode, "ask")
        self.assertEqual(meta.status, "active")
        self.assertEqual(meta.message_count, 0)

    def test_create_session_makes_disk_artifacts(self):
        meta = self.store.create_session()
        session_dir = os.path.join(
            self.root, ".nexcoder", "sessions", meta.session_id
        )
        self.assertTrue(os.path.isdir(session_dir))
        self.assertTrue(os.path.isfile(os.path.join(session_dir, "session.json")))
        self.assertTrue(os.path.isfile(os.path.join(session_dir, "messages.jsonl")))

    def test_create_session_rejects_duplicate_id(self):
        meta = self.store.create_session(session_id="abc12345")
        with self.assertRaises(FileExistsError):
            self.store.create_session(session_id="abc12345")

    def test_create_session_rejects_invalid_id(self):
        with self.assertRaises(ValueError):
            self.store.create_session(session_id="../etc/passwd")

    # ── append_message ───────────────────────────────────────────────

    def test_append_message_increments_count(self):
        meta = self.store.create_session()
        self.store.append_message(meta.session_id, "user", "hi")
        self.store.append_message(meta.session_id, "assistant", "hello")
        listed = self.store.list_sessions()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].message_count, 2)

    def test_append_message_updates_title_to_first_user_prompt(self):
        meta = self.store.create_session(title="New session")
        self.store.append_message(meta.session_id, "user", "Fix the login bug")
        _, messages = self.store.load_session(meta.session_id)
        self.assertEqual(messages[0].role, "user")
        # The metadata title is updated to the first user message.
        listed = self.store.list_sessions()
        self.assertEqual(listed[0].title, "Fix the login bug")

    def test_append_message_truncates_long_titles(self):
        meta = self.store.create_session(title="New session")
        long_prompt = "a " * 100
        self.store.append_message(meta.session_id, "user", long_prompt)
        listed = self.store.list_sessions()
        self.assertLessEqual(len(listed[0].title), 64)

    def test_append_message_persists_metadata(self):
        meta = self.store.create_session()
        self.store.append_message(
            meta.session_id, "user", "hi",
            metadata={"task_type": "question"},
        )
        reloaded = self.store.load_session(meta.session_id)
        self.assertEqual(reloaded[1][0].metadata.get("task_type"), "question")

    def test_append_message_writes_valid_jsonl(self):
        meta = self.store.create_session()
        self.store.append_message(meta.session_id, "user", "line1")
        self.store.append_message(meta.session_id, "assistant", "line2")
        path = os.path.join(
            self.root, ".nexcoder", "sessions",
            meta.session_id, "messages.jsonl",
        )
        with open(path, "r", encoding="utf-8") as fh:
            lines = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["role"], "user")
        self.assertEqual(lines[1]["content"], "line2")

    # ── list_sessions ────────────────────────────────────────────────

    def test_list_sessions_empty(self):
        self.assertEqual(self.store.list_sessions(), [])

    def test_list_sessions_newest_first(self):
        a = self.store.create_session(title="a")
        b = self.store.create_session(title="b")
        sessions = self.store.list_sessions()
        self.assertEqual([s.session_id for s in sessions], [b.session_id, a.session_id])

    def test_list_sessions_reflects_updates(self):
        a = self.store.create_session(title="a")
        self.store.append_message(a.session_id, "user", "ping")
        sessions = self.store.list_sessions()
        self.assertEqual(sessions[0].message_count, 1)

    # ── load_session ─────────────────────────────────────────────────

    def test_load_session_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.store.load_session("does-not-exist")

    def test_load_session_corrupt_raises_value_error(self):
        meta = self.store.create_session()
        path = os.path.join(
            self.root, ".nexcoder", "sessions",
            meta.session_id, "session.json",
        )
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        with self.assertRaises(ValueError):
            self.store.load_session(meta.session_id)

    def test_load_session_skips_corrupt_message_lines(self):
        meta = self.store.create_session()
        path = os.path.join(
            self.root, ".nexcoder", "sessions",
            meta.session_id, "messages.jsonl",
        )
        self.store.append_message(meta.session_id, "user", "first")
        # Manually append a corrupt line then a valid one.
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("{not json\n")
        self.store.append_message(meta.session_id, "user", "second")
        _, messages = self.store.load_session(meta.session_id)
        # Corrupt line is skipped; the rest still load.
        self.assertEqual(len(messages), 2)
        self.assertEqual([m.content for m in messages], ["first", "second"])

    # ── delete_session ───────────────────────────────────────────────

    def test_delete_session_removes_files(self):
        meta = self.store.create_session()
        self.assertTrue(self.store.delete_session(meta.session_id))
        self.assertEqual(self.store.list_sessions(), [])

    def test_delete_session_missing_returns_false(self):
        self.assertFalse(self.store.delete_session("never-existed"))

    def test_delete_session_keeps_others(self):
        a = self.store.create_session()
        b = self.store.create_session()
        self.store.delete_session(a.session_id)
        remaining = [s.session_id for s in self.store.list_sessions()]
        self.assertEqual(remaining, [b.session_id])

    def test_archive_session_updates_metadata_without_deleting(self):
        meta = self.store.create_session(title="keep")
        archived = self.store.archive_session(meta.session_id, True)
        self.assertTrue(archived.archived)

        loaded_meta, _ = self.store.load_session(meta.session_id)
        self.assertTrue(loaded_meta.archived)
        self.assertTrue(os.path.isdir(os.path.join(
            self.root, ".nexcoder", "sessions", meta.session_id
        )))

    def test_archive_session_can_unarchive(self):
        meta = self.store.create_session(title="restore")
        self.store.archive_session(meta.session_id, True)
        restored = self.store.archive_session(meta.session_id, False)
        self.assertFalse(restored.archived)
        self.assertFalse(self.store.list_sessions()[0].archived)

    # ── set_status ───────────────────────────────────────────────────

    def test_set_status_updates_metadata(self):
        meta = self.store.create_session()
        self.store.set_status(meta.session_id, "complete")
        self.store.set_status(meta.session_id, "cancelled")
        loaded = self.store.load_session(meta.session_id)[0]
        self.assertEqual(loaded.status, "cancelled")

    def test_set_status_rejects_unknown(self):
        meta = self.store.create_session()
        with self.assertRaises(ValueError):
            self.store.set_status(meta.session_id, "bogus")

    # ── iter_messages ────────────────────────────────────────────────

    def test_iter_messages_streams(self):
        meta = self.store.create_session()
        for i in range(5):
            self.store.append_message(meta.session_id, "user", f"msg {i}")
        # iter_messages returns a fresh iterator each call.
        it = self.store.iter_messages(meta.session_id)
        contents = [m.content for m in it]
        self.assertEqual(contents, [f"msg {i}" for i in range(5)])

    def test_truncate_messages_keeps_only_selected_prefix(self):
        meta = self.store.create_session(title="New session")
        for role, content in [
            ("user", "first"), ("assistant", "done"),
            ("user", "second"), ("assistant", "done again"),
        ]:
            self.store.append_message(meta.session_id, role, content)

        retained = self.store.truncate_messages(meta.session_id, 2)

        loaded_meta, loaded = self.store.load_session(meta.session_id)
        self.assertEqual([message.content for message in retained], ["first", "done"])
        self.assertEqual([message.content for message in loaded], ["first", "done"])
        self.assertEqual(loaded_meta.message_count, 2)
        self.assertEqual(loaded_meta.status, "active")

    def test_truncate_messages_to_empty_resets_default_title(self):
        meta = self.store.create_session(title="New session")
        self.store.append_message(meta.session_id, "user", "old branch")

        self.store.truncate_messages(meta.session_id, 0)
        loaded_meta, loaded = self.store.load_session(meta.session_id)

        self.assertEqual(loaded, [])
        self.assertEqual(loaded_meta.message_count, 0)
        self.assertEqual(loaded_meta.title, "New session")

    def test_truncate_messages_rejects_out_of_range_boundary(self):
        meta = self.store.create_session()
        self.store.append_message(meta.session_id, "user", "hello")
        with self.assertRaises(ValueError):
            self.store.truncate_messages(meta.session_id, 2)

    # ── index persistence ────────────────────────────────────────────

    def test_index_file_is_rewritten_on_change(self):
        self.store.create_session(title="a")
        path = os.path.join(self.root, ".nexcoder", "sessions", "index.json")
        self.assertTrue(os.path.isfile(path))
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(len(data), 1)


class AtomicWriteJsonTests(unittest.TestCase):
    def test_writes_atomically(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "subdir", "out.json")
            _atomic_write_json(path, {"k": "v"})
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data, {"k": "v"})

    def test_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.json")
            _atomic_write_json(path, {"old": True})
            _atomic_write_json(path, {"new": True})
            with open(path, "r", encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), {"new": True})


if __name__ == "__main__":
    unittest.main()
