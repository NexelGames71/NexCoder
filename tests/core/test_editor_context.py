from nexcoder.agent.core.editor_context import (
    MAX_HISTORY_MESSAGES, MAX_SELECTION_CHARS,
    render_chat_history, render_editor_context,
)


def test_empty_context_renders_nothing():
    assert render_editor_context(None) == ""
    assert render_editor_context({}) == ""
    assert render_editor_context({"active_file": "", "selection": None}) == ""
    assert render_editor_context({"selection": {"text": "   "}}) == ""


def test_active_file_only():
    out = render_editor_context({"active_file": "src/app.py"})
    assert "Active file: src/app.py" in out
    assert "Editor context" in out
    assert "Selected code" not in out


def test_selection_with_lines_and_path():
    out = render_editor_context({
        "active_file": "src/app.py",
        "selection": {"path": "src/app.py", "start_line": 3,
                      "end_line": 5, "text": "def f():\n    pass"},
    })
    assert "Selected code in src/app.py (lines 3-5):" in out
    assert "def f():" in out


def test_bare_string_selection_from_legacy_callers():
    out = render_editor_context({"selection": "x = 1"})
    assert "Selected code:" in out
    assert "x = 1" in out


def test_paths_become_project_relative(tmp_path):
    target = tmp_path / "pkg" / "mod.py"
    out = render_editor_context(
        {"active_file": str(target)}, project_root=tmp_path)
    assert "Active file: pkg/mod.py" in out
    # Paths outside the project pass through untouched.
    out = render_editor_context(
        {"active_file": "C:/elsewhere/x.py"}, project_root=tmp_path)
    assert "x.py" in out


def test_long_selection_truncates():
    out = render_editor_context({"selection": {"text": "a" * 10_000}})
    assert "(selection truncated)" in out
    assert len(out) < MAX_SELECTION_CHARS + 400


def test_chat_history_empty_and_junk():
    assert render_chat_history(None) == ""
    assert render_chat_history([]) == ""
    assert render_chat_history([{"role": "system", "content": "x"},
                                {"role": "user", "content": "  "}]) == ""


def test_chat_history_renders_recent_exchanges():
    out = render_chat_history([
        {"role": "user", "content": "add a parser"},
        {"role": "assistant", "content": "Done: parser.py created."},
    ])
    assert out.startswith("--- Prior conversation")
    assert "User: add a parser" in out
    assert "Assistant: Done: parser.py created." in out
    assert out.rstrip().endswith("--- Current request ---")


def test_chat_history_caps_message_count_and_length():
    many = [{"role": "user", "content": f"msg {i} " + "x" * 2000}
            for i in range(20)]
    out = render_chat_history(many)
    assert out.count("User:") == MAX_HISTORY_MESSAGES
    assert "msg 19" in out and "msg 5" not in out
    assert "…(truncated)" in out
