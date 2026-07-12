import os
import time

from nexcoder.agent.core.tools.base import ToolBelt, ToolContext
from nexcoder.agent.core.tools.search import register_search_tools


def make(tmp_path):
    belt = ToolBelt()
    register_search_tools(belt)
    return belt, ToolContext(project_root=tmp_path, emit=lambda _e: None, run_id="t")


def test_glob_matches_and_sorts_by_recency(tmp_path):
    (tmp_path / "old.py").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "new.py").write_text("y", encoding="utf-8")
    (tmp_path / "readme.md").write_text("z", encoding="utf-8")
    past = time.time() - 1000
    os.utime(tmp_path / "old.py", (past, past))
    belt, ctx = make(tmp_path)
    result = belt.execute("glob", {"pattern": "**/*.py"}, ctx)
    assert result["success"]
    assert result["files"] == ["sub/new.py", "old.py"]


def test_glob_skips_filtered_dirs(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.py").write_text("d", encoding="utf-8")
    (tmp_path / "app.py").write_text("a", encoding="utf-8")
    belt, ctx = make(tmp_path)
    assert belt.execute("glob", {"pattern": "**/*.py"}, ctx)["files"] == ["app.py"]


def test_grep_regex_with_glob_filter(tmp_path):
    (tmp_path / "a.py").write_text("def alpha():\n    pass\n", encoding="utf-8")
    (tmp_path / "b.ts").write_text("function alpha() {}\n", encoding="utf-8")
    belt, ctx = make(tmp_path)
    result = belt.execute("grep", {"pattern": r"def \w+", "glob": "*.py"}, ctx)
    assert result["success"]
    assert result["results"] == [{"file": "a.py", "line": 1, "content": "def alpha():"}]


def test_grep_invalid_regex(tmp_path):
    belt, ctx = make(tmp_path)
    assert belt.execute("grep", {"pattern": "("}, ctx)["error_code"] == "invalid_args"
