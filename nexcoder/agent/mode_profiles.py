"""ModeProfile — per-mode policy for the agentic runner.

A mode profile captures everything the runner needs to enforce *outside* of
the LLM tool calls themselves:

- which tools the model is allowed to invoke
- whether the mode is read-only (no file writes, no shell)
- how many turns the loop is allowed
- how many contract-violation retries before the runner gives up
- what shape the final assistant message must take

Keeping this in a dataclass lets the four mode wrappers (ask / edit / debug
/ review) stay tiny while the runner enforces policy in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# Tools the loop knows how to dispatch. Defined as a literal so a typo in a
# profile fails mypy instead of silently allowing a forbidden tool.
ToolName = Literal[
    "read_file",
    "write_file",
    "search_grep",
    "list_directory",
    "create_directory",
    "move_path",
    "run_command",
    "load_skill",
]

# Final-output shape the runner enforces on the last turn.
#
# - ``final_answer`` — the model MUST produce a structured
#   ``final_answer`` object. The runner extracts it, fills defaults, and
#   attaches it to the result so the UI can render a structured card.
# - ``write_or_diff`` — the loop must produce at least one
#   ``write_file`` call, ``diff`` block, or ``approval_request`` /
#   ``validation_report`` object. Plain prose is not enough.
# - ``any`` — the loop can return whatever the model produced. Used by
#   agent mode when the task type is unknown at profile load time.
FinalShape = Literal["final_answer", "write_or_diff", "any"]

# Task types. Mirrors the values in ``intent_router`` so the runner
# can pick a final-shape without re-classifying the prompt.
TaskType = Literal[
    "question",
    "scan",
    "implement",
    "edit",
    "debug",
    "review",
]


@dataclass(frozen=True)
class ModeProfile:
    """Policy for a single AI mode."""

    name: str
    read_only: bool
    allowed_tools: tuple[ToolName, ...]
    max_turns: int
    max_retries: int
    final_shape: FinalShape
    # The system prompt to prepend; each mode overrides this with its own
    # voice. Kept here so the runner is the single source of truth for the
    # first user-visible message.
    system_prompt: str
    # Extra instructions appended after the tool contract. Use this to
    # communicate mode-specific behaviour (e.g. "you must emit a write_file
    # call or a diff block") without forking the contract helper.
    extra_instructions: str = ""
    # Default task type for the mode. The runtime can override it via
    # ``context["task_type"]`` when it has a stronger signal (e.g. the
    # user clicked a "Scan codebase" quick-action).
    task_type: TaskType = "question"


# Sentinel tool list for read-only modes. ``load_skill`` is a read
# operation (it returns SKILL.md content from disk) so it is allowed
# alongside the file-inspection tools.
READ_TOOLS: tuple[ToolName, ...] = (
    "read_file",
    "search_grep",
    "list_directory",
    "load_skill",
)
ALL_TOOLS: tuple[ToolName, ...] = (
    "read_file",
    "write_file",
    "search_grep",
    "list_directory",
    "create_directory",
    "move_path",
    "run_command",
    "load_skill",
)


# Final-answer XML tags the model is asked to use for read-only modes. The
# runner extracts whatever is between these tags and streams it as the final
# response, so the model doesn't have to choose between prose and tool calls
# on the same turn.
FINAL_ANSWER_OPEN = "<final_answer>"
FINAL_ANSWER_CLOSE = "</final_answer>"


ASK_PROFILE = ModeProfile(
    name="ask",
    read_only=True,
    allowed_tools=READ_TOOLS,
    max_turns=6,
    max_retries=3,
    final_shape="final_answer",
    task_type="question",
    system_prompt=(
        "You are NexCoder AI, an expert coding assistant. "
        "You answer questions about code by inspecting the project directly "
        "using the available tools. Do not invent file contents or line "
        "numbers — call read_file or search_grep first."
    ),
    extra_instructions=(
        f"Wrap your final summary in {FINAL_ANSWER_OPEN}...{FINAL_ANSWER_CLOSE} tags. "
        "Do not emit any tool calls inside that block."
    ),
)

EDIT_PROFILE = ModeProfile(
    name="edit",
    read_only=False,
    allowed_tools=ALL_TOOLS,
    max_turns=10,
    max_retries=3,
    final_shape="write_or_diff",
    task_type="edit",
    system_prompt=(
        "You are NexCoder AI, an expert code editor. "
        "You make precise, minimal code changes by inspecting the relevant "
        "files first, then emitting a write_file tool call or a unified diff "
        "block. Run a verification command (build, test, typecheck) before "
        "considering the task complete."
    ),
    extra_instructions=(
        "The final turn must contain either a write_file tool call or a "
        "```diff block. Prose-only responses are not accepted as final output."
    ),
)

DEBUG_PROFILE = ModeProfile(
    name="debug",
    read_only=False,
    allowed_tools=ALL_TOOLS,
    max_turns=8,
    max_retries=3,
    final_shape="write_or_diff",
    task_type="debug",
    system_prompt=(
        "You are NexCoder AI, an expert debugger. "
        "You locate the root cause of an error by reading the offending file "
        "and searching the codebase, then propose a targeted fix. Always run "
        "a verification command (the failing test, the build) after the fix."
    ),
    extra_instructions=(
        "The final turn must contain a write_file tool call, a ```diff "
        "block, or a clear explanation if no fix is possible. Prose-only "
        "guesses are not accepted as final output."
    ),
)

REVIEW_PROFILE = ModeProfile(
    name="review",
    read_only=True,
    allowed_tools=READ_TOOLS,
    max_turns=6,
    max_retries=3,
    final_shape="final_answer",
    task_type="review",
    system_prompt=(
        "You are NexCoder AI, a thorough code reviewer. "
        "You read the relevant files, search for call sites, and produce a "
        "structured review covering security, bugs, performance, code quality, "
        "and architecture. Cite file paths and line numbers; do not invent them."
    ),
    extra_instructions=(
        f"Wrap the structured review in {FINAL_ANSWER_OPEN}...{FINAL_ANSWER_CLOSE} tags. "
        "Use severity tags (🔴 Critical, 🟡 Warning, 🔵 Info) inside that block."
    ),
)

AGENT_PROFILE = ModeProfile(
    name="agent",
    read_only=False,
    allowed_tools=ALL_TOOLS,
    max_turns=16,
    max_retries=3,
    final_shape="any",
    task_type="implement",
    system_prompt=(
        "You are NexCoder Hermes, an autonomous coding agent. "
        "You inspect files, plan changes, generate patches, and run "
        "verification commands. Do not produce markdown explanations until "
        "after tool results have been provided."
    ),
    extra_instructions=(
        "At least one useful tool call must be executed before the task is "
        "considered complete."
    ),
)

# Scan profile — read-only, narrower than ask, dedicated to producing a
# project map / overview. The runner uses this when the runtime signals
# ``task_type == "scan"`` or the user invokes the dedicated scan action.
SCAN_PROFILE = ModeProfile(
    name="scan",
    read_only=True,
    allowed_tools=READ_TOOLS,
    max_turns=4,
    max_retries=2,
    final_shape="final_answer",
    task_type="scan",
    system_prompt=(
        "You are NexCoder AI, a codebase overview assistant. "
        "You inspect a project to produce a structured summary: language, "
        "framework, key files, purpose, and any notable patterns. Use "
        "list_directory and read_file to gather facts before summarising."
    ),
    extra_instructions=(
        f"When you have enough context, emit a final-answer object inside "
        f"{FINAL_ANSWER_OPEN}...{FINAL_ANSWER_CLOSE} tags with the shape: "
        '{"type": "final_answer", "title": "Project Summary", '
        '"summary": "...", "evidence": ["..."], '
        '"files_used": ["README.md", "..."], "next_steps": ["..."]}. '
        "Do not emit any tool calls inside that block."
    ),
)


PROFILES: dict[str, ModeProfile] = {
    "ask": ASK_PROFILE,
    "edit": EDIT_PROFILE,
    "agent": AGENT_PROFILE,
    "debug": DEBUG_PROFILE,
    "review": REVIEW_PROFILE,
    "scan": SCAN_PROFILE,
}


def get_profile(mode: str) -> ModeProfile:
    """Return the profile for *mode*. Raises ``ValueError`` for unknown modes."""
    try:
        return PROFILES[mode]
    except KeyError as exc:
        raise ValueError(f"Unknown mode: {mode!r}") from exc
