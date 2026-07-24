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


def test_grep_accepts_a_file_path(tmp_path):
    (tmp_path / "main.py").write_text("def generate_world():\n    pass\n", encoding="utf-8")
    belt, ctx = make(tmp_path)
    result = belt.execute(
        "grep", {"path": "main.py", "pattern": "generate_world"}, ctx)
    assert result["success"]
    assert result["results"] == [{
        "file": "main.py", "line": 1, "content": "def generate_world():"}]


def test_grep_double_star_glob_matches_top_level_and_nested_files(tmp_path):
    (tmp_path / "main.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "nested.py").write_text("needle\n", encoding="utf-8")
    belt, ctx = make(tmp_path)
    result = belt.execute(
        "grep", {"pattern": "needle", "glob": "**/*.py"}, ctx)
    assert result["success"]
    assert {item["file"] for item in result["results"]} == {
        "main.py", "src/nested.py"}


def test_grep_invalid_regex(tmp_path):
    belt, ctx = make(tmp_path)
    assert belt.execute("grep", {"pattern": "("}, ctx)["error_code"] == "invalid_args"


def test_code_search_ranks_path_and_dense_matches(tmp_path):
    (tmp_path / "auth_service.py").write_text(
        "class TokenValidator:\n    def validate_token(self):\n        return True\n",
        encoding="utf-8",
    )
    (tmp_path / "unrelated.py").write_text(
        "def token():\n    return 'single mention'\n", encoding="utf-8")
    belt, ctx = make(tmp_path)
    result = belt.execute(
        "code_search", {"query": "token validation auth", "max_results": 5}, ctx)
    assert result["success"]
    assert result["results"][0]["file"] == "auth_service.py"
    assert result["results"][0]["snippets"]


def test_code_search_accepts_a_file_path(tmp_path):
    (tmp_path / "main.py").write_text(
        "def generate_terrain():\n    return 'smooth terrain'\n", encoding="utf-8")
    belt, ctx = make(tmp_path)
    result = belt.execute(
        "code_search", {"query": "smooth terrain", "path": "main.py"}, ctx)
    assert result["success"]
    assert result["scanned_files"] == 1
    assert result["results"][0]["file"] == "main.py"


def test_code_search_rejects_empty_query_and_skips_dependencies(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "auth.py").write_text("secret auth", encoding="utf-8")
    belt, ctx = make(tmp_path)
    assert belt.execute("code_search", {"query": "the and"}, ctx)["error_code"] == "invalid_args"
    result = belt.execute("code_search", {"query": "secret auth"}, ctx)
    assert result["results"] == []
