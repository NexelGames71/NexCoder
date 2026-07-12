"""Cancellation — cooperative cancellation for long-running agent runs.

The agent runs on a background thread (via ``ThreadPoolExecutor``) so the
Qt UI never blocks. Cooperative cancellation lets the user abort a run
without killing the worker thread — the loop checks the token between
turns, the executor checks it before each tool call, and the tool layer
checks it before expensive operations.

The token is a small, thread-safe object passed through the call chain
via ``context["_cancellation_token"]``. When no token is present the
agent runs as before — every layer falls back to a no-op check.

Usage::

    token = CancellationToken()
    runtime.run_mode("agent", prompt, {"_cancellation_token": token, ...})
    # Later, from the UI:
    runtime.cancel_active_run()  # → token.cancel()

The token is **cooperative**: it does not interrupt the running thread
on its own. Each layer must call ``raise_if_cancelled()`` (or
``is_cancelled()``) at safe checkpoints. For long-running tools like
``run_command`` the tool layer is expected to terminate the subprocess
when cancellation is observed.
"""

from __future__ import annotations

import threading
from typing import Optional

from nexcoder.agent.errors import AgentCancelledError


class CancellationToken:
    """Thread-safe single-shot cancellation flag.

    Once cancelled the token stays cancelled. Callers can pass the same
    token to multiple subsystems (e.g. model connector and tool registry)
    so they all observe the same cancel signal.
    """

    __slots__ = ("_event", "_reason")

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason: str = ""

    def cancel(self, reason: str = "cancelled by user") -> None:
        """Mark the token cancelled. Idempotent."""
        if not self._event.is_set():
            self._reason = reason
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason or "cancelled"

    def raise_if_cancelled(self) -> None:
        """Raise :class:`AgentCancelledError` if the token has been cancelled."""
        if self._event.is_set():
            raise AgentCancelledError(self._reason or "cancelled")

    def reset(self) -> None:
        """Reset the token so it can be used again. Tests only."""
        self._event.clear()
        self._reason = ""


def get_token(context: Optional[dict]) -> Optional[CancellationToken]:
    """Return the cancellation token from a context dict, or None."""
    if not context:
        return None
    token = context.get("_cancellation_token")
    return token if isinstance(token, CancellationToken) else None


__all__ = ["CancellationToken", "AgentCancelledError", "get_token"]