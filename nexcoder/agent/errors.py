"""Custom exceptions and structured error envelopes for NexCoder.

Two distinct kinds of errors flow through the system:

- **Exceptions** — raised internally between Python layers (the agent
  runtime, the loop, the executor, the tool registry). Each carries
  enough context for the surrounding layer to surface a useful message
  to the UI.

- **ErrorEnvelope** — a JSON-serialisable structure used at every
  boundary that crosses from Python into the React frontend (every
  ``@Slot`` return, every ``agent_complete`` payload, every tool
  result that flows back through the bridge). The UI renders the
  ``category`` as a badge colour and uses ``retryable`` to decide
  whether to surface a "Retry" button.

The error kinds:

- :class:`AgentContractError` — the model did not produce a usable tool
  call or final-answer block after the configured retry budget. The
  runtime surfaces this to the UI as a structured failure
  (``agent_complete`` with ``error_kind == "agent_contract_failure"``)
  so the user sees a clear message instead of a silent fallback.

- :class:`AgentExecutionError` — a tool call or model call raised an
  underlying exception (network error, blocked command, etc.) that is
  not a contract violation.

- :class:`AgentCancelledError` — a cooperative cancellation was
  observed. Carries the cancel reason so the UI can show
  "Stopped by user" vs "Stopped: token budget exceeded".

- :class:`ErrorEnvelope` — the serialisable shape used for every error
  that crosses the bridge. See :func:`envelope_from_exception`.
"""

from __future__ import annotations

import logging
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AgentError(Exception):
    """Base class for agent runtime errors."""


class AgentContractError(AgentError):
    """The model did not honour the tool-call / final-answer contract.

    Attributes:
        mode: The mode name (ask, edit, agent, debug, review).
        attempts: Number of turns the runner used before giving up.
        last_response: Truncated text of the last assistant message, useful
            for the UI to show *what* the model said instead of the contract.
    """

    def __init__(self, mode: str, attempts: int, last_response: str = "") -> None:
        self.mode = mode
        self.attempts = attempts
        self.last_response = last_response
        snippet = (last_response or "").strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "..."
        message = (
            f"The model did not produce a tool call or final-answer block "
            f"after {attempts} attempts in {mode!r} mode."
        )
        if snippet:
            message += f" Last response: {snippet!r}"
        super().__init__(message)


class AgentExecutionError(AgentError):
    """A tool call or model call failed for non-contract reasons."""


class ModelStreamError(AgentExecutionError):
    """The model stream failed before a complete assistant response arrived."""

    code = "model_stream_interrupted"


class ModelUnavailableError(AgentExecutionError):
    """The configured model endpoint could not be reached."""

    code = "model_unavailable"


class ModelHTTPError(AgentExecutionError):
    """The model endpoint returned a non-success HTTP status."""

    code = "model_http_error"


class AgentCancelledError(AgentError):
    """The agent run was cancelled before it could finish cleanly.

    Raised by cooperative cancellation checks. The ``reason`` attribute
    carries a short explanation ("cancelled by user", "token budget
    exceeded", etc.) so the UI can show a meaningful message.
    """

    def __init__(self, reason: str = "cancelled") -> None:
        self.reason = reason
        super().__init__(f"Agent run cancelled: {reason}")


# ── ErrorEnvelope ─────────────────────────────────────────────────────
#
# A serialisable error record that crosses the QWebChannel boundary.
# Every ``@Slot`` and every ``agent_complete`` payload uses this shape
# instead of returning ``{"success": False, "error": str(e)}``.


# Stable error codes the UI can branch on. Add new codes by appending;
# never repurpose an existing one because the UI uses them as keys.
ERROR_CODES: dict[str, str] = {
    # Cancellation
    "agent_cancelled": "Agent run was cancelled",
    # Contract / model output shape
    "agent_contract_failure": "Model did not produce a valid tool call or final answer",
    "tool_parse_error": "Could not parse tool call arguments",
    # Tool layer
    "tool_blocked": "Tool call was blocked by safety policy",
    "tool_not_found": "Unknown tool",
    "tool_unknown_tool": "Tool registry has no handler for this tool",
    "tool_invalid_args": "Tool call had invalid arguments",
    "tool_exception": "Tool raised an unexpected exception",
    "tool_timeout": "Tool exceeded its time budget",
    "tool_duplicate": "Duplicate tool call was blocked",
    "tool_path_blocked": "Path is outside the active project",
    "tool_file_not_found": "File not found",
    "tool_file_too_large": "File exceeds read limit",
    "tool_directory_not_found": "Directory not found",
    "tool_skill_not_found": "Unknown skill id",
    "tool_sensitive_file": "Write blocked: file is on the sensitive-file list",
    "tool_command_blocked": "Command is on the blocked-command list",
    "tool_command_failed": "Command exited with a non-zero status",
    # Model layer
    "model_unavailable": "Cannot reach the AI backend",
    "model_http_error": "AI backend returned an HTTP error",
    "model_invalid_response": "AI backend returned a malformed response",
    "model_stream_interrupted": "Streaming response was interrupted",
    # Session / persistence
    "session_not_found": "Session not found",
    "session_corrupt": "Session file is corrupt or unreadable",
    "session_save_failed": "Could not write session to disk",
    # Redaction
    "redaction_failed": "Could not redact sensitive content",
    # Generic
    "internal_error": "Unexpected internal error",
    "not_implemented": "Feature not yet implemented",
    "invalid_args": "Invalid arguments",
    "no_active_project": "No project is currently open",
}


