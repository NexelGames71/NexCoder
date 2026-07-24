from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.loop import AgentLoop
from nexcoder.agent.core.memory import load_project_memory, remember_note
from nexcoder.agent.core.tools.base import ToolContext
from nexcoder.agent.core.transport import XmlAdapter


class RecordingModel:
    def __init__(self):
        self.received = []

    def complete(self, messages, *, extras, on_delta=None):
        self.received.append(messages)
        return {"role": "assistant", "content": "ok"}


def test_load_memory_missing_returns_empty(tmp_path):
    assert load_project_memory(tmp_path) == ""


def test_remember_appends_and_loads(tmp_path):
    remember_note(tmp_path, "tests run via pytest -q")
    remember_note(tmp_path, "never touch legacy/ folder")
    memory = load_project_memory(tmp_path)
    assert "tests run via pytest -q" in memory
    assert "never touch legacy/" in memory


def test_memory_capped(tmp_path):
    for i in range(300):
        remember_note(tmp_path, f"note number {i} " + "x" * 100)
    memory = load_project_memory(tmp_path)
    assert len(memory) <= 8200  # cap plus marker tolerance
    assert "note number 299" in memory  # newest survives trimming


def test_loop_injects_memory_into_system_prompt(tmp_path):
    remember_note(tmp_path, "the build command is npm run build")
    model = RecordingModel()
    loop = AgentLoop(
        project_root=tmp_path, model=model, adapter=XmlAdapter(),
        belt=build_default_belt(), system_prompt="sys")
    loop.run("hello")
    system = model.received[0][0]
    assert system["role"] == "system"
    assert "npm run build" in system["content"]
    assert "Project memory" in system["content"]


def test_remember_tool_registered_and_writes(tmp_path):
    belt = build_default_belt()
    assert "remember" in belt.names
    ctx = ToolContext(project_root=tmp_path, emit=lambda _e: None, run_id="t")
    result = belt.execute("remember", {"note": "database lives in db/dev.sqlite"}, ctx)
    assert result["success"]
    assert "db/dev.sqlite" in load_project_memory(tmp_path)
