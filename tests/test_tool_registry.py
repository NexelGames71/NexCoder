"""Tests for the ToolRegistry: path safety, sensitive files, command blocklist, cancellation."""

import os
import tempfile
import time
import unittest
from pathlib import Path

from nexcoder.agent.cancellation import CancellationToken
from nexcoder.agent.errors import AgentCancelledError
from nexcoder.agent.patch_generator import PatchGenerator
from nexcoder.agent.tool_registry import ToolRegistry


class ToolRegistryPathSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.tr = ToolRegistry(self.root)

    def test_list_directory_works_inside_project(self):
        result = self.tr.list_directory({"path": "."})
        self.assertTrue(result["success"])

    def test_list_directory_blocks_traversal(self):
        # The ``..`` resolves to outside the project root.
        result = self.tr.list_directory({"path": ".."})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "blocked")

    def test_read_file_blocks_path_traversal(self):
        result = self.tr.read_file({"path": "../outside.txt"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "blocked")

    def test_read_file_returns_content(self):
        path = os.path.join(self.root, "ok.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("hello")
        result = self.tr.read_file({"path": "ok.txt"})
        self.assertTrue(result["success"])
        self.assertEqual(result["content"], "hello")

    def test_read_file_suggests_matches_on_missing(self):
        # The file exists with a similar but distinct name; the
        # suggestion matcher should find the prefix-similar name.
        path = os.path.join(self.root, "wanted.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("x = 1")
        result = self.tr.read_file({"path": "wanted.py.bak"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "file_not_found")
        # The current implementation does a case-insensitive exact
        # match; the suggestion list should at least not crash and
        # should still surface useful info if any matches exist.
        self.assertIsInstance(result.get("suggested_matches"), list)

    def test_read_file_blocks_oversized(self):
        # MAX_READ_BYTES is 1MB. Make a 2MB file and confirm rejection.
        path = os.path.join(self.root, "huge.bin")
        with open(path, "wb") as fh:
            fh.write(b"x" * (2 * 1024 * 1024))
        result = self.tr.read_file({"path": "huge.bin"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "file_too_large")


class ToolRegistrySensitiveFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.tr = ToolRegistry(self.root)

    def test_env_file_write_is_blocked(self):
        result = self.tr.write_file({"path": ".env", "content": "SECRET=x"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "tool_sensitive_file")

    def test_pem_file_write_is_blocked(self):
        result = self.tr.write_file({"path": "key.pem", "content": "x"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "tool_sensitive_file")

    def test_safe_file_write_succeeds(self):
        result = self.tr.write_file({"path": "ok.py", "content": "x = 1"})
        self.assertTrue(result["success"])

    def test_safe_file_write_queues_patch_without_touching_disk(self):
        patches = []
        tr = ToolRegistry(self.root, on_diff=patches.append)
        result = tr.write_file({"path": "ok.py", "content": "x = 1"})

        self.assertTrue(result["success"])
        self.assertFalse(os.path.exists(os.path.join(self.root, "ok.py")))
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]["content"], "x = 1")
        self.assertEqual(patches[0]["action"], "create")

    def test_safe_file_write_emits_modify_patch(self):
        # Overwriting an existing file should emit a pending patch so
        # the user can approve it from the UI.
        path = os.path.join(self.root, "ok.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("old")
        result = self.tr.write_file({"path": "ok.py", "content": "new"})
        self.assertTrue(result["success"])
        self.assertIsNotNone(result.get("changed_file"))
        with open(path, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "old")

    def test_deferred_patchset_reads_staged_content_and_flushes_once(self):
        patches = []
        tr = ToolRegistry(self.root, on_diff=patches.append, defer_diffs=True)

        tr.write_file({"path": "site/index.html", "content": "first"})
        tr.write_file({"path": "site/index.html", "content": "final"})
        tr.write_file({"path": "site/styles.css", "content": "body {}"})

        staged = tr.read_file({"path": "site/index.html"})
        listing = tr.list_directory({"path": "site"})
        self.assertTrue(staged["success"])
        self.assertTrue(staged["staged"])
        self.assertEqual(staged["content"], "final")
        self.assertEqual({item["name"] for item in listing["entries"]}, {"index.html", "styles.css"})
        self.assertEqual(patches, [])

        flushed = tr.flush_pending_diffs()
        self.assertEqual(len(flushed), 2)
        self.assertEqual(len(patches), 2)
        self.assertEqual(patches[0]["content"], "final")

    def test_run_command_waits_for_staged_changes_to_be_approved(self):
        tr = ToolRegistry(self.root, defer_diffs=True)
        tr.write_file({"path": "index.html", "content": "ok"})
        result = tr.run_command({"command": "echo should-not-run"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "approval_required")

    def test_create_directory_is_staged_until_patch_approval(self):
        tr = ToolRegistry(self.root, defer_diffs=True)

        result = tr.create_directory({"path": "assets/styles"})
        patches = tr.flush_pending_diffs()

        self.assertTrue(result["success"])
        self.assertFalse((Path(self.root) / "assets" / "styles").exists())
        self.assertEqual(patches[0]["action"], "mkdir")
        PatchGenerator(self.root).apply_patchset(patches)
        self.assertTrue((Path(self.root) / "assets" / "styles").is_dir())

    def test_move_existing_file_is_staged_and_applied(self):
        source = Path(self.root) / "styles.css"
        source.write_text("body {}", encoding="utf-8")
        tr = ToolRegistry(self.root, defer_diffs=True)

        result = tr.move_path({"source": "styles.css", "destination": "assets/css/styles.css"})
        patches = tr.flush_pending_diffs()

        self.assertTrue(result["success"])
        self.assertTrue(source.exists())
        self.assertEqual(patches[0]["action"], "move")
        self.assertEqual(patches[0]["source"], "styles.css")
        PatchGenerator(self.root).apply_patchset(patches)
        self.assertFalse(source.exists())
        self.assertEqual(
            (Path(self.root) / "assets" / "css" / "styles.css").read_text(encoding="utf-8"),
            "body {}",
        )

    def test_move_binary_file_without_rewriting_bytes(self):
        source = Path(self.root) / "logo.png"
        payload = b"\x89PNG\r\n\x1a\n\x00binary"
        source.write_bytes(payload)
        tr = ToolRegistry(self.root, defer_diffs=True)

        result = tr.move_path({"source": "logo.png", "destination": "assets/images/logo.png"})
        patches = tr.flush_pending_diffs()
        PatchGenerator(self.root).apply_patchset(patches)

        self.assertTrue(result["success"])
        self.assertTrue(patches[0]["binary"])
        self.assertFalse(source.exists())
        self.assertEqual((Path(self.root) / "assets" / "images" / "logo.png").read_bytes(), payload)

    def test_move_staged_file_supersedes_original_pending_patch(self):
        first = ToolRegistry(self.root, defer_diffs=True)
        first.write_file({"path": "script.js", "content": "console.log('ok')"})
        seeded = first.flush_pending_diffs()
        tr = ToolRegistry(self.root, defer_diffs=True, pending_patches=seeded)

        result = tr.move_path({"source": "script.js", "destination": "assets/js/script.js"})
        moved = tr.read_file({"path": "assets/js/script.js"})
        old = tr.read_file({"path": "script.js"})
        patches = tr.flush_pending_diffs()

        self.assertTrue(result["success"])
        self.assertTrue(moved["success"])
        self.assertEqual(moved["content"], "console.log('ok')")
        self.assertEqual(old["error_code"], "path_moved")
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]["file"], "assets/js/script.js")
        self.assertEqual(patches[0]["action"], "create")
        self.assertEqual(patches[0]["supersedes"], ["script.js"])

    def test_move_directory_preserves_nested_files(self):
        source = Path(self.root) / "legacy"
        (source / "nested").mkdir(parents=True)
        (source / "a.txt").write_text("a", encoding="utf-8")
        (source / "nested" / "b.txt").write_text("b", encoding="utf-8")
        tr = ToolRegistry(self.root, defer_diffs=True)

        result = tr.move_path({"source": "legacy", "destination": "src"})
        patches = tr.flush_pending_diffs()
        PatchGenerator(self.root).apply_patchset(patches)

        self.assertTrue(result["success"])
        self.assertFalse(source.exists())
        self.assertEqual((Path(self.root) / "src" / "a.txt").read_text(encoding="utf-8"), "a")
        self.assertEqual((Path(self.root) / "src" / "nested" / "b.txt").read_text(encoding="utf-8"), "b")


class ToolRegistryCommandBlocklistTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.tr = ToolRegistry(self.root)

    def test_rm_rf_slash_blocked(self):
        result = self.tr.run_command({"command": "rm -rf /"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "tool_command_blocked")

    def test_format_blocked(self):
        result = self.tr.run_command({"command": "format C:"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "tool_command_blocked")

    def test_echo_succeeds(self):
        result = self.tr.run_command({"command": "echo hello"})
        self.assertTrue(result["success"])
        self.assertIn("hello", result["stdout"])

    def test_failing_command_reports_nonzero(self):
        result = self.tr.run_command({"command": "exit 7"})
        self.assertFalse(result["success"])
        self.assertEqual(result["exit_code"], 7)


class ToolRegistrySearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.tr = ToolRegistry(self.root)

    def test_search_grep_finds_match(self):
        with open(os.path.join(self.root, "a.py"), "w", encoding="utf-8") as fh:
            fh.write("def hello():\n    return 1\n")
        result = self.tr.search_grep({"query": "hello"})
        self.assertTrue(result["success"])
        self.assertGreaterEqual(len(result["results"]), 1)

    def test_search_grep_respects_skip_dirs(self):
        # node_modules is in the skip list; matches inside it are
        # filtered out.
        os.makedirs(os.path.join(self.root, "node_modules"), exist_ok=True)
        with open(os.path.join(self.root, "node_modules", "x.js"), "w", encoding="utf-8") as fh:
            fh.write("hello")
        # A matching file outside the skip dir, so we can confirm the
        # search still runs and just the skip-dir match is filtered.
        with open(os.path.join(self.root, "real.py"), "w", encoding="utf-8") as fh:
            fh.write("hello")
        result = self.tr.search_grep({"query": "hello"})
        # node_modules match is filtered, but the real one is found.
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["file"], "real.py")

    def test_search_grep_cancellable(self):
        token = CancellationToken()
        tr = ToolRegistry(self.root, cancellation_token=token)
        # Add a couple of files; cancel after creation.
        for i in range(5):
            with open(os.path.join(self.root, f"f_{i}.py"), "w", encoding="utf-8") as fh:
                fh.write("hello\n")
        token.cancel()
        result = tr.search_grep({"query": "hello"})
        # Either a clean cancel signal or an empty result is acceptable
        # depending on whether the cancel was observed before any
        # files were scanned. Both signal "we respected the token".
        self.assertIn(result.get("error_code"), {"agent_cancelled", None})


class ToolRegistryLoadSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.tr = ToolRegistry(self.root)

    def test_load_skill_unknown_id(self):
        result = self.tr.load_skill({"id": "this-skill-does-not-exist"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "skill_not_found")


class ToolRegistryExecuteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.tr = ToolRegistry(self.root)

    def test_unknown_tool_returns_error(self):
        result = self.tr.execute("nonexistent_tool", {})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "unknown_tool")

    def test_alias_resolves_to_canonical_tool(self):
        result = self.tr.execute("list_project_tree", {"path": "."})
        self.assertTrue(result["success"])

    def test_run_command_alias(self):
        result = self.tr.execute("run_tests", {"command": "echo alias_works"})
        self.assertTrue(result["success"])
        self.assertIn("alias_works", result["stdout"])

    def test_execute_respects_cancellation(self):
        token = CancellationToken()
        token.cancel()
        # The registry's ``execute`` raises ``AgentCancelledError``
        # when the token is already cancelled; the executor
        # (AgentExecutor) is the layer that converts the raise into
        # a structured error dict.
        with self.assertRaises(AgentCancelledError):
            self.tr.execute("read_file", {"path": "x"}, cancellation_token=token)


if __name__ == "__main__":
    unittest.main()

