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


def test_loop_todo_state_in_result(tmp_path):
    model = FakeModel([
        xml_call("todo_write",
                 '{"todos": [{"content": "step 1", "status": "in_progress"}]}'),
        {"role": "assistant", "content": "planned"},
    ])
    loop, _ = make_loop(tmp_path, model)
    result = loop.run("plan it")
    assert result["todos"][0]["content"] == "step 1"
