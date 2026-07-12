"""EditMode — controlled single-file edit mode, now agentic.

The mode still surfaces a single diff to the user for approval (the
``on_diff`` callback emits the patch and the runtime shows the diff UI),
but the underlying loop is the same Hermes agent loop used by Agent mode.
The runner profile restricts the loop to read-first, then write_file or
diff, then run_command for verification.
"""

import logging
from typing import Any, Callable

from nexcoder.agent.agentic_runner import AgenticRunner
from nexcoder.agent.mode_profiles import EDIT_PROFILE

logger = logging.getLogger(__name__)


class EditMode:
    """Edit mode — generates patches for approval via the agent loop."""

    def __init__(self) -> None:
        self._runner = AgenticRunner(EDIT_PROFILE)

    def execute(
        self,
        prompt: str,
        context: dict[str, Any],
        history: list[dict[str, str]],
        callbacks: dict[str, Callable],
    ) -> dict[str, Any]:
        return self._runner.run(prompt, context, callbacks)
