import sys
import threading
import time

from nexcoder.agent.cancellation import CancellationToken
from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.loop import AgentLoop
from nexcoder.agent.core.tools.base import ToolContext
from nexcoder.agent.core.tools.shell import register_shell_tool
from nexcoder.agent.core.transport import XmlAdapter


def xml_call(tool, args_json):
    return {"role": "assistant",
            "content": f'<tool_call name="{tool}">{args_json}</tool_call>'}


def test_loop_stops_between_turns_when_cancelled(tmp_path):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    token = CancellationToken()

    class CancelAfterFirst:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, *, extras, on_delta=None):
            self.calls += 1
            if self.calls == 1:
                token.cancel()
                return xml_call("read_file", '{"path": "a.txt"}')
            return {"role": "assistant", "content": "should never be reached"}

    model = CancelAfterFirst()
    events: list[AgentEvent] = []
    loop = AgentLoop(
        project_root=tmp_path, model=model, adapter=XmlAdapter(),
        belt=build_default_belt(), system_prompt="sys",
        emit=events.append, cancel_token=token)
    result = loop.run("read the file")
    assert result["status"] == "cancelled"
    assert result["success"] is False
    assert model.calls == 1  # no second model call after cancel
    completed = [e for e in events if e.type == "run_completed"]
    assert completed and completed[0].payload["status"] == "cancelled"


def test_run_command_killed_on_cancel(tmp_path):
    token = CancellationToken()
    belt_events: list[AgentEvent] = []
    from nexcoder.agent.core.tools.base import ToolBelt
    belt = ToolBelt()
    register_shell_tool(belt)
    ctx = ToolContext(project_root=tmp_path, emit=belt_events.append,
                      run_id="t", cancel_token=token)
    code = "import time; time.sleep(30)"
    timer = threading.Timer(1.0, token.cancel)
    timer.start()
    started = time.monotonic()
    result = belt.execute(
        "run_command", {"command": f'"{sys.executable}" -c "{code}"'}, ctx)
    elapsed = time.monotonic() - started
    timer.cancel()
    assert result["error_code"] == "agent_cancelled"
    assert elapsed < 10  # killed promptly, not after the 30s sleep
