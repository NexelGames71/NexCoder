from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.loop import AgentLoop
from nexcoder.agent.core.transport import XmlAdapter


class FakeModel:
    """Scripted ModelClient: returns queued assistant messages in order."""

    def __init__(self, messages):
        self.queue = list(messages)
        self.received: list[list[dict]] = []

    def complete(self, messages, *, extras, on_delta=None):
        self.received.append(messages)
        message = self.queue.pop(0) if self.queue else {"role": "assistant", "content": "done"}
        if on_delta and message.get("content"):
            on_delta(message["content"])
        return message


def xml_call(tool, args_json):
    return {"role": "assistant",
            "content": f'<tool_call name="{tool}">{args_json}</tool_call>'}


def make_loop(tmp_path, model, **kwargs):
    events: list[AgentEvent] = []
    loop = AgentLoop(
        project_root=tmp_path, model=model, adapter=XmlAdapter(),
        belt=build_default_belt(), system_prompt="You are a test agent.",
        emit=events.append, **kwargs)
    return loop, events


def test_loop_executes_tools_then_finishes(tmp_path):
    (tmp_path / "hello.txt").write_text("world", encoding="utf-8")
    model = FakeModel([
        xml_call("read_file", '{"path": "hello.txt"}'),
        {"role": "assistant", "content": "The file says world."},
    ])
    loop, events = make_loop(tmp_path, model)
    result = loop.run("what does hello.txt say?")
    assert result["success"] and result["status"] == "completed"
    assert result["final_text"] == "The file says world."
    assert result["turns"] == 2
    types = [e.type for e in events]
    assert "run_started" in types and "tool_started" in types
    assert "tool_result" in types and "run_completed" in types
    # Tool result was fed back to the model as a tool_response user message
    second_request = model.received[1]
    assert any("<tool_response>" in str(m.get("content")) for m in second_request)


def test_loop_edit_creates_checkpoint_and_reports_mutations(tmp_path):
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    model = FakeModel([
        xml_call("edit_file", '{"path": "a.py", "old_string": "x = 1", "new_string": "x = 2"}'),
        {"role": "assistant", "content": "Changed x to 2."},
    ])
    loop, _ = make_loop(tmp_path, model)
    result = loop.run("set x to 2")
    assert (tmp_path / "a.py").read_bytes() == b"x = 2\n"
    assert result["mutated_files"] == ["a.py"]
    assert result["checkpoint_id"]


def test_loop_feeds_parse_errors_back(tmp_path):
    model = FakeModel([
        {"role": "assistant", "content": '<tool_call name="read_file">{broken</tool_call>'},
        {"role": "assistant", "content": "ok, giving up"},
    ])
    loop, _ = make_loop(tmp_path, model)
    result = loop.run("do something")
    assert result["status"] == "completed"
    correction = model.received[1]
    assert any("valid JSON" in str(m.get("content")) for m in correction)


def test_loop_duplicate_calls_blocked_then_stalls(tmp_path):
    (tmp_path / "f.txt").write_text("hi", encoding="utf-8")
    same = xml_call("read_file", '{"path": "f.txt"}')
    model = FakeModel([same] * 12)
    loop, _ = make_loop(tmp_path, model)
    result = loop.run("loop forever")
    assert result["status"] == "stalled"
    assert result["success"] is False


def test_loop_max_turns(tmp_path):
    # Alternating distinct reads so guardrails never block.
    calls = [xml_call("read_file", f'{{"path": "no{i}.txt"}}') for i in range(20)]
    model = FakeModel(calls)
    loop, _ = make_loop(tmp_path, model, max_turns=3)
    result = loop.run("never finish")
    assert result["status"] == "max_turns" and result["turns"] == 3


