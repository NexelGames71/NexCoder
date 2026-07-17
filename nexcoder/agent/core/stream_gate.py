"""StreamGate — stream model prose, suppress tool-call markup.

The model's raw output interleaves prose with tool-call payloads (XML
tags, fenced JSON, bare JSON). Users should see the prose stream live and
the actions only as structured step events — never a wall of escaped file
content. The gate forwards text up to the first tool-markup marker of a
turn and swallows the rest; the parsed tool calls arrive separately as
tool_started/tool_result events, and the full final text still travels in
run_completed.
"""

from __future__ import annotations

from typing import Callable

MARKERS = ("<tool_call", '{"name"', "```")
_HOLDBACK = max(len(marker) for marker in MARKERS) - 1

# Markers that identify raw tool-call payloads in *final* text. Code
# fences are excluded here: a legitimate final answer may contain them.
_FINAL_TEXT_MARKERS = ("<tool_call", '{"name"')


def scrub_tool_markup(text: str) -> str:
    """Strip any raw tool-call payload from user-facing final text.

    Unparseable (usually truncated) tool calls must never render as a
    wall of escaped file content in the transcript.
    """
    cut = min((index for index in
               (text.find(marker) for marker in _FINAL_TEXT_MARKERS)
               if index != -1), default=-1)
    if cut == -1:
        return text
    kept = text[:cut].rstrip()
    notice = "(a malformed tool call was removed from this message)"
    return f"{kept}\n\n{notice}" if kept else notice


class StreamGate:
    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._buffer = ""
        self._stopped = False

    def push(self, delta: str) -> None:
        if self._stopped:
            return
        self._buffer += delta
        cut = min((index for index in
                   (self._buffer.find(marker) for marker in MARKERS)
                   if index != -1), default=-1)
        if cut != -1:
            text = self._buffer[:cut]
            if text:
                self._emit(text)
            self._stopped = True
            self._buffer = ""
            return
        # Hold back enough characters that a marker split across deltas
        # cannot leak its head before we recognise it.
        if len(self._buffer) > _HOLDBACK:
            text, self._buffer = self._buffer[:-_HOLDBACK], self._buffer[-_HOLDBACK:]
            self._emit(text)

    def flush(self) -> None:
        """End of turn: release any held-back tail."""
        if not self._stopped and self._buffer:
            self._emit(self._buffer)
        self._buffer = ""
        self._stopped = False
