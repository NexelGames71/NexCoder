"""Approval-gated implementation plan lifecycle."""

import pytest

from nexcoder.agent.core.tools.base import ToolBelt, ToolContext, ToolSpec
from nexcoder.agent.planning.commands import parse_plan_command
from nexcoder.agent.planning.manager import (
    PlanApprovalError, PlanConflictError, PlanManager,
)


def draft_payload():
    return {
        "title": "Ship the feature",
        "objective": "Implement a safe feature",
        "current_state_findings": ["app.py is the entry point"],
        "proposed_architecture": ["Keep the existing application boundary"],
        "confirmed_requirements": ["Keep compatibility"],
        "inspected_files": ["app.py"],
        "phases": [{
            "id": "phase_1", "title": "Implementation",
            "tasks": [
                {"id": "task_1", "title": "Edit app.py"},
                {"id": "task_2", "title": "Run tests"},
            ],
        }],
        "files": [{
            "path": "app.py", "operation": "modify",
            "description": "Add the feature", "confirmed": True,
        }],
        "risks": [{
            "title": "Regression", "mitigation": "Run tests",
            "severity": "medium",
        }],
        "validation_steps": [{
            "description": "Run tests", "command": "pytest",
        }],
        "definition_of_done": ["Tests pass"],
    }


def test_plan_requires_current_revision_and_project_fingerprint(tmp_path):
    (tmp_path / "app.py").write_text("print('one')\n", encoding="utf-8")
    manager = PlanManager(tmp_path)
    plan = manager.create(conversation_id="chat_1", request="Build it")
    plan = manager.submit_draft(plan.id, draft_payload())

    assert plan.status == "awaiting_approval"
    assert plan.revision == 1
    assert manager.load(plan.id).markdown_content.startswith(
        "# Implementation Plan: Ship the feature")

    (tmp_path / "app.py").write_text("print('changed')\n", encoding="utf-8")
    with pytest.raises(PlanApprovalError, match="project changed"):
        manager.approve(plan.id, plan.revision)


def test_revision_can_be_resubmitted_and_only_approved_plan_mutates(tmp_path):
    (tmp_path / "app.py").write_text("print('one')\n", encoding="utf-8")
    manager = PlanManager(tmp_path)
    plan = manager.create(conversation_id="chat_1", request="Build it")
    plan = manager.submit_draft(plan.id, draft_payload())
    plan = manager.request_revision(plan.id, plan.revision, "Add a test phase")
    plan = manager.submit_draft(plan.id, draft_payload(), "Added requested tests")
    assert plan.status == "awaiting_approval"
    assert plan.revision == 2

    called = []
    belt = ToolBelt()
    belt.register(ToolSpec(
        name="mutate", description="test", parameters={"type": "object"},
        mutating=True,
        handler=lambda args, ctx: called.append(True) or {"success": True},
    ))
    context = ToolContext(
        project_root=tmp_path, emit=lambda event: None,
        plan_manager=manager, plan_id=plan.id, plan_revision=plan.revision,
    )
    blocked = belt.execute("mutate", {}, context)
    assert blocked["error_code"] == "plan_approval_required"
    assert not called

    manager.approve(plan.id, plan.revision)
    manager.begin_execution(plan.id, plan.revision)
    assert belt.execute("mutate", {}, context)["success"]
    assert called == [True]


def test_clarification_answers_persist_and_stale_revision_is_rejected(tmp_path):
    (tmp_path / "app.py").write_text("print('one')\n", encoding="utf-8")
    manager = PlanManager(tmp_path)
    plan = manager.create(conversation_id="chat_1", request="Build it")
    plan = manager.set_questions(plan.id, [{
        "id": "auth", "title": "Which provider?", "kind": "single",
        "options": [{"id": "existing", "label": "Use existing"}],
    }])
    plan = manager.answer_questions(plan.id, plan.revision, {"auth": "existing"})
    assert manager.load(plan.id).questions[0].answer == "existing"

    plan = manager.submit_draft(plan.id, draft_payload())
    with pytest.raises(PlanConflictError, match="Stale plan revision"):
        manager.approve(plan.id, plan.revision - 1)


def test_execution_progress_and_material_pause_are_persisted(tmp_path):
    (tmp_path / "app.py").write_text("print('one')\n", encoding="utf-8")
    manager = PlanManager(tmp_path)
    plan = manager.create(conversation_id="chat_1", request="Build it")
    plan = manager.submit_draft(plan.id, draft_payload())
    manager.approve(plan.id, plan.revision)
    manager.begin_execution(plan.id, plan.revision)

    plan = manager.sync_progress(plan.id, [
        {"status": "completed"}, {"status": "in_progress"},
    ])
    assert [task.status for task in plan.phases[0].tasks] == [
        "completed", "in_progress"]
    assert plan.phases[0].status == "in_progress"

    plan = manager.record_deviation(
        plan.id, "material", "A public API must change", "Revise phase 1")
    assert plan.status == "paused"
    assert manager.complete(plan.id, True).status == "paused"


@pytest.mark.parametrize("value, action", [
    ("/plan implement auth", "start"),
    ("/plan revise use OAuth", "revise"),
    ("Approve revision 1", "approve"),
    ("proceed", "approve"),
])
def test_plan_command_parser_is_explicit(value, action):
    parsed = parse_plan_command(value)
    assert (parsed.action if parsed else None) == action
