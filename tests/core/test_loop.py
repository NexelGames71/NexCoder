from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.loop import AgentLoop
from nexcoder.agent.core.transport import NativeAdapter, XmlAdapter


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


def test_loop_retries_a_dropped_stream(tmp_path, monkeypatch):
    from nexcoder.agent.errors import ModelStreamError

    class FlakyModel(FakeModel):
        def __init__(self, messages, fail_first=1):
            super().__init__(messages)
            self.failures_left = fail_first

        def complete(self, messages, *, extras, on_delta=None):
            if self.failures_left > 0:
                self.failures_left -= 1
                raise ModelStreamError("connection forcibly closed")
            return super().complete(messages, extras=extras, on_delta=on_delta)

    monkeypatch.setattr("time.sleep", lambda _s: None)
    model = FlakyModel([
        {"role": "assistant", "content": "All good."},
    ])
    loop, events = make_loop(tmp_path, model)
    result = loop.run("say hi")
    assert result["success"] and result["final_text"] == "All good."
    assert "stream_retry" in [e.type for e in events]


def test_loop_gives_up_after_repeated_stream_drops(tmp_path, monkeypatch):
    from nexcoder.agent.errors import ModelStreamError

    class DeadModel(FakeModel):
        def complete(self, messages, *, extras, on_delta=None):
            raise ModelStreamError("connection forcibly closed")

    monkeypatch.setattr("time.sleep", lambda _s: None)
    loop, _events = make_loop(tmp_path, DeadModel([]))
    result = loop.run("say hi")
    assert not result["success"]
    assert result["status"] == "error"


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


def test_native_parse_error_does_not_leave_dangling_tool_call(tmp_path):
    model = FakeModel([
        {
            "role": "assistant",
            "content": "private reasoning</think>",
            "tool_calls": [{
                "id": "call_bad",
                "type": "function",
                "function": {"name": "write_file", "arguments": '{"path":'},
            }],
        },
        {"role": "assistant", "content": "Recovered cleanly."},
    ])
    loop = AgentLoop(
        project_root=tmp_path, model=model, adapter=NativeAdapter(),
        belt=build_default_belt(), system_prompt="test")

    result = loop.run("create a file")

    assert result["status"] == "completed"
    retry_payload = model.received[1]
    assert not any(message.get("tool_calls") for message in retry_payload)
    assert any("100 lines" in str(message.get("content"))
               for message in retry_payload)


def test_loop_resumes_complete_native_tool_history(tmp_path):
    prior = [
        {"role": "system", "content": "old system"},
        {"role": "user", "content": "inspect config.py"},
        {"role": "assistant", "content": "thoughts</think>", "tool_calls": [{
            "id": "call_read", "type": "function",
            "function": {"name": "read_file", "arguments": '{"path":"config.py"}'},
        }]},
        {"role": "tool", "tool_call_id": "call_read",
         "content": '{"success":true,"content":"PORT=8000"}'},
    ]
    model = FakeModel([{"role": "assistant", "content": "Continued without rereading."}])
    loop = AgentLoop(
        project_root=tmp_path, model=model, adapter=NativeAdapter(),
        belt=build_default_belt(), system_prompt="new system")

    result = loop.run("now change the port", resume_messages=prior)

    assert result["status"] == "completed"
    payload = model.received[0]
    assert [message["role"] for message in payload] == [
        "system", "user", "assistant", "tool", "user"]
    assert payload[2]["content"] == ""
    assert payload[-1]["content"] == "now change the port"


def test_loop_sends_image_attachment_as_multimodal_user_content(tmp_path):
    import base64

    data_url = "data:image/png;base64," + base64.b64encode(
        bytes.fromhex("89504e470d0a1a0a")).decode()
    model = FakeModel([{"role": "assistant", "content": "I can see the UI bug."}])
    loop, _ = make_loop(tmp_path, model)

    result = loop.run("Fix this screenshot", input_attachments=[{
        "name": "bug.png", "data_url": data_url,
    }])

    assert result["status"] == "completed"
    content = model.received[0][-1]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"


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
    assert result["final_text"]


def test_loop_synthesizes_a_handoff_after_the_operational_turn_limit(tmp_path):
    model = FakeModel([
        xml_call("read_file", '{"path": "missing-1.txt"}'),
        xml_call("read_file", '{"path": "missing-2.txt"}'),
        {"role": "assistant", "content":
         "I inspected both candidate paths; neither exists. The entry point is still unknown."},
    ])
    loop, _ = make_loop(tmp_path, model, max_turns=2)
    result = loop.run("find the entry point")
    assert result["status"] == "max_turns"
    assert "entry point is still unknown" in result["final_text"]
    final_request = model.received[-1]
    assert final_request[-1]["role"] == "user"
    assert "Do not call tools" in final_request[-1]["content"]


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


def test_loop_emits_context_usage_each_turn(tmp_path):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    model = FakeModel([
        xml_call("read_file", '{"path": "a.txt"}'),
        {"role": "assistant", "content": "done"},
    ])
    loop, events = make_loop(tmp_path, model)
    loop.run("read it")
    usage = [e for e in events if e.type == "context_usage"]
    assert len(usage) == 2  # one per turn
    payload = usage[0].payload
    assert payload["tokens"] > 0
    assert payload["budget"] > 0
    assert 0 <= payload["percent"] <= 100
    # Usage grows as history accumulates
    assert usage[1].payload["tokens"] > usage[0].payload["tokens"]


def test_loop_todo_state_in_result(tmp_path):
    model = FakeModel([
        xml_call("todo_write",
                 '{"todos": [{"content": "step 1", "status": "in_progress"}]}'),
        {"role": "assistant", "content": "planned"},
    ])
    loop, _ = make_loop(tmp_path, model)
    result = loop.run("plan it")
    assert result["todos"][0]["content"] == "step 1"


def test_loop_applies_late_user_steering_before_completing(tmp_path):
    model = FakeModel([
        {"role": "assistant", "content": "Initial answer."},
        {"role": "assistant", "content": "Updated answer after follow-up."},
    ])
    reads = 0

    def steering_source():
        nonlocal reads
        reads += 1
        # First check is at the turn boundary. The second simulates a prompt
        # arriving while the first model response is streaming.
        return ["Also cover the tests."] if reads == 2 else []

    loop, events = make_loop(
        tmp_path, model, steering_source=steering_source)
    result = loop.run("Explain the change")

    assert result["status"] == "completed"
    assert result["final_text"] == "Updated answer after follow-up."
    assert any(
        message.get("role") == "user"
        and "Also cover the tests." in str(message.get("content"))
        for message in model.received[1]
    )
    steering_events = [event for event in events
                       if event.type == "steering_applied"]
    assert len(steering_events) == 1
    assert steering_events[0].payload["text"] == "Also cover the tests."
