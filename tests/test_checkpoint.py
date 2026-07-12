"""Tests for the CheckpointManager: create, restore, list, cleanup."""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path


class CheckpointManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

        # Lazy import so the test does not depend on the import-time
        # path being set up the way the rest of the app expects.
        from nexcoder.services.checkpoint import CheckpointManager

        self.CheckpointManager = CheckpointManager
        self.cm = CheckpointManager(self.root)

    def _write(self, rel: str, content: str) -> str:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    # ── create ───────────────────────────────────────────────────────

    def test_create_returns_id(self):
        self._write("a.py", "x = 1")
        cid = self.cm.create([os.path.join(self.root, "a.py")], label="test")
        self.assertTrue(cid)
        # The id is a timestamp-like string.
        self.assertTrue(cid.isdigit())

    def test_create_writes_manifest(self):
        path = self._write("a.py", "x = 1")
        cid = self.cm.create([path], label="test")
        manifest_path = os.path.join(
            self.root, ".nexcoder", "checkpoints", cid, "manifest.json"
        )
        self.assertTrue(os.path.isfile(manifest_path))
        with open(manifest_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["label"], "test")
        self.assertEqual(len(data["files"]), 1)

    def test_create_records_missing_files_for_rollback(self):
        # Missing targets are recorded so rollback can remove files that
        # were newly created after the checkpoint.
        path = self._write("real.py", "x = 1")
        cid = self.cm.create(
            [path, os.path.join(self.root, "ghost.py")],
            label="mixed",
        )
        with open(
            os.path.join(self.root, ".nexcoder", "checkpoints", cid, "manifest.json"),
            "r", encoding="utf-8",
        ) as fh:
            data = json.load(fh)
        self.assertEqual(len(data["files"]), 2)
        ghost = next(item for item in data["files"] if item["relative"] == "ghost.py")
        self.assertFalse(ghost["existed"])

    def test_create_with_no_project_root_raises(self):
        with self.assertRaises(ValueError):
            self.CheckpointManager(None).create([], label="x")

    # ── list ─────────────────────────────────────────────────────────

    def test_list_empty(self):
        self.assertEqual(self.cm.list_checkpoints(), [])

    def test_list_returns_created_checkpoints(self):
        a = self._write("a.py", "x = 1")
        b = self._write("b.py", "y = 2")
        cid_a = self.cm.create([a])
        cid_b = self.cm.create([b])
        listed = self.cm.list_checkpoints()
        ids = {entry["id"] for entry in listed}
        self.assertEqual(ids, {cid_a, cid_b})

    # ── restore ──────────────────────────────────────────────────────

    def test_restore_round_trip(self):
        path = self._write("a.py", "original")
        cid = self.cm.create([path], label="snap")
        # Modify the file.
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("modified")
        # Restore.
        result = self.cm.restore(cid)
        # The restored list uses forward-slash paths internally; check
        # by the trailing path component to be cross-platform safe.
        self.assertTrue(
            any(r.replace("\\", "/").endswith("/a.py") for r in result["restored"]),
            f"a.py not in restored list: {result['restored']}",
        )
        with open(path, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "original")

    def test_restore_specific_files(self):
        a = self._write("a.py", "a-original")
        b = self._write("b.py", "b-original")
        cid = self.cm.create([a, b])
        with open(a, "w", encoding="utf-8") as fh:
            fh.write("a-modified")
        with open(b, "w", encoding="utf-8") as fh:
            fh.write("b-modified")
        # Restore only ``a``.
        a_norm = a.replace("\\", "/")
        self.cm.restore(cid, files=[a_norm])
        with open(a, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "a-original")
        with open(b, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "b-modified")

    def test_restore_removes_file_created_after_checkpoint(self):
        new_file = os.path.join(self.root, "created.py")
        cid = self.cm.create([new_file], label="before-create")
        self._write("created.py", "new content")
        self.assertTrue(os.path.isfile(new_file))

        self.cm.restore(cid, files=[new_file])

        self.assertFalse(os.path.exists(new_file))

    def test_restore_removes_directory_created_after_checkpoint(self):
        new_directory = os.path.join(self.root, "generated", "assets")
        cid = self.cm.create([new_directory], label="before-directory-create")
        os.makedirs(new_directory)

        self.cm.restore(cid, files=[new_directory])

        self.assertFalse(os.path.exists(new_directory))

    def test_restore_missing_checkpoint_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.cm.restore("nonexistent-id")

    # ── delete ───────────────────────────────────────────────────────

    def test_delete_removes_checkpoint(self):
        path = self._write("a.py", "x = 1")
        cid = self.cm.create([path])
        self.assertTrue(self.cm.delete(cid))
        # restore should now fail.
        with self.assertRaises(FileNotFoundError):
            self.cm.restore(cid)

    def test_delete_missing_is_noop(self):
        # No exception even if id doesn't exist (rmtree with
        # ignore_errors=True).
        self.cm.delete("never-existed")

    # ── cleanup ──────────────────────────────────────────────────────

    def test_cleanup_removes_oldest(self):
        from nexcoder.services.checkpoint import MAX_CHECKPOINTS

        # Create more than the cap; oldest should be evicted.
        for i in range(MAX_CHECKPOINTS + 3):
            path = self._write(f"f_{i}.py", f"x = {i}")
            self.cm.create([path], label=f"cp_{i}")
            # Force distinct timestamps so eviction order is stable.
            time.sleep(0.002)
        listed = self.cm.list_checkpoints()
        self.assertLessEqual(len(listed), MAX_CHECKPOINTS)


if __name__ == "__main__":
    unittest.main()
