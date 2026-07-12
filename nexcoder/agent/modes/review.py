"""ReviewMode — code audit and quality review mode, now agentic.

The runner profile restricts the loop to read-only tools so the reviewer
cannot mutate files. The model is asked to wrap the structured review in
``<final_answer>`` tags so the runner can stream a clean summary back to
the UI.
"""

import logging
from typing import Any, Callable

from nexcoder.agent.agentic_runner import AgenticRunner
from nexcoder.agent.mode_profiles import REVIEW_PROFILE

logger = logging.getLogger(__name__)


class ReviewMode:
    """Code review mode — read-only audit via the agent loop."""

    def __init__(self) -> None:
        self._runner = AgenticRunner(REVIEW_PROFILE)

    def execute(
        self,
        prompt: str,
        context: dict[str, Any],
        history: list[dict[str, str]],
        callbacks: dict[str, Callable],
    ) -> dict[str, Any]:
        # Append the severity checklist to the prompt so the model has the
        # review structure in mind before the loop starts.
        review_prompt = (
            f"{prompt}\n\n"
            "Please provide a structured code review covering:\n"
            "1. **Security** — vulnerabilities, injection risks, auth issues\n"
            "2. **Bugs** — logic errors, edge cases, null checks\n"
            "3. **Performance** — bottlenecks, unnecessary operations\n"
            "4. **Code Quality** — readability, naming, DRY, complexity\n"
            "5. **Architecture** — design patterns, coupling, separation of concerns\n\n"
            "For each issue found, specify:\n"
            "- Severity: 🔴 Critical | 🟡 Warning | 🔵 Info\n"
            "- File and line (if applicable)\n"
            "- Description and suggested fix"
        )
        return self._runner.run(review_prompt, context, callbacks)
