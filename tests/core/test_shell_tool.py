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


def test_windows_quote_normalization():
    from nexcoder.agent.core.tools.shell import windows_normalize_quotes
    assert windows_normalize_quotes("git commit -m 'fix: the bug'") == \
        'git commit -m "fix: the bug"'
    assert windows_normalize_quotes("echo 'a' && echo 'b'") == 'echo "a" && echo "b"'
    # Already double-quoted: untouched
    assert windows_normalize_quotes('git commit -m "it\'s fine"') == 'git commit -m "it\'s fine"'
    # Lone apostrophe: untouched
    assert windows_normalize_quotes("echo don't panic") == "echo don't panic"


def test_run_command_timeout(tmp_path):
    belt, ctx, _ = make(tmp_path)
    code = "import time; time.sleep(30)"
    result = belt.execute("run_command",
                          {"command": f'"{sys.executable}" -c "{code}"', "timeout": 2}, ctx)
    assert result["error_code"] == "tool_timeout"


def test_command_environment_redacts_secrets(monkeypatch, tmp_path):
    from nexcoder.agent.core.tools.shell import command_environment
    monkeypatch.setenv("NEXCODER_TEST_TOKEN", "do-not-leak")
    monkeypatch.setenv("ORDINARY_SETTING", "visible")
    environment = command_environment(str(tmp_path))
    assert "NEXCODER_TEST_TOKEN" not in environment
    assert environment["ORDINARY_SETTING"] == "visible"
    assert environment["NEXCODER_PROJECT_ROOT"] == str(tmp_path)


def test_command_environment_supports_explicit_opt_in(monkeypatch, tmp_path):
    from nexcoder.agent.core.tools.shell import command_environment
    monkeypatch.setenv("PROJECT_API_KEY", "allowed-for-test")
    monkeypatch.setenv("NEXCODER_COMMAND_ENV_ALLOW", "PROJECT_API_KEY")
    assert command_environment(str(tmp_path))["PROJECT_API_KEY"] == "allowed-for-test"
