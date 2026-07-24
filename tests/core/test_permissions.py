import json

from nexcoder.agent.core.permissions import AllowlistGate, FullAutoGate
from nexcoder.agent.core.tools.base import ALLOW, ALLOW_ALWAYS, DENY


class ScriptedGate:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def request(self, *, tool, detail):
        self.calls.append(detail)
        return self.answer


def test_allowlist_skips_inner_when_listed(tmp_path):
    (tmp_path / ".nexcoder").mkdir()
    (tmp_path / ".nexcoder" / "permissions.json").write_text(
        json.dumps({"allowed_commands": ["npm test"]}), encoding="utf-8")
    inner = ScriptedGate(DENY)
    gate = AllowlistGate(inner, tmp_path)
    assert gate.request(tool="run_command", detail="npm test") == ALLOW
    assert inner.calls == []


def test_allow_always_persists(tmp_path):
    inner = ScriptedGate(ALLOW_ALWAYS)
    gate = AllowlistGate(inner, tmp_path)
    assert gate.request(tool="run_command", detail="pytest -q") == ALLOW
    saved = json.loads((tmp_path / ".nexcoder" / "permissions.json").read_text(encoding="utf-8"))
    assert "pytest -q" in saved["allowed_commands"]
    # Second time: no inner prompt
    inner2 = ScriptedGate(DENY)
    gate2 = AllowlistGate(inner2, tmp_path)
    assert gate2.request(tool="run_command", detail="pytest -q") == ALLOW
    assert inner2.calls == []


def test_full_auto_gate_blocks_risky():
    gate = FullAutoGate()
    assert gate.request(tool="run_command", detail="npm test") == ALLOW
    assert gate.request(tool="run_command", detail="git push origin main") == DENY
    assert gate.request(tool="run_command", detail="rm -r build") == DENY
