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


def test_load_skill_reads_project_skills(tmp_path):
    make_project_skill(tmp_path, "deploy-widget", body="Widget body.")
    call = {"role": "assistant", "content":
            '<tool_call name="load_skill">{"id": "deploy-widget"}</tool_call>'}
    model = TwoTurn(call)
    loop = make_loop(tmp_path, model)
    loop.run("ship it")
    tool_response = str(model.received[1][-1]["content"])
    assert "Widget body." in tool_response
