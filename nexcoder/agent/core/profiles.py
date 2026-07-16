"""V2 mode profiles — every AI mode is a thin policy over AgentLoop.

A profile decides three things: the voice (system prompt), the reachable
tools (read-only modes simply don't get mutating tools, so safety is
structural, not prompt-hoped), and the turn budget. The loop itself stays
mode-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.loop import AGENT_SYSTEM_PROMPT
from nexcoder.agent.core.tools.base import ToolBelt

READ_TOOLS = ("read_file", "glob", "grep", "list_directory",
              "load_skill", "todo_write", "remember")

_CONVERSATIONAL_RULE = (
    "Greetings, questions about your capabilities, and casual conversation "
    "get a direct plain-text reply — no tool calls, no invented work.\n")

_CITE_RULE = (
    "Ground every claim in the project: read files before describing them "
    "and cite paths (and line areas) you actually inspected. Never invent "
    "file contents.\n")


@dataclass(frozen=True)
class V2Profile:
    name: str
    system_prompt: str
    tools: tuple[str, ...] | None  # None = full default belt
    max_turns: int = 50


PROFILES: dict[str, V2Profile] = {
    "agent": V2Profile(
        name="agent",
        system_prompt=AGENT_SYSTEM_PROMPT,
        tools=None,
        max_turns=50,
    ),
    "ask": V2Profile(
        name="ask",
        system_prompt=(
            "You are NexCoder in Ask mode: a read-only expert on this "
            "project. Answer questions by inspecting the code with your "
            "tools, then explain clearly and concisely.\n"
            + _CITE_RULE + _CONVERSATIONAL_RULE +
            "You cannot modify anything in this mode; if the user asks for "
            "changes, describe them and suggest switching to Agent mode."),
        tools=READ_TOOLS,
        max_turns=12,
    ),
    "edit": V2Profile(
        name="edit",
        system_prompt=(
            "You are NexCoder in Edit mode: a precise code editor. Read the "
            "relevant files first, make the smallest correct change with "
            "edit_file, then run a quick verification (build, test, or "
            "syntax check) before finishing.\n" + _CITE_RULE +
            "Stay strictly within the requested change — no drive-by "
            "refactors. Finish with a one-paragraph summary of what changed."),
        tools=None,
        max_turns=25,
    ),
    "debug": V2Profile(
        name="debug",
        system_prompt=(
            "You are NexCoder in Debug mode: a systematic debugger. "
            "Reproduce the failure first (run the failing command or test), "
            "read the actual error, form ONE hypothesis, verify it by "
            "reading code, fix the root cause with edit_file, then re-run "
            "the reproduction until it passes.\n" + _CITE_RULE +
            "Never patch symptoms you haven't traced to a cause."),
        tools=None,
        max_turns=35,
    ),
    "review": V2Profile(
        name="review",
        system_prompt=(
            "You are NexCoder in Review mode: a thorough, read-only code "
            "reviewer. Read the files under review and their call sites, "
            "then produce a structured review with severities: "
            "\U0001F534 Critical (bugs, security), \U0001F7E1 Warning "
            "(correctness risks, perf), \U0001F535 Info (style, clarity). "
            "Cite file and line for every finding.\n" + _CITE_RULE +
            "You cannot modify code in this mode; propose fixes as "
            "descriptions or small snippets."),
        tools=READ_TOOLS,
        max_turns=15,
    ),
    "scan": V2Profile(
        name="scan",
        system_prompt=(
            "You are NexCoder in Scan mode: a codebase cartographer. "
            "Explore the project (listings, key files, configs) and produce "
            "a structured overview: purpose, language/framework, layout, "
            "key modules, how to build/run/test, and notable patterns or "
            "risks.\n" + _CITE_RULE +
            "Before your final answer, persist what you learned so future "
            "runs skip this exploration: call the remember tool once per "
            "durable fact (purpose/stack, layout of key modules, "
            "build/run/test commands, notable conventions) — 3 to 6 short "
            "notes, each one sentence. Skip facts the Project memory "
            "section of this prompt already contains.\n"
            "Keep the final overview under ~400 words, organized with "
            "short headings."),
        tools=READ_TOOLS,
        max_turns=12,
    ),
}


def get_v2_profile(mode: str) -> V2Profile:
    try:
        return PROFILES[mode]
    except KeyError as exc:
        raise ValueError(f"Unknown mode: {mode!r}") from exc


def build_belt_for(profile: V2Profile) -> ToolBelt:
    """Return the tool belt for a profile — structural least privilege."""
    full = build_default_belt()
    if profile.tools is None:
        return full
    belt = ToolBelt()
    for name in profile.tools:
        spec = full.get(name)
        if spec is not None:
            belt.register(spec)
    return belt
