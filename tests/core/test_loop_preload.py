from skill_helpers import make_project_skill

from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.loop import AgentLoop
from nexcoder.agent.core.transport import XmlAdapter


class RecordingModel:
    def __init__(self):
        self.received = []

    def complete(self, messages, *, extras, on_delta=None):
        self.received.append(messages)
        return {"role": "assistant", "content": "done"}


class TwoTurn:
    def __init__(self, first_call):
        self.queue = [first_call, {"role": "assistant", "content": "ok"}]
        self.received = []

    def complete(self, messages, *, extras, on_delta=None):
        self.received.append(messages)
        return self.queue.pop(0)


def make_loop(tmp_path, model, events=None):
    return AgentLoop(
        project_root=tmp_path, model=model, adapter=XmlAdapter(),
        belt=build_default_belt(), system_prompt="sys",
        emit=(events.append if events is not None else None))


def test_preload_injects_skill_system_message(tmp_path):
    make_project_skill(tmp_path, "deploy-widget", body="Step 1: widgetize.")
    model = RecordingModel()
    loop = make_loop(tmp_path, model)
    loop.run("ship it", preload_skill="deploy-widget")
    first_request = model.received[0]
    assert first_request[1]["role"] == "system"
    assert "[Skill: deploy-widget]" in first_request[1]["content"]
    assert "widgetize" in first_request[1]["content"]
    assert first_request[2]["role"] == "user"


def test_preload_unknown_skill_warns_and_proceeds(tmp_path):
    events: list[AgentEvent] = []
    model = RecordingModel()
    loop = make_loop(tmp_path, model, events)
    result = loop.run("ship it", preload_skill="nope")
    assert result["status"] == "completed"
    started = next(e for e in events if e.type == "run_started")
    assert "nope" in started.payload["preload_warning"]


def test_load_skill_short_circuits_when_preloaded(tmp_path):
    make_project_skill(tmp_path, "deploy-widget", body="B" * 500)
    call = {"role": "assistant", "content":
            '<tool_call name="load_skill">{"id": "deploy-widget"}</tool_call>'}
    model = TwoTurn(call)
    loop = make_loop(tmp_path, model)
    loop.run("ship it", preload_skill="deploy-widget")
    tool_response = str(model.received[1][-1]["content"])
    assert "already loaded" in tool_response
    assert "B" * 100 not in tool_response  # body not re-sent


def test_run_seeds_nexcoder_gitignore(tmp_path):
    loop = make_loop(tmp_path, RecordingModel())
    loop.run("anything")
    ignore = tmp_path / ".nexcoder" / ".gitignore"
    assert ignore.read_text(encoding="utf-8").strip() == "*"


def test_exempt_tool_repeat_blocked_after_failure(tmp_path):
    import json as _json
    # A command that always fails identically must not be re-runnable forever.
    bad = {"role": "assistant", "content":
           '<tool_call name="run_command">' + _json.dumps({"command": "definitely-not-a-cmd-xyz"}) + "</tool_call>"}
    from nexcoder.agent.core.events import AgentEvent
    events: list[AgentEvent] = []
    model = type("M", (), {
        "queue": [bad] * 10,
        "complete": lambda self, messages, *, extras, on_delta=None:
            self.queue.pop(0) if self.queue else {"role": "assistant", "content": "done"},
    })()
    loop = make_loop(tmp_path, model, events)
    loop.run("run the bad command")
    executed = [e for e in events if e.type == "tool_started"]
    # First run executes and fails; identical retries get blocked quickly
    # rather than executing 10 times.
    assert 1 <= len(executed) <= 2


def test_failed_command_rerunnable_after_successful_edit(tmp_path):
    # fail pytest -> fix code -> re-run same pytest: must be allowed.
    import json as _json
    import sys
    (tmp_path / "flag.py").write_bytes(b"OK = False\n")
    check = (f'"{sys.executable}" -c "import flag; import sys; '
             'sys.exit(0 if flag.OK else 1)"')
    run = {"role": "assistant", "content":
           '<tool_call name="run_command">' + _json.dumps({"command": check}) + "</tool_call>"}
    fix = {"role": "assistant", "content":
           '<tool_call name="edit_file">' + _json.dumps({
               "path": "flag.py", "old_string": "OK = False",
               "new_string": "OK = True"}) + "</tool_call>"}
    done = {"role": "assistant", "content": "fixed and verified"}

    class Scripted:
        def __init__(self):
            self.queue = [run, fix, run, done]
            self.received = []

        def complete(self, messages, *, extras, on_delta=None):
            self.received.append(messages)
            return self.queue.pop(0)

    from nexcoder.agent.core.events import AgentEvent
    events: list[AgentEvent] = []
    loop = make_loop(tmp_path, Scripted(), events)
    result = loop.run("make the check pass")
    assert result["status"] == "completed"
    runs = [e for e in events if e.type == "tool_result"
            and e.payload["tool"] == "run_command"]
    assert len(runs) == 2
    assert runs[0].payload["success"] is False
    assert runs[1].payload["success"] is True


def test_load_skill_reads_project_skills(tmp_path):
    make_project_skill(tmp_path, "deploy-widget", body="Widget body.")
    call = {"role": "assistant", "content":
            '<tool_call name="load_skill">{"id": "deploy-widget"}</tool_call>'}
    model = TwoTurn(call)
    loop = make_loop(tmp_path, model)
    loop.run("ship it")
    tool_response = str(model.received[1][-1]["content"])
    assert "Widget body." in tool_response
