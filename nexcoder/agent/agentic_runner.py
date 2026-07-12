"""AgenticRunner — mode-aware wrapper around :class:`HermesAgentLoop`.

The runner is the single place that knows:

- which mode profile to enforce (read-only vs. write-capable, allowed
  tools, turn budget, retry policy);
- how to extract the final assistant summary (the ``<final_answer>``
  tags for read-only modes, the prose tail for write-capable modes);
- how to translate a contract failure into a UI-renderable error
  (``AgentContractError`` → ``status: error`` + ``agent_complete`` payload
  with ``error_kind``).

The mode wrappers (``ask.py``, ``edit.py``, ``debug.py``, ``review.py``)
all become thin ``AgenticRunner(profile=...).run(prompt, context,
callbacks)`` calls. The agent mode keeps delegating to the loop directly
because it already enforces the right policy.

For read-only task types (``question``, ``scan``, ``review``) the loop
produces a structured ``final_answer`` object that the runner passes
through unchanged. The result dict the runner returns always carries:

- ``response`` — the prose summary the chat stream shows
- ``task_type`` — the long-form task type (``question`` / ``scan`` / …)
- ``final_answer`` — a structured object the UI renders as a card, or
  ``None`` for write-capable task types
- ``patches`` — number of files the loop prepared for write-back
"""

from __future__ import annotations

import re
from typing import Any, Callable

from nexcoder.agent.context_builder import ContextBuilder
from nexcoder.agent.errors import AgentContractError
from nexcoder.agent.final_answer import (
    extract_final_answer_object,
)
from nexcoder.agent.hermes_runtime import HermesAgentLoop
from nexcoder.agent.mode_profiles import (
    FINAL_ANSWER_CLOSE,
    FINAL_ANSWER_OPEN,
    FinalShape,
    ModeProfile,
    get_profile,
)
from nexcoder.agent.intent_router import TaskType


_FINAL_ANSWER_RE = re.compile(
    re.escape(FINAL_ANSWER_OPEN) + r"(.*?)" + re.escape(FINAL_ANSWER_CLOSE),
    re.DOTALL,
)


def _extract_prose(text: str) -> str:
    """Return the text inside ``<final_answer>`` tags, or the whole text.

    Kept for backwards compatibility with callers that still expect a
    prose string. New code should use
    :func:`extract_final_answer_object` from ``final_answer.py`` which
    returns a structured payload.
    """
    if not text:
        return ""
    match = _FINAL_ANSWER_RE.search(text)
    if match:
        return match.group(1).strip()
    cleaned = text.replace(FINAL_ANSWER_OPEN, "").replace(FINAL_ANSWER_CLOSE, "")
    return cleaned.strip()


# Backwards-compatible alias. The test suite uses this name.
_extract_final_answer = _extract_prose


