"""AgentLoop — the canonical agentic loop.

messages -> model -> tool calls -> results -> repeat, until the model
answers with no tool calls, guardrails stall it, or the turn cap hits.
Mode-specific behaviour lives in the system prompt and belt, never here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Protocol
import uuid

from nexcoder.agent.core.conversation import Conversation
from nexcoder.agent.core.events import AgentEvent, EventCallback
from nexcoder.agent.core.session_store import SessionStore
from nexcoder.agent.core.tools.base import PermissionGate, ToolBelt, ToolContext
from nexcoder.agent.core.transport import ToolCallAdapter
from nexcoder.agent.tool_guardrails import ToolGuardrailConfig, ToolGuardrailController
from nexcoder.agent.trajectory import AgentTrajectoryRecorder

logger = logging.getLogger(__name__)

MAX_GUARDRAIL_BLOCKS = 6
MAX_NO_TOOL_NUDGES = 2

NO_TOOL_NUDGE = (
    "You have not called any tools yet, so nothing has actually happened in "
    "the project. Printing code in markdown fences does NOT create files. "
    "Act now by emitting tool calls in this exact format:\n"
    "<tool_call>\n"
    '{"name": "write_file", "arguments": {"path": "index.html", "content": "..."}}\n'
    "</tool_call>"
)

AGENT_SYSTEM_PROMPT = """You are NexCoder, an autonomous coding agent working \
inside the user's project.

