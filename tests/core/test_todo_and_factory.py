from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import ToolContext


def make_ctx(tmp_path, events):
    return ToolContext(project_root=tmp_path, emit=events.append, run_id="t")


def test_default_belt_has_all_tools():
    belt = build_default_belt()
    assert set(belt.names) == {
        "read_file", "edit_file", "write_file", "create_directory", "move_path",
        "list_directory", "glob", "grep", "run_command", "todo_write", "load_skill"}


def test_todo_write_updates_context_and_emits(tmp_path):
    belt = build_default_belt()
    events: list[AgentEvent] = []
    ctx = make_ctx(tmp_path, events)
    result = belt.execute("todo_write", {"todos": [
        {"content": "plan", "status": "completed"},
        {"content": "build", "status": "in_progress"}]}, ctx)
    assert result["success"]
    assert [t["status"] for t in ctx.todos] == ["completed", "in_progress"]
    updated = [e for e in events if e.type == "todo_updated"]
    assert updated and len(updated[0].payload["todos"]) == 2


def test_todo_write_rejects_bad_status(tmp_path):
    belt = build_default_belt()
    ctx = make_ctx(tmp_path, [])
    result = belt.execute("todo_write", {"todos": [{"content": "x", "status": "done"}]}, ctx)
    assert result["error_code"] == "invalid_args"


def test_load_skill_unknown(tmp_path):
    belt = build_default_belt()
    ctx = make_ctx(tmp_path, [])
    assert belt.execute("load_skill", {"id": "no-such-skill"}, ctx)["error_code"] == "skill_not_found"