# Categories drive UI affordances (badge colour, retry button, severity
# in chat). Keep this small and stable.
ERROR_CATEGORIES = {"user_recoverable", "system", "contract", "safety", "internal"}


@dataclass
class ErrorEnvelope:
    """Structured error returned across the bridge.

    The ``code`` field is the stable key the UI branches on. The
    ``category`` drives UI affordances. ``message`` is the human-readable
    line that goes in the chat pane. ``details`` carries optional
    structured context (file paths, exit codes, etc.) the UI can render
    inline. ``retryable`` hints whether the UI should show a retry
    button — most system / network errors are retryable; contract and
    safety errors are not.
    """

    code: str
    message: str
    category: str = "internal"
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    traceback: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_exception(
        cls,
        exc: BaseException,
        *,
        code: Optional[str] = None,
        category: Optional[str] = None,
        retryable: Optional[bool] = None,
        details: Optional[dict[str, Any]] = None,
        include_traceback: bool = False,
    ) -> "ErrorEnvelope":
        """Build an envelope from a Python exception.

        ``code`` defaults to the exception class's ``code`` attribute
        (if it has one) or ``"internal_error"``. ``category`` defaults
        based on the exception type. The full traceback is included
        only when ``include_traceback`` is true — usually only when
        debug logging is on.
        """
        resolved_code = code or getattr(exc, "code", None) or _code_from_exception(exc)
        resolved_category = category or _category_from_exception(exc, resolved_code)
        resolved_retryable = (
            retryable if retryable is not None else _retryable_from_category(resolved_category)
        )
        tb = traceback.format_exc() if include_traceback else None
        return cls(
            code=resolved_code,
            message=str(exc) or ERROR_CODES.get(resolved_code, "Unknown error"),
            category=resolved_category,
            details=dict(details or {}),
            retryable=resolved_retryable,
            traceback=tb,
        )


def _code_from_exception(exc: BaseException) -> str:
    """Map a Python exception to a stable error code."""
    if isinstance(exc, AgentCancelledError):
        return "agent_cancelled"
    if isinstance(exc, AgentContractError):
        return "agent_contract_failure"
    name = exc.__class__.__name__
    # Convention: ``FooError`` → ``foo_error`` so callers don't have to
    # hand-write every mapping. The few that need a different code
    # carry a ``code`` attribute (e.g. subclasses can override).
    if name.endswith("Error"):
        return _snake_case(name[:-5]) + "_error"
    return "internal_error"


def _snake_case(name: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _category_from_exception(exc: BaseException, code: str) -> str:
    if isinstance(exc, AgentCancelledError):
        return "user_recoverable"
    if isinstance(exc, AgentContractError):
        return "contract"
    if code in {"tool_blocked", "tool_command_blocked", "tool_sensitive_file"}:
        return "safety"
    if code.startswith("model_"):
        return "system"
    if code == "tool_command_failed":
        return "user_recoverable"
    if code == "tool_duplicate":
        return "contract"
    return "internal"


def _retryable_from_category(category: str) -> bool:
    return category in {"system", "user_recoverable"}


def envelope_from_exception(
    exc: BaseException,
    *,
    code: Optional[str] = None,
    category: Optional[str] = None,
    retryable: Optional[bool] = None,
    details: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Convenience wrapper: returns the envelope as a plain dict."""
    return ErrorEnvelope.from_exception(
        exc,
        code=code,
        category=category,
        retryable=retryable,
        details=details,
    ).to_dict()


__all__ = [
    "AgentError",
    "AgentContractError",
    "AgentExecutionError",
    "AgentCancelledError",
    "ErrorEnvelope",
    "ERROR_CODES",
    "ERROR_CATEGORIES",
    "envelope_from_exception",
]