How you work:
1. On non-trivial tasks, call todo_write first with your plan, and keep \
statuses current as you complete each step.
2. Inspect before you change: use glob/grep/read_file to find and understand \
the relevant code. Never invent file contents.
3. Edit precisely: prefer edit_file with an exact unique old_string. Use \
write_file only for new files or full rewrites.
4. Verify your work: after making changes, run a verification command \
(tests, build, or a quick check) with run_command. If it fails, read the \
error, fix the code, and verify again before finishing.
5. When the task is fully complete and verified, reply with a short plain-text \
summary of what changed and how it was verified. No tool calls in that final \
message."""


class ModelClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        extras: dict[str, Any],
        on_delta: Callable[[str], None] | None = None,
    ) -> dict[str, Any]: ...


class AgentLoop:
    def __init__(
        self,
        *,
        project_root: str | Path,
        model: ModelClient,
        adapter: ToolCallAdapter,
        belt: ToolBelt,
        system_prompt: str,
        emit: EventCallback | None = None,
        permission_gate: PermissionGate | None = None,
        max_turns: int = 50,
        context_window: int = 8192,
        reserve_output: int = 3072,
        extra_system: str = "",
        trajectory_mode: str = "agent",
        guardrail_config: ToolGuardrailConfig | None = None,
        session_store: SessionStore | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.model = model
        self.adapter = adapter
        self.belt = belt
        self.system_prompt = system_prompt
        self.emit: EventCallback = emit or (lambda _event: None)
        self.permission_gate = permission_gate
        self.max_turns = max_turns
        self.context_window = context_window
        self.reserve_output = reserve_output
        self.extra_system = extra_system
        self.trajectory_mode = trajectory_mode
        # Re-running the same command is the verify -> fix -> re-verify loop,
        # not a stuck agent; exempt it from exact-repeat blocking by default.
        self.guardrail_config = guardrail_config or ToolGuardrailConfig(
            exempt_repeat_tools=frozenset({"run_command"}))
        self.session_store = session_store

    def _summarize(self, old_messages: list[dict[str, Any]]) -> str:
        transcript = "\n".join(
            f"{m.get('role')}: {str(m.get('content'))[:400]}" for m in old_messages)
        prompt = [
            {"role": "system", "content":
             "Summarize this agent transcript in under 200 words. Keep: the "
             "task, files touched, decisions made, and current state."},
            {"role": "user", "content": transcript[:12000]},
        ]
        try:
            message = self.model.complete(prompt, extras={}, on_delta=None)
            return str(message.get("content") or "").strip() or "(no summary)"
        except Exception as exc:
            logger.warning("Compaction summarizer failed: %s", exc)
            return "(summary unavailable)"

    def run(self, task: str) -> dict[str, Any]:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        ctx = ToolContext(
            project_root=self.project_root, emit=self.emit,
            permission_gate=self.permission_gate, run_id=run_id)
        schemas = self.belt.schemas()
        system = self.system_prompt
        if self.extra_system:
            system += "\n\n" + self.extra_system
        system += self.adapter.system_prompt_suffix(schemas)
        conversation = Conversation(
            system, context_window=self.context_window,
            reserve_output=self.reserve_output)
        conversation.add({"role": "user", "content": task})
        guardrails = ToolGuardrailController(self.guardrail_config)
        trajectory = AgentTrajectoryRecorder(
            self.project_root, task=task, mode=self.trajectory_mode)
        extras = self.adapter.request_extras(schemas)

        def _persist(current_status: str, turn_number: int) -> None:
            if self.session_store is None:
                return
            try:
                self.session_store.save(run_id, {
                    "task": task, "status": current_status,
                    "messages": conversation.messages(),
                    "todos": ctx.todos, "turn": turn_number})
            except Exception:
                logger.warning("Session persist failed", exc_info=True)

        self.emit(AgentEvent("run_started", {"run_id": run_id, "task": task}))
        status = "max_turns"
        final_text = ""
        blocked_total = 0
        turns_used = 0
        made_tool_call = False
        nudges = 0

        try:
            for turn in range(1, self.max_turns + 1):
                turns_used = turn
                self.emit(AgentEvent("turn_started", {"turn": turn, "run_id": run_id}))

                if conversation.needs_compaction():
                    stats = conversation.compact(self._summarize)
                    self.emit(AgentEvent("compaction", stats))

                message = self.model.complete(
                    conversation.payload_messages(), extras=extras,
                    on_delta=lambda delta: self.emit(
                        AgentEvent("text_delta", {"text": delta, "turn": turn})))
                conversation.add(message)
                turn_data = self.adapter.parse_assistant_message(message)

                if turn_data.parse_error:
                    trajectory.record("parse_error", {"error": turn_data.parse_error})
                    conversation.add({"role": "user", "content":
                                      f"Tool call error: {turn_data.parse_error}. "
                                      "Re-emit the call with valid JSON arguments."})
                    continue

                if not turn_data.tool_calls:
                    if not made_tool_call and nudges < MAX_NO_TOOL_NUDGES:
                        nudges += 1
                        trajectory.record("no_tool_nudge", {"nudge": nudges})
                        conversation.add({"role": "user", "content": NO_TOOL_NUDGE})
                        continue
                    final_text = turn_data.text
                    status = "completed"
                    break
                made_tool_call = True

                results: list[dict[str, Any]] = []
                for call in turn_data.tool_calls:
                    decision = guardrails.before_call(call.name, call.args)
                    if not decision.allows_execution:
                        blocked_total += 1
                        result: dict[str, Any] = {
                            "success": False, "error_code": decision.code,
                            "error": decision.message}
                    else:
                        self.emit(AgentEvent("tool_started", {
                            "tool": call.name, "args": call.args, "turn": turn}))
                        result = self.belt.execute(call.name, call.args, ctx)
                        after = guardrails.after_call(call.name, call.args, result)
                        if after.action == "block":
                            blocked_total += 1
                            result = {**result, "guardrail": after.message}
                        elif after.action == "warn":
                            result = {**result, "guardrail": after.message}
                    self.emit(AgentEvent("tool_result", {
                        "tool": call.name, "success": bool(result.get("success")),
                        "summary": str(result.get("message") or result.get("error") or "")[:200],
                        "turn": turn}))
                    trajectory.record("tool_call", {
                        "tool": call.name, "args": call.args, "result": result})
                    results.append(result)

                for result_message in self.adapter.tool_result_messages(
                        list(turn_data.tool_calls), results):
                    conversation.add(result_message)
                _persist("running", turn)

                if blocked_total >= MAX_GUARDRAIL_BLOCKS:
                    status = "stalled"
                    final_text = ("Run stopped: the agent repeated unproductive "
                                  "tool calls too many times.")
                    break
        except Exception as exc:
            logger.exception("Agent run failed")
            status = "error"
            final_text = f"Run failed: {exc}"
            self.emit(AgentEvent("run_error", {"run_id": run_id, "error": str(exc)}))

        result = {
            "success": status == "completed",
            "status": status,
            "final_text": final_text,
            "run_id": run_id,
            "checkpoint_id": ctx.checkpoint_id,
            "mutated_files": sorted(ctx.mutated_files),
            "todos": ctx.todos,
            "turns": turns_used,
        }
        _persist(status, turns_used)
        trajectory.finish(status=status, result={
            "final_text": final_text, "mutated_files": result["mutated_files"]})
        self.emit(AgentEvent("run_completed", result))
        return result