class AgenticRunner:
    """Run a coding task in a specific mode using the Hermes agent loop."""

    def __init__(
        self,
        profile: ModeProfile | str,
        project_root: str | None = None,
    ) -> None:
        if isinstance(profile, str):
            profile = get_profile(profile)
        self.profile = profile
        self.project_root = project_root
        self._context_builder = ContextBuilder()
        self._loop = HermesAgentLoop(project_root)

    def run(
        self,
        prompt: str,
        context: dict[str, Any],
        callbacks: dict[str, Callable] | None = None,
    ) -> dict[str, Any]:
        """Execute the agentic loop for this mode.

        ``callbacks`` is a dict that may include ``on_chunk``, ``on_status``,
        ``on_diff`` and ``on_timeline``. Missing callbacks default to
        no-ops so the runner is easy to test.
        """
        callbacks = callbacks or {}
        on_chunk = callbacks.get("on_chunk", lambda chunk: None)
        on_status = callbacks.get("on_status", lambda status, message: None)
        on_diff = callbacks.get("on_diff", lambda diff: None)
        on_timeline = callbacks.get("on_timeline", lambda item: None)

        # Resolve the task type. The runtime can override it via
        # ``context["task_type"]``; otherwise we fall back to the
        # profile's default task type so each mode declares its own
        # final-artifact contract.
        task_type: TaskType = (
            context.get("task_type")
            or getattr(self.profile, "task_type", None)
            or "question"
        )

        # Inject the profile into the context so the loop can pick it up
        # without changing its public signature. Keep the rest of the
        # context untouched so the existing ContextBuilder + frontend
        # wiring is unchanged.
        loop_context = dict(context)
        loop_context["_mode_profile"] = self.profile
        loop_context["task_type"] = task_type
        # The loop reads project_path / projectPath; normalise here so the
        # profile-driven path matches the legacy path.
        if self.project_root and "project_path" not in loop_context and "projectPath" not in loop_context:
            loop_context["project_path"] = self.project_root

        # Also expose the task type as a status update so the timeline
        # can show it before the first tool runs.
        try:
            on_status("task_type", f"task_type={task_type}")
        except Exception:
            pass

        result = self._loop.run(prompt, loop_context, callbacks)
        return self._enforce_final_shape(result, on_chunk)

    # ──────────────────────────────────────────────────────────────────
    # Final-shape enforcement
    # ──────────────────────────────────────────────────────────────────

    def _enforce_final_shape(
        self,
        result: dict[str, Any],
        on_chunk: Callable[[str], None],
    ) -> dict[str, Any]:
        """Coerce the raw loop result into the shape the mode requires.

        The loop already attaches ``task_type`` and ``final_answer`` for
        read-only task types; this method:

        - For ``final_answer`` modes: re-streams the prose summary,
          copies the structured ``final_answer`` payload to the result
          top-level, and synthesises a fallback card if the loop did not
          produce one.
        - For ``write_or_diff`` modes: surfaces the existing diff /
          approval path. Marks the result if the model produced prose
          without a patch so the UI can warn the user.
        - For ``any`` modes: passes the result through, attaching a
          default ``task_type`` if the loop omitted one.
        """
        shape: FinalShape = self.profile.final_shape
        response = result.get("response", "") or ""
        task_type: TaskType = result.get("task_type") or getattr(
            self.profile, "task_type", None
        ) or "implement"

        result["task_type"] = task_type
        result["final_answer"] = result.get("final_answer")

        if shape == "final_answer":
            # Re-emit the prose summary if the loop produced one inside
            # tags, then expose the structured card.
            cleaned = _extract_prose(response)
            if cleaned and cleaned != response:
                on_chunk(cleaned)
            result["response"] = cleaned
            # If the loop didn't attach a final_answer object (older
            # callers, or paths that bypass HermesAgentLoop) build one
            # from the prose so the UI always has a card to render.
            if not result["final_answer"]:
                result["final_answer"] = extract_final_answer_object(response)
            return result

        if shape == "write_or_diff":
            wrote_or_patched = bool(result.get("patches")) or self._has_diff_marker(response)
            if not wrote_or_patched and response.strip():
                result["response"] = response
                result["write_or_diff_missing"] = True
            # write_or_diff tasks must end with a patch_proposal,
            # approval_request, validation_report, or failure_report.
            # If none of those exists we attach a failure_report so the
            # UI never has to render an empty task timeline.
            if not wrote_or_patched and not result.get("failure_report"):
                result["failure_report"] = {
                    "type": "failure_report",
                    "title": "No patch produced",
                    "summary": (
                        "The agent finished without writing any files. "
                        "Re-run with a more specific instruction or "
                        "manually draft the patch."
                    ),
                }
            return result

        # "any" — agent mode's existing behaviour. The result already
        # carries the loop's own task_type / final_answer fields.
        return result

    @staticmethod
    def _has_diff_marker(text: str) -> bool:
        return "```diff" in text or "<tool_call name=\"write_file\"" in text
