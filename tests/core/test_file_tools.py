from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import ToolBelt, ToolContext
from nexcoder.agent.core.tools.files import register_file_tools


def make(tmp_path):
    events: list[AgentEvent] = []
    belt = ToolBelt()
    register_file_tools(belt)
    ctx = ToolContext(project_root=tmp_path, emit=events.append, run_id="t")
    return belt, ctx, events


def test_read_file_with_offset_limit(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"l1\nl2\nl3\nl4\n")  # bytes: no CRLF translation
    belt, ctx, _ = make(tmp_path)
    result = belt.execute("read_file", {"path": "a.txt", "offset": 2, "limit": 2}, ctx)
    assert result["success"] and result["content"] == "l2\nl3"
    assert result["total_lines"] == 4
    full = belt.execute("read_file", {"path": "a.txt"}, ctx)
    assert full["content"] == "l1\nl2\nl3\nl4\n"


def test_read_file_not_found_and_escape(tmp_path):
    belt, ctx, _ = make(tmp_path)
    assert belt.execute("read_file", {"path": "nope.txt"}, ctx)["error_code"] == "file_not_found"
    assert belt.execute("read_file", {"path": "../x"}, ctx)["error_code"] == "blocked"


def test_edit_file_replaces_and_snapshots(tmp_path):
    (tmp_path / "m.py").write_text("def old():\n    return 1\n", encoding="utf-8")
    belt, ctx, events = make(tmp_path)
    result = belt.execute("edit_file", {
        "path": "m.py", "old_string": "def old():", "new_string": "def new():"}, ctx)
    assert result["success"] and result["replacements"] == 1
    assert (tmp_path / "m.py").read_text(encoding="utf-8") == "def new():\n    return 1\n"
    assert "m.py" in ctx.mutated_files and ctx.checkpoint_id
    assert any(e.type == "edit_applied" for e in events)


def test_edit_file_error_codes(tmp_path):
    (tmp_path / "d.txt").write_text("aa bb aa", encoding="utf-8")
    belt, ctx, _ = make(tmp_path)
    assert belt.execute("edit_file", {"path": "d.txt", "old_string": "zz",
                        "new_string": "q"}, ctx)["error_code"] == "not_found_in_file"
    assert belt.execute("edit_file", {"path": "d.txt", "old_string": "aa",
                        "new_string": "q"}, ctx)["error_code"] == "ambiguous_match"
    assert belt.execute("edit_file", {"path": "d.txt", "old_string": "bb",
                        "new_string": "bb"}, ctx)["error_code"] == "no_change"
    ok = belt.execute("edit_file", {"path": "d.txt", "old_string": "aa",
                      "new_string": "q", "replace_all": True}, ctx)
    assert ok["success"] and ok["replacements"] == 2
    assert (tmp_path / "d.txt").read_text(encoding="utf-8") == "q bb q"


def test_edit_file_preserves_crlf(tmp_path):
    (tmp_path / "w.txt").write_bytes(b"one\r\ntwo\r\n")
    belt, ctx, _ = make(tmp_path)
    result = belt.execute("edit_file", {"path": "w.txt", "old_string": "two",
                          "new_string": "2"}, ctx)
    assert result["success"]
    assert (tmp_path / "w.txt").read_bytes() == b"one\r\n2\r\n"


def test_write_file_creates_parents_and_snapshots(tmp_path):
    belt, ctx, _ = make(tmp_path)
    result = belt.execute("write_file", {"path": "sub/new.txt", "content": "hello"}, ctx)
    assert result["success"]
    assert (tmp_path / "sub" / "new.txt").read_text(encoding="utf-8") == "hello"
    assert "sub/new.txt" in ctx.mutated_files


def test_write_file_sensitive_blocked(tmp_path):
    belt, ctx, _ = make(tmp_path)
    result = belt.execute("write_file", {"path": ".env", "content": "X=1"}, ctx)
    assert result["error_code"] == "tool_sensitive_file"


def test_move_and_mkdir_and_list(tmp_path):
    (tmp_path / "src.txt").write_text("s", encoding="utf-8")
    belt, ctx, _ = make(tmp_path)
    assert belt.execute("create_directory", {"path": "pkg"}, ctx)["success"]
    result = belt.execute("move_path", {"source": "src.txt", "destination": "pkg/dst.txt"}, ctx)
    assert result["success"]
    assert (tmp_path / "pkg" / "dst.txt").exists() and not (tmp_path / "src.txt").exists()
    listing = belt.execute("list_directory", {"path": "."}, ctx)
    names = [e["name"] for e in listing["entries"]]
    assert "pkg" in names
    assert belt.execute("move_path", {"source": ".git/x", "destination": "y"}, ctx)["error_code"] == "blocked"
