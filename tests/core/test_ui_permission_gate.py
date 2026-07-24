import threading

from nexcoder.agent.agent_runtime_v2 import UiPermissionGate
from nexcoder.agent.core.tools.base import ALLOW, DENY


def test_gate_blocks_until_resolved():
    requests = []
    gate = UiPermissionGate(on_request=lambda rid, tool, detail: requests.append(rid))
    result_box = {}

    def ask():
        result_box["decision"] = gate.request(tool="run_command", detail="npm test")

    thread = threading.Thread(target=ask)
    thread.start()
    for _ in range(100):
        if requests:
            break
        threading.Event().wait(0.01)
    assert requests, "on_request was never called"
    gate.resolve(requests[0], ALLOW)
    thread.join(timeout=2)
    assert result_box["decision"] == ALLOW


def test_gate_times_out_to_deny():
    gate = UiPermissionGate(on_request=lambda *a: None, timeout=0.05)
    assert gate.request(tool="run_command", detail="x") == DENY


def test_gate_unknown_request_id_is_ignored():
    gate = UiPermissionGate(on_request=lambda *a: None, timeout=0.05)
    gate.resolve("nope", ALLOW)  # must not raise


def test_gate_unknown_id_resolves_single_pending_request():
    # The UI answers with the loop event's id, not the gate's internal id.
    gate = UiPermissionGate(on_request=lambda *a: None)
    result_box = {}

    def ask():
        result_box["decision"] = gate.request(tool="run_command", detail="npm test")

    thread = threading.Thread(target=ask)
    thread.start()
    for _ in range(100):
        with gate._lock:
            if gate._pending:
                break
        threading.Event().wait(0.01)
    gate.resolve("some-other-id", ALLOW)
    thread.join(timeout=2)
    assert result_box["decision"] == ALLOW