def test_loop_nudges_only_when_code_fences_replace_tool_calls(tmp_path):
    # Printing code in fences instead of acting gets a corrective nudge...
    model = FakeModel([
        {"role": "assistant", "content": "Here is some code: ```html ... ```"},
        {"role": "assistant", "content": "Understood, nothing to write."},
    ])
    loop, _ = make_loop(tmp_path, model)
    result = loop.run("build a page")
    assert result["status"] == "completed"
    assert result["final_text"] == "Understood, nothing to write."
    assert result["turns"] == 2
    nudge_request = model.received[1]
    assert any("tool" in str(m.get("content", "")).lower() and m.get("role") == "user"
               for m in nudge_request[-1:])


def test_loop_accepts_conversational_reply_without_nudging(tmp_path):
    # "hello" deserves a greeting, not an unsolicited index.html.
    model = FakeModel([
        {"role": "assistant", "content": "Hi! Tell me what you'd like to build."},
    ])
    loop, _ = make_loop(tmp_path, model)
    result = loop.run("hello")
    assert result["status"] == "completed"
    assert result["turns"] == 1
    assert result["final_text"] == "Hi! Tell me what you'd like to build."
    assert result["mutated_files"] == []


def test_loop_no_nudge_after_real_tool_call(tmp_path):
    (tmp_path / "x.txt").write_text("hi", encoding="utf-8")
    model = FakeModel([
        xml_call("read_file", '{"path": "x.txt"}'),
        {"role": "assistant", "content": "done reading"},
    ])
    loop, _ = make_loop(tmp_path, model)
    result = loop.run("read x")
    assert result["turns"] == 2 and result["final_text"] == "done reading"


def test_loop_allows_repeated_run_command(tmp_path):
    # verify -> fix -> re-verify: the same command must be runnable twice.
    import json
    import sys
    command = f'"{sys.executable}" -c "print(1)"'
    call = xml_call("run_command", json.dumps({"command": command}))
    model = FakeModel([call, call, {"role": "assistant", "content": "verified twice"}])
    loop, events = make_loop(tmp_path, model)
    result = loop.run("run it twice")
    assert result["status"] == "completed"
    ran = [e for e in events if e.type == "tool_result" and e.payload["tool"] == "run_command"]
    assert len(ran) == 2 and all(e.payload["success"] for e in ran)


def test_loop_retries_truncated_tool_call(tmp_path):
    # Output cut off mid tool call (max_tokens): re-ask, don't treat as prose.
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    model = FakeModel([
        {"role": "assistant", "content": 'Let me look.\n<tool_call>\n{"name": "read_file'},
        xml_call("read_file", '{"path": "a.txt"}'),
        {"role": "assistant", "content": "done"},
    ])
    loop, events = make_loop(tmp_path, model)
    result = loop.run("inspect a.txt")
    assert result["status"] == "completed"
    reads = [e for e in events if e.type == "tool_result" and e.payload["tool"] == "read_file"]
    assert len(reads) == 1 and reads[0].payload["success"]
    retry_request = model.received[1]
    assert any("cut off" in str(m.get("content", "")) for m in retry_request[-1:])


def test_repeated_read_allowed_after_compaction(tmp_path):
    # Compaction collapses old tool results; re-reading must become legal.
    from nexcoder.agent.tool_guardrails import ToolGuardrailController
    guardrails = ToolGuardrailController()
    first = guardrails.before_call("read_file", {"path": "a.py"})
    assert first.allows_execution
    guardrails.after_call("read_file", {"path": "a.py"}, {"success": True, "content": "x"})
    blocked = guardrails.before_call("read_file", {"path": "a.py"})
    assert not blocked.allows_execution
    guardrails.note_context_compacted()
    again = guardrails.before_call("read_file", {"path": "a.py"})
    assert again.allows_execution


def test_loop_todo_state_in_result(tmp_path):
    model = FakeModel([
        xml_call("todo_write",
                 '{"todos": [{"content": "step 1", "status": "in_progress"}]}'),
        {"role": "assistant", "content": "planned"},
    ])
    loop, _ = make_loop(tmp_path, model)
    result = loop.run("plan it")
    assert result["todos"][0]["content"] == "step 1"
