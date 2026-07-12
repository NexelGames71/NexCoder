"""Tests for the token-aware context builder."""

import os
import tempfile
import unittest
from pathlib import Path

from nexcoder.agent.context.token_builder import TokenAwareContextBuilder


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


class TokenAwareContextBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    # ── Token counting ───────────────────────────────────────────────

    def test_count_tokens_returns_positive_for_text(self):
        b = TokenAwareContextBuilder()
        self.assertGreater(b.count_tokens("hello world"), 0)

    def test_count_tokens_zero_for_empty(self):
        b = TokenAwareContextBuilder()
        self.assertEqual(b.count_tokens(""), 0)

    # ── Project structure block ──────────────────────────────────────

    def test_empty_project_returns_empty_context(self):
        b = TokenAwareContextBuilder()
        out = b.build({}, project_root=self.root)
        # No files → no structure block, no related files.
        self.assertEqual(out, "")

    def test_includes_project_structure(self):
        _write(os.path.join(self.root, "README.md"), "# Title")
        _write(os.path.join(self.root, "src", "main.py"), "print('hi')")
        b = TokenAwareContextBuilder()
        out = b.build({}, project_root=self.root)
        self.assertIn("Project Structure", out)
        self.assertIn("README.md", out)
        self.assertIn("src/", out)

    def test_skips_node_modules_and_venv(self):
        _write(os.path.join(self.root, "node_modules", "lib.js"), "// skip me")
        _write(os.path.join(self.root, "venv", "x.py"), "# skip me")
        _write(os.path.join(self.root, "real.py"), "# keep me")
        b = TokenAwareContextBuilder()
        out = b.build({}, project_root=self.root)
        self.assertIn("real.py", out)
        self.assertNotIn("node_modules", out)
        self.assertNotIn("venv", out)

    # ── Current file block ───────────────────────────────────────────

    def test_current_file_appears_in_context(self):
        path = os.path.join(self.root, "app.py")
        _write(path, "def hello():\n    return 1\n")
        b = TokenAwareContextBuilder()
        out = b.build(
            {"currentFile": path, "currentContent": "def hello():\n    return 1\n"},
            project_root=self.root,
        )
        self.assertIn("Current File", out)
        self.assertIn("app.py", out)
        self.assertIn("def hello", out)

    # ── Budget enforcement ───────────────────────────────────────────

    def test_budget_drops_low_priority_content(self):
        # Write three big related files (well over the budget).
        # The project structure block is a separate priority, so
        # give the related files a high enough budget to win.
        for i in range(3):
            content = "# keyword: tokenization\n" * 50
            _write(os.path.join(self.root, f"file_{i}.py"), content)
        b = TokenAwareContextBuilder(max_tokens=2000, related_file_cap=600)
        out = b.build(
            {"prompt": "explain tokenization in the codebase"},
            project_root=self.root,
        )
        # The output must fit the budget.
        self.assertLessEqual(b.count_tokens(out), b.max_tokens + 50)
        # Some related file got picked; the budget enforced.
        self.assertIn("Related File", out)

    def test_per_block_cap_truncates_huge_files(self):
        # Single big file (well over the per-block cap). The prompt
        # needs to mention a word that actually appears in the file
        # content so the keyword-overlap ranking picks it up. The
        # broad-scan trigger ("codebase") alone isn't enough — the
        # builder also scores by relevance.
        huge = "# padding line\n" * 5000
        path = os.path.join(self.root, "padding.py")
        _write(path, huge)
        b = TokenAwareContextBuilder(
            max_tokens=4000, related_file_cap=500,
        )
        out = b.build(
            {"prompt": "look at the padding in the codebase"},
            project_root=self.root,
        )
        # The huge file would otherwise blow the budget; the marker
        # tells the model the content was cut.
        self.assertIn("[truncated", out)
        self.assertLessEqual(b.count_tokens(out), b.max_tokens + 50)

    def test_priority_ordering_favors_current_file(self):
        # Create a related file and a current file. Current file wins
        # at priority 70, related at 50 — so the current file should
        # always make it in even if the related file is huge.
        _write(os.path.join(self.root, "related.py"), "x = 1\n" * 1000)
        current_content = "current = True\n"
        current_path = os.path.join(self.root, "current.py")
        _write(current_path, current_content)
        b = TokenAwareContextBuilder(max_tokens=200, related_file_cap=50)
        out = b.build(
            {
                "currentFile": current_path,
                "currentContent": current_content,
                "prompt": "explain the codebase",  # forces broad scan
            },
            project_root=self.root,
        )
        self.assertIn("Current File", out)
        # The huge related file should NOT make it in under a tight budget.
        self.assertNotIn("Related File", out)

    # ── Selection & error output ─────────────────────────────────────

    def test_selection_appears(self):
        b = TokenAwareContextBuilder()
        out = b.build(
            {"selection": "foo.bar()", "cursorLine": 42},
            project_root=self.root,
        )
        self.assertIn("Selected Code", out)
        self.assertIn("foo.bar()", out)
        self.assertIn("line 42", out)

    def test_error_output_appears(self):
        b = TokenAwareContextBuilder()
        out = b.build(
            {"errorOutput": "Traceback: boom"},
            project_root=self.root,
        )
        self.assertIn("Error Output", out)
        self.assertIn("Traceback: boom", out)

    # ── Auto-retrieval ───────────────────────────────────────────────

    def test_short_prompt_does_not_trigger_broad_scan(self):
        _write(os.path.join(self.root, "auth.py"), "def authenticate(): pass")
        b = TokenAwareContextBuilder()
        out = b.build({"prompt": "hi"}, project_root=self.root)
        self.assertNotIn("Related File", out)

    def test_relevant_files_ranked_higher(self):
        _write(
            os.path.join(self.root, "auth.py"),
            "def authenticate(): return True",
        )
        _write(
            os.path.join(self.root, "utils.py"),
            "def format_date(): return ''",
        )
        b = TokenAwareContextBuilder(max_tokens=2000)
        out = b.build(
            {"prompt": "how does the authentication flow work"},
            project_root=self.root,
        )
        # The auth file matches the prompt; utils does not. We expect
        # the auth file to be packed before any non-matching ones.
        self.assertIn("auth.py", out)

    # ── on_file_read callback ────────────────────────────────────────

    def test_on_file_read_called_for_picked_files(self):
        # Two files: one matches the prompt keywords, one doesn't.
        # (The keyword overlap is exact substring; the file content
        # has to literally contain the words from the prompt.)
        _write(
            os.path.join(self.root, "auth.py"),
            "# authentication module\n"
            "def authenticate_user(): return True\n",
        )
        _write(
            os.path.join(self.root, "utils.py"),
            "def format_date(): return ''",
        )
        seen: list[str] = []
        b = TokenAwareContextBuilder()
        # ``on_file_read`` is a kwarg on ``build`` (matches the
        # legacy ContextBuilder signature) — not a context key.
        b.build(
            {
                # "codebase" forces the broad scan to run; the
                # "authentication" word ranks ``auth.py`` highest.
                "prompt": "explain the authentication flow in the codebase",
            },
            project_root=self.root,
            on_file_read=lambda n: seen.append(n),
        )
        # ``auth.py`` matches the prompt — it should be picked and
        # ``on_file_read`` should be called at least once.
        self.assertIn("auth.py", seen)

    # ── Explicit relatedFiles override ──────────────────────────────

    def test_explicit_related_files_are_picked(self):
        path = os.path.join(self.root, "manual.py")
        _write(path, "manual = True")
        b = TokenAwareContextBuilder()
        out = b.build(
            {"relatedFiles": [path], "prompt": "anything"},
            project_root=self.root,
        )
        self.assertIn("Related File", out)
        self.assertIn("manual.py", out)


if __name__ == "__main__":
    unittest.main()