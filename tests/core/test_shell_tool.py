import sys

from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import DENY, ToolBelt, ToolContext
from nexcoder.agent.core.tools.shell import register_shell_tool


class DenyGate:
    def request(self, *, tool, detail):
        return DENY


def make(tmp_path, gate=None):
    events: list[AgentEvent] = []
    belt = ToolBelt()
    register_shell_tool(belt)
    ctx = ToolContext(project_root=tmp_path, emit=events.append,
                      permission_gate=gate, run_id="t")
    return belt, ctx, events


def test_run_command_streams_and_reports_exit(tmp_path):
    belt, ctx, events = make(tmp_path)
    code = "import sys; print('out1'); print('err1', file=sys.stderr)"
    result = belt.execute("run_command", {"command": f'"{sys.executable}" -c "{code}"'}, ctx)
    assert result["success"] and result["exit_code"] == 0
    assert "out1" in result["stdout"] and "err1" in result["stderr"]
    assert any(e.type == "command_output" for e in events)


def test_run_command_denied_by_gate(tmp_path):
    belt, ctx, events = make(tmp_path, DenyGate())
    result = belt.execute("run_command", {"command": "echo hi"}, ctx)
    assert result["error_code"] == "permission_denied"
    types = [e.type for e in events]
    assert "permission_request" in types and "permission_resolved" in types


def test_run_command_blocklist_always_wins(tmp_path):
    belt, ctx, _ = make(tmp_path)  # AllowAllGate default
    result = belt.execute("run_command", {"command": "rm -rf /"}, ctx)
    assert result["error_code"] == "tool_command_blocked"


def test_run_command_timeout(tmp_path):
    belt, ctx, _ = make(tmp_path)
    code = "import time; time.sleep(30)"
    result = belt.execute("run_command",
                          {"command": f'"{sys.executable}" -c "{code}"', "timeout": 2}, ctx)
    assert result["error_code"] == "tool_timeout"
