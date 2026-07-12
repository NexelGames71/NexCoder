"""AskMode — read-only agentic question/answer mode."""

import logging
from typing import Any, Callable

from nexcoder.agent.agentic_runner import AgenticRunner
from nexcoder.agent.mode_profiles import ASK_PROFILE

logger = logging.getLogger(__name__)


class AskMode:
    """Read-only mode — answers questions by inspecting project files.

    Backed by the Hermes agent loop with a read-only profile (no writes, no
    shell). The runner extracts the model's ``<final_answer>`` summary and
    streams it to the frontend; intermediate tool activity (read_file,
    search_grep, list_directory) is surfaced through ``status_update``.
    """

    def __init__(self) -> None:
        self._runner = AgenticRunner(ASK_PROFILE)

    def execute(
        self,
        prompt: str,
        context: dict[str, Any],
        history: list[dict[str, str]],
        callbacks: dict[str, Callable],
    ) -> dict[str, Any]:
        return self._runner.run(prompt, context, callbacks)
