"""Intent routing — decide how to handle a user prompt before the agent loop.

Cursor-style agents route trivial chat to a direct reply, code questions to
read-only exploration, and create/edit/fix tasks to the full write-capable loop.

This module exposes two related but distinct classifiers:

- :func:`classify_prompt` returns the short-form :data:`Intent` (``chat``,
  ``read``, ``write``, ``scan``) used by the runtime to skip the loop for
  greetings or to enter the autonomous mode.
- :func:`classify_task_type` returns the longer :data:`TaskType` enumeration
  (``question | scan | implement | edit | debug | review``) the runner uses
  to decide what *kind* of final artifact the task is allowed to produce.
  Read-only task types (``question``, ``scan``, ``review``) MUST end with a
  ``final_answer`` object — they cannot be marked complete with raw tool
  activity alone. Write-capable task types (``implement``, ``edit``,
  ``debug``) require a patch, an approval request, or a validation report.
"""

from __future__ import annotations

import re
from typing import Literal

# Short-form intent. Drives loop entry decisions.
Intent = Literal["chat", "read", "write", "scan"]

# Long-form task type. Drives the final-artifact contract.
TaskType = Literal[
    "question",
    "scan",
    "implement",
    "edit",
    "debug",
    "review",
]

_GREETING_RE = re.compile(
    r"^\s*(?:hi|hello|hey|yo|sup|howdy|good\s+(?:morning|afternoon|evening)|"
    r"what(?:'s|\s+is)\s+up|thanks?(\s+you)?|thank\s+you|thx|"
    r"bye|goodbye|see\s+ya|who\s+are\s+you|what\s+are\s+you)\b",
    re.IGNORECASE,
)

_META_RE = re.compile(
    r"^\s*(?:help|what\s+can\s+you\s+do|how\s+do\s+(?:i|you)\s+use)\b",
    re.IGNORECASE,
)

_WRITE_RE = re.compile(
    r"\b(?:create|add|write|build|implement|generate|make|fix|patch|update|"
    r"refactor|rename|delete|remove|migrate|scaffold|setup|set\s+up|"
    r"install|deploy|convert|rewrite|modify|change|edit)\b",
    re.IGNORECASE,
)

_SCAN_RE = re.compile(
    r"\b(?:scan\s+(?:the\s+)?(?:project|codebase)|codebase\s+map|"
    r"project\s+overview|understand\s+the\s+project|scan\s+through|"
    r"summarise\s+the\s+(?:project|codebase)|summarize\s+the\s+(?:project|codebase))\b",
    re.IGNORECASE,
)

_READ_RE = re.compile(
    r"\b(?:what\s+is|what(?:'s|\s+are)|explain|describe|how\s+does|"
    r"where\s+is|show\s+me|tell\s+me|summarize|overview|review|analyze|"
    r"find|search|look\s+at|read|inspect|list|which|why|"
    r"what\s+does\b)\b",
    re.IGNORECASE,
)

_DEBUG_RE = re.compile(
    r"\b(?:debug|error|exception|traceback|stack\s*trace|"
    r"failing|fails|crash(?:es|ed)?|broken|bug|"
    r"why\s+is\s+(?:it|this)\s+(?:not\s+working|failing)|"
    r"doesn'?t\s+work|does\s+not\s+work)\b",
    re.IGNORECASE,
)


def classify_prompt(prompt: str, mode: str = "ask") -> Intent:
    """Return the best intent for *prompt* given the active UI mode."""
    text = (prompt or "").strip()
    if not text:
        return "chat"

    if _SCAN_RE.search(text):
        return "scan"

    # Short greetings and meta questions → direct chat, no tools.
    if len(text) <= 80 and (_GREETING_RE.match(text) or _META_RE.match(text)):
        return "chat"

    # Write-capable modes with action verbs → must produce file changes.
    if mode in {"agent", "edit", "debug"} and _WRITE_RE.search(text):
        return "write"

    # Explicit create/edit language in any mode.
    if _WRITE_RE.search(text) and re.search(
        r"\b(?:file|component|page|module|class|function|test|api|route|"
        r"endpoint|feature|script|config|showcase|readme)\b",
        text,
        re.IGNORECASE,
    ):
        return "write"

    if _READ_RE.search(text):
        return "read"

    # Agent/edit/debug default to write when the task sounds actionable.
    if mode in {"agent", "edit", "debug"} and len(text) > 20:
        return "write"

    return "read" if len(text) > 15 else "chat"


def classify_task_type(prompt: str, mode: str = "ask") -> TaskType:
    """Return the task type for *prompt*.

    The task type tells the runner what *kind* of final artifact the user
    is asking for. Read-only question/scan/review tasks must produce a
    ``final_answer``; edit/implement/debug tasks must produce a patch,
    approval request, or validation report.
    """
    text = (prompt or "").strip()

    # Mode short-circuits for tasks the user already selected from the UI.
    if mode in {"review"}:
        return "review"
    if mode in {"debug"}:
        return "debug"
    if mode in {"edit"}:
        return "edit"
    if mode in {"agent"}:
        # Agent mode defaults to "implement" (write-capable) but scan/question
        # patterns are still recognised.
        if _SCAN_RE.search(text):
            return "scan"
        if _READ_RE.search(text) and not _WRITE_RE.search(text):
            return "question"
        if _DEBUG_RE.search(text):
            return "debug"
        if _WRITE_RE.search(text):
            return "implement"
        if text and not _WRITE_RE.search(text) and not _READ_RE.search(text):
            # Bare "do something" with no verbs still defaults to implement.
            return "implement"
        return "question"

    # Ask / no mode selected — pick the read-only task type.
    if _SCAN_RE.search(text):
        return "scan"
    if _DEBUG_RE.search(text) and mode in {"agent", "edit", "debug"}:
        return "debug"
    if _READ_RE.search(text):
        return "question"
    return "question"


# Convenience mapping used by the runtime to decide the final-artifact rule.
TASK_TYPE_REQUIRES_FINAL_ANSWER: frozenset[TaskType] = frozenset(
    {"question", "scan", "review"}
)
TASK_TYPE_REQUIRES_EDITS: frozenset[TaskType] = frozenset(
    {"implement", "edit", "debug"}
)


def requires_file_changes(intent: Intent) -> bool:
    """True when the task should not be marked complete without writes."""
    return intent == "write"


def allows_direct_reply(intent: Intent) -> bool:
    """True when the prompt can skip the tool loop entirely."""
    return intent == "chat"


def task_type_requires_final_answer(task_type: TaskType) -> bool:
    """True for read-only task types that must end with a ``final_answer``."""
    return task_type in TASK_TYPE_REQUIRES_FINAL_ANSWER


def task_type_requires_edits(task_type: TaskType) -> bool:
    """True for write-capable task types that must end with a patch / diff."""
    return task_type in TASK_TYPE_REQUIRES_EDITS
