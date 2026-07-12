from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import AllowAllGate, ToolBelt, ToolContext, ToolSpec


def make_ctx(tmp_path, events=None):
    return ToolContext(
        project_root=tmp_path,
        emit=(events.append if events is not None else (lambda _e: None)),
        run_id="run_test",
    )


def test_belt_registers_and_executes(tmp_path):
    def hello(args, ctx):
        return {"success": True, "greeting": f"hi {args['name']}"}

    belt = ToolBelt()
    belt.register(ToolSpec(
        name="hello", description="Say hi",
        parameters={"type": "object", "properties": {"name": {"type": "string"}},
                    "required": ["name"]},
        handler=hello))
    result = belt.execute("hello", {"name": "world"}, make_ctx(tmp_path))
    assert result == {"success": True, "greeting": "hi world"}
    assert belt.names == ("hello",)
    schema = belt.schemas()[0]
    assert schema["function"]["name"] == "hello"


def test_belt_unknown_tool_and_exception_are_error_results(tmp_path):
    def boom(args, ctx):
        raise RuntimeError("kaboom")

    belt = ToolBelt()
    belt.register(ToolSpec(name="boom", description="", parameters={"type": "object", "properties": {}}, handler=boom))
    assert belt.execute("nope", {}, make_ctx(tmp_path))["error_code"] == "unknown_tool"
    result = belt.execute("boom", {}, make_ctx(tmp_path))
    assert result["success"] is False
    assert result["error_code"] == "tool_exception"
    assert "kaboom" in result["error"]


def test_context_resolve_blocks_escape(tmp_path):
    ctx = make_ctx(tmp_path)
    assert ctx.resolve("sub/file.txt") is not None
    assert ctx.resolve("..") is None
    assert ctx.resolve("../outside.txt") is None


def test_snapshot_before_mutation_creates_then_extends_checkpoint(tmp_path):
    (tmp_path / "one.txt").write_text("1", encoding="utf-8")
    (tmp_path / "two.txt").write_text("2", encoding="utf-8")
    events: list[AgentEvent] = []
    ctx = make_ctx(tmp_path, events)
    ctx.snapshot_before_mutation("one.txt")
    first_id = ctx.checkpoint_id
    assert first_id is not None
    ctx.snapshot_before_mutation("two.txt")
    ctx.snapshot_before_mutation("one.txt")  # no-op
    assert ctx.checkpoint_id == first_id
    assert ctx.mutated_files == {"one.txt", "two.txt"}
    assert [e.type for e in events] == ["checkpoint_created"]
