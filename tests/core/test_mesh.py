"""Agent Mesh: plan parsing, validation, conflicts, and a full
orchestrated run over scripted models."""

import json

from nexcoder.agent.core.transport import XmlAdapter
from nexcoder.agent.mesh.orchestrator import MeshOrchestrator, list_mesh_runs
from nexcoder.agent.mesh.types import (
    MeshAgentResult, detect_conflicts, parse_plan, topo_sort, WorkUnit,
)


class FakeModel:
    def __init__(self, messages):
        self.queue = list(messages)
        self.received = []

    def complete(self, messages, *, extras, on_delta=None):
        self.received.append(messages)
        message = (self.queue.pop(0) if self.queue
                   else {"role": "assistant", "content": "done"})
        if on_delta and message.get("content"):
            on_delta(message["content"])
        return message


class AllowGate:
    def request(self, *, tool, detail):
        return "allow"


# ── Plan parsing ─────────────────────────────────────────────────────

def test_parse_plan_accepts_clean_json():
    text = json.dumps([
        {"id": "a", "title": "Scout", "role": "explorer",
         "description": "look around", "dependencies": []},
        {"id": "b", "title": "Build", "role": "implementation",
         "description": "build it", "dependencies": ["a"],
         "completion_criteria": ["it works"]},
    ])
    units, fallback = parse_plan(text, "goal")
    assert not fallback
    assert [u.id for u in units] == ["a", "b"]
    assert units[1].dependencies == ["a"]
    assert units[1].completion_criteria == ["it works"]


def test_parse_plan_tolerates_fences_and_prose():
    text = ('Here is my plan:\n```json\n'
            '[{"id": "x", "role": "implementation", "title": "T", '
            '"description": "do the thing"}]\n```\nGood luck!')
    units, fallback = parse_plan(text, "goal")
    assert not fallback
    assert units[0].id == "x"


def test_parse_plan_garbage_falls_back():
    units, fallback = parse_plan("I think we should just do it.", "add auth")
    assert fallback
    roles = [u.role for u in units]
    assert roles == ["explorer", "implementation", "review"]
    assert "add auth" in units[1].description


def test_parse_plan_drops_unknown_roles_and_caps():
    raw = [{"id": f"u{i}", "role": "implementation",
            "description": f"part {i}"} for i in range(8)]
    raw.insert(0, {"id": "bad", "role": "wizard", "description": "magic"})
    units, fallback = parse_plan(json.dumps(raw), "goal")
    assert not fallback
    assert len(units) == 4
    assert all(u.role == "implementation" for u in units)


def test_parse_plan_prunes_unknown_dependencies():
    text = json.dumps([
        {"id": "a", "role": "implementation", "description": "d",
         "dependencies": ["ghost", "a"]},
    ])
    units, _ = parse_plan(text, "goal")
    assert units[0].dependencies == []


def test_topo_sort_orders_dependencies_and_breaks_cycles():
    units = [
        WorkUnit(id="c", title="c", role="review", description="d",
                 dependencies=["b"]),
        WorkUnit(id="a", title="a", role="explorer", description="d",
                 dependencies=["c"]),  # cycle a→c→b→a
        WorkUnit(id="b", title="b", role="implementation", description="d",
                 dependencies=["a"]),
    ]
    ordered = topo_sort(units)
    ids = [u.id for u in ordered]
    assert sorted(ids) == ["a", "b", "c"]
    # Every remaining dependency points backwards.
    seen = set()
    for unit in ordered:
        assert all(dep in seen for dep in unit.dependencies)
        seen.add(unit.id)


def test_detect_conflicts_flags_shared_files():
    results = [
        MeshAgentResult(unit_id="a", role="implementation",
                        status="completed", mutated_files=["app.py", "x.py"]),
        MeshAgentResult(unit_id="b", role="test", status="completed",
                        mutated_files=["app.py"]),
    ]
    conflicts = detect_conflicts(results)
    assert conflicts == [{"file": "app.py", "units": ["a", "b"]}]


# ── Orchestrated run ─────────────────────────────────────────────────

def test_mesh_run_end_to_end(tmp_path):
    plan = json.dumps([
        {"id": "scout", "title": "Scout", "role": "explorer",
         "description": "Find the entry point."},
        {"id": "build", "title": "Build", "role": "implementation",
         "description": "Create hello.txt", "dependencies": ["scout"]},
    ])
    write_call = ('<tool_call>\n{"name": "write_file", "arguments": '
                  '{"path": "hello.txt", "content": "hi"}}\n</tool_call>')
    model = FakeModel([
        {"role": "assistant", "content": plan},              # plan
        {"role": "assistant", "content": "Entry is main.py"},  # explorer
        {"role": "assistant", "content": write_call},        # impl turn 1
        {"role": "assistant", "content": "Created hello.txt."},  # impl done
        {"role": "assistant", "content": "Team delivered the goal."},  # report
    ])
    events = []
    orchestrator = MeshOrchestrator(
        project_root=tmp_path, model=model, adapter=XmlAdapter(),
        permission_gate=AllowGate(),
        emit=lambda t, p: events.append((t, p)))
    summary = orchestrator.run("Create hello.txt")

    assert summary["status"] == "completed"
    assert summary["mutated_files"] == ["hello.txt"]
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hi"
    assert summary["report"] == "Team delivered the goal."

    types = [t for t, _ in events]
    assert types[0] == "mesh_started"
    assert types[1] == "mesh_plan"
    assert types.count("agent_started") == 2
    assert types.count("agent_completed") == 2
    assert types[-1] == "mesh_completed"

    # The implementation unit received the explorer's handoff.
    impl_task = model.received[2][-1]["content"]
    assert "Entry is main.py" in impl_task

    # The run persisted for the panel's history list.
    runs = list_mesh_runs(tmp_path)
    assert len(runs) == 1 and runs[0]["status"] == "completed"


