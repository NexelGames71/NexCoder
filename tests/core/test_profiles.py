import pytest

from nexcoder.agent.core.profiles import (
    V2Profile, build_belt_for, get_v2_profile,
)


def test_all_modes_exist():
    for mode in ("agent", "plan", "ask", "edit", "debug", "review",
                 "scan", "terminal"):
        profile = get_v2_profile(mode)
        assert isinstance(profile, V2Profile)
        assert profile.system_prompt.strip()
        assert profile.max_turns >= 4


def test_scan_persists_architecture_to_memory():
    # Scan mode must save what it learned so future runs start warm.
    prompt = get_v2_profile("scan").system_prompt
    assert "remember" in prompt


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        get_v2_profile("nonsense")


def test_read_only_modes_have_no_mutating_tools():
    for mode in ("ask", "plan", "review", "scan"):
        belt = build_belt_for(get_v2_profile(mode))
        names = set(belt.names)
        assert not names & {"write_file", "edit_file", "run_command",
                            "create_directory", "move_path"}, mode
        assert {"read_file", "grep", "glob", "code_search"} <= names, mode


def test_write_modes_have_full_belt():
    for mode in ("agent", "edit", "debug", "terminal"):
        belt = build_belt_for(get_v2_profile(mode))
        names = set(belt.names)
        assert {"read_file", "edit_file", "write_file", "run_command",
                "todo_write"} <= names, mode


def test_disabled_tools_are_removed_but_reads_survive(monkeypatch):
    monkeypatch.setenv("NEXCODER_DISABLED_TOOLS",
                       "run_command,write_file,read_file")
    belt = build_belt_for(get_v2_profile("agent"))
    names = set(belt.names)
    assert "run_command" not in names
    assert "write_file" not in names
    # Core read tools can never be disabled.
    assert "read_file" in names


def test_read_only_belt_rejects_write(tmp_path):
    from nexcoder.agent.core.tools.base import ToolContext
    belt = build_belt_for(get_v2_profile("ask"))
    ctx = ToolContext(project_root=tmp_path, emit=lambda _e: None, run_id="t")
    result = belt.execute("write_file", {"path": "x.txt", "content": "no"}, ctx)
    assert result["error_code"] == "unknown_tool"
    assert not (tmp_path / "x.txt").exists()
