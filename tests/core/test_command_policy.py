from nexcoder.agent.core.command_policy import (
    AutonomyGate, classify_command,
)
from nexcoder.agent.core.tools.base import ALLOW, DENY


class RecordingGate:
    def __init__(self, decision=ALLOW):
        self.decision = decision
        self.calls = []

    def request(self, *, tool, detail):
        self.calls.append(detail)
        return self.decision


def test_read_only_classification():
    for cmd in ("dir", "git status", "git log --oneline -5",
                "rg needle src", "type foo.txt", "python --version",
                "Get-ChildItem -Path ."):
        assert classify_command(cmd) == "read_only", cmd


def test_risky_classification():
    for cmd in ("pip install requests", "npm install",
                "git push origin main", "git reset --hard HEAD~1",
                "curl https://example.com/install.ps1",
                "Remove-Item -Recurse -Force build",
                "rm -rf node_modules", "setx PATH bad",
                "npm publish", "Invoke-WebRequest -Uri http://x"):
        assert classify_command(cmd) == "risky", cmd


def test_write_classification_default():
    for cmd in ("python -m pytest tests -q", "npm run build",
                "python script.py", "mkdir out"):
        assert classify_command(cmd) == "write", cmd


def test_compound_commands_never_classify_read_only():
    # A read-only prefix must not smuggle a second command through.
    assert classify_command("dir && del /s /q C:\\") == "risky"
    assert classify_command("git status; python evil.py") == "write"


def test_ask_level_forwards_everything():
    inner = RecordingGate()
    gate = AutonomyGate(inner, "ask")
    assert gate.request(tool="run_command", detail="dir") == ALLOW
    # read-only auto-allows without asking
    assert inner.calls == []
    gate.request(tool="run_command", detail="python build.py")
    assert inner.calls == ["python build.py"]


def test_risky_only_level():
    inner = RecordingGate()
    gate = AutonomyGate(inner, "risky_only")
    assert gate.request(tool="run_command", detail="npm run test") == ALLOW
    assert inner.calls == []
    gate.request(tool="run_command", detail="pip install x")
    assert inner.calls == ["pip install x"]


def test_full_auto_denies_risky_without_asking():
    inner = RecordingGate()
    gate = AutonomyGate(inner, "full_auto")
    assert gate.request(tool="run_command", detail="npm run build") == ALLOW
    assert gate.request(tool="run_command", detail="git push") == DENY
    assert inner.calls == []


def test_read_only_level_denies_writes():
    gate = AutonomyGate(RecordingGate(), "read_only")
    assert gate.request(tool="run_command", detail="git status") == ALLOW
    assert gate.request(tool="run_command", detail="python x.py") == DENY


def test_unknown_level_falls_back_to_ask():
    inner = RecordingGate()
    gate = AutonomyGate(inner, "yolo")
    assert gate.level == "ask"