def test_mesh_preserves_long_goal_for_planner_and_specialist(tmp_path):
    goal = "Build a production game.\n" + ("Detailed requirement. " * 1200)
    plan = json.dumps([{
        "id": "review", "title": "Review", "role": "review",
        "description": "Verify every requirement.",
    }])
    model = FakeModel([
        {"role": "assistant", "content": plan},
        {"role": "assistant", "content": "Reviewed."},
        {"role": "assistant", "content": "All requirements reviewed."},
    ])
    orchestrator = MeshOrchestrator(
        project_root=tmp_path, model=model, adapter=XmlAdapter(),
        permission_gate=AllowGate(), emit=lambda *_: None)

    summary = orchestrator.run(goal)

    assert model.received[0][-1]["content"] == goal
    assert goal in model.received[1][-1]["content"]
    assert summary["goal"] == goal
    # The sidebar history uses a compact preview, while the persisted run
    # keeps the full request for audit/resume fidelity.
    saved = json.loads((tmp_path / ".nexcoder" / "mesh"
                        / f"{summary['mesh_id']}.json").read_text(encoding="utf-8"))
    assert saved["goal"] == goal
    assert list_mesh_runs(tmp_path)[0]["goal"] == goal[:160]


def test_mesh_continues_dependents_in_degraded_mode(tmp_path):
    plan = json.dumps([
        {"id": "build", "title": "Build", "role": "implementation",
         "description": "impossible thing"},
        {"id": "verify", "title": "Verify", "role": "review",
         "description": "review it", "dependencies": ["build"]},
    ])

    class ExplodingModel(FakeModel):
        def complete(self, messages, *, extras, on_delta=None):
            if not self.queue:
                raise RuntimeError("model down")
            return super().complete(messages, extras=extras,
                                    on_delta=on_delta)

    model = ExplodingModel([{"role": "assistant", "content": plan}])
    events = []
    orchestrator = MeshOrchestrator(
        project_root=tmp_path, model=model, adapter=XmlAdapter(),
        permission_gate=AllowGate(),
        emit=lambda t, p: events.append((t, p)))
    summary = orchestrator.run("goal")

    assert summary["status"] == "completed_with_issues"
    statuses = {u["id"]: u["status"] for u in summary["units"]}
    assert statuses["build"] == "failed"
    assert statuses["verify"] == "failed"
    assert any(event_type == "agent_degraded" for event_type, _ in events)


def test_mesh_can_complete_implementation_after_explorer_failure(tmp_path):
    plan = json.dumps([
        {"id": "scout", "title": "Scout", "role": "explorer",
         "description": "Find the entry point."},
        {"id": "build", "title": "Build", "role": "implementation",
         "description": "Create hello.txt", "dependencies": ["scout"]},
    ])
    write_call = ('<tool_call>\n{"name": "write_file", "arguments": '
                  '{"path": "hello.txt", "content": "recovered"}}\n</tool_call>')

    class RecoveringModel(FakeModel):
        def __init__(self):
            super().__init__([
                {"role": "assistant", "content": plan},
                {"role": "assistant", "content": write_call},
                {"role": "assistant", "content": "Created hello.txt independently."},
                {"role": "assistant", "content": "Implementation recovered the goal."},
            ])
            self.calls = 0

        def complete(self, messages, *, extras, on_delta=None):
            self.calls += 1
            if self.calls == 2:  # explorer model call
                self.received.append(messages)
                raise RuntimeError("scout backend failure")
            return super().complete(messages, extras=extras, on_delta=on_delta)

    events = []
    orchestrator = MeshOrchestrator(
        project_root=tmp_path, model=RecoveringModel(), adapter=XmlAdapter(),
        permission_gate=AllowGate(),
        emit=lambda t, p: events.append((t, p)))
    summary = orchestrator.run("Create hello.txt")

    statuses = {u["id"]: u["status"] for u in summary["units"]}
    assert statuses == {"scout": "failed", "build": "completed"}
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "recovered"
    assert summary["mutated_files"] == ["hello.txt"]
    assert summary["status"] == "completed_with_issues"
    assert any(event_type == "agent_degraded" for event_type, _ in events)
