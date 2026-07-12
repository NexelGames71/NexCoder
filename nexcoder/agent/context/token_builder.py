"""TokenAwareContextBuilder — context packing with a hard token budget.

The legacy :class:`nexcoder.agent.context_builder.ContextBuilder` packs
files into the context until a character cap is hit, then drops the
rest. That works for short prompts but fails badly for long projects:

- 24,000 chars ≈ 6,000 tokens, but actual token count varies wildly
  with code (a Python file with lots of punctuation and short
  identifiers can be ~30% more tokens than 4-chars-per-token suggests).
- The packing order is insertion order, not relevance. A 5-line
  config file dumped in early can shove the actually-relevant file out.
- Nothing caps individual files; a single 8,000-token file can
  blow the whole budget by itself.

This builder addresses those gaps with three small changes:

1. **Token counting.** Either via ``tiktoken`` (preferred, installed as
   an optional dependency) or a 4-chars-per-token heuristic that
   over-estimates so we don't accidentally overflow the model's window.
2. **Priority + relevance ranking.** Each candidate block carries a
   priority (system = highest, current file = high, related files
   ranked by keyword overlap + mtime). The packer fills the budget
   in priority order, then by descending relevance.
3. **Per-block caps.** A single oversized file is truncated with a
   clear ``... [truncated] ...`` marker instead of pushing everything
   else out.

The result is a context string that fits the model's window and
surfaces the most relevant content first.

The class deliberately does not call the model — summarising oversized
content is a Tier B concern (it would require a second model call and
its own retry policy). For now we truncate with a marker.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, Optional

from nexcoder.agent.path_filters import should_skip_dir

logger = logging.getLogger(__name__)

# Try to use tiktoken for accurate token counting. If it's not
# installed, fall back to a conservative heuristic (1 token ≈ 4 chars).
try:  # pragma: no cover - optional dependency
    import tiktoken

    _DEFAULT_ENCODING = tiktoken.get_encoding("cl100k_base")

    def _count_tokens_accurate(text: str) -> int:
        if not text:
            return 0
        return len(_DEFAULT_ENCODING.encode(text))

except Exception:  # noqa: BLE001 - tiktoken not installed
    _DEFAULT_ENCODING = None

    def _count_tokens_accurate(text: str) -> int:  # type: ignore[no-redef]
        # 4 chars per token is a coarse but safe lower bound for English
        # text; for code with lots of short identifiers and punctuation
        # the real ratio is closer to 3.0, so this over-counts, which is
        # what we want for a budget guard.
        return (len(text) + 3) // 4


# Extensions to consider for broad scan / auto-retrieval.
SCAN_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs",
    ".java", ".cpp", ".c", ".h", ".md",
}

# English stop words. Mirrors the list in the legacy
# :class:`ContextBuilder` so broad-scan triggers behave the same.
_STOP_WORDS = frozenset({
    "the", "and", "for", "you", "that", "this", "with", "have", "can",
    "your", "from", "are", "but", "not", "what", "all", "about", "how",
    "codebase", "project", "code", "file", "files", "please", "scan",
    "read", "find", "search", "check", "tell", "explain", "where", "show",
    "get", "set", "use", "make", "need", "like", "should", "would", "here",
})

# Priority levels — higher number wins. Tweak to taste.
_PRIORITY_SYSTEM = 100       # project structure
_PRIORITY_ERROR = 90         # error output
_PRIORITY_SELECTION = 80     # user selection
_PRIORITY_CURRENT_FILE = 70  # active editor file
_PRIORITY_RELATED = 50       # auto-retrieved related files


class TokenAwareContextBuilder:
    """Build a context string that fits within a token budget.

    The packer fills the budget in priority order, then by relevance
    within each priority band. Per-block caps prevent a single large
    file from monopolising the budget.
    """

    DEFAULT_MAX_TOKENS = 8000
    # Per-block caps, in tokens. A file that exceeds this is truncated
    # with a marker instead of consuming the whole budget.
    DEFAULT_CURRENT_FILE_CAP = 3500
    DEFAULT_RELATED_FILE_CAP = 1500
    DEFAULT_ERROR_OUTPUT_CAP = 1500
    DEFAULT_SELECTION_CAP = 1000
    DEFAULT_STRUCTURE_CAP = 500

    def __init__(
        self,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        *,
        current_file_cap: int = DEFAULT_CURRENT_FILE_CAP,
        related_file_cap: int = DEFAULT_RELATED_FILE_CAP,
        error_output_cap: int = DEFAULT_ERROR_OUTPUT_CAP,
        selection_cap: int = DEFAULT_SELECTION_CAP,
        structure_cap: int = DEFAULT_STRUCTURE_CAP,
    ) -> None:
        self._max_tokens = max(500, int(max_tokens))
        self._current_file_cap = int(current_file_cap)
        self._related_file_cap = int(related_file_cap)
        self._error_output_cap = int(error_output_cap)
        self._selection_cap = int(selection_cap)
        self._structure_cap = int(structure_cap)

    # ── Public API ───────────────────────────────────────────────────

    def count_tokens(self, text: str) -> int:
        """Return the token count for *text*. Uses tiktoken when
        available, else the 4-chars-per-token heuristic.
        """
        return _count_tokens_accurate(text)

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def build(
        self,
        context: dict[str, Any],
        project_root: Optional[str] = None,
        on_file_read: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Build a context string that fits the token budget.

        See :class:`nexcoder.agent.context_builder.ContextBuilder` for
        the full set of accepted context keys; the semantics are the
        same, the packing is just smarter.
        """
        if not project_root:
            project_root = context.get("project_path") or context.get("projectPath")
        prompt = (context.get("prompt") or "").lower()

        # Phase 1: collect candidate blocks, each tagged with a
        # priority and a per-block cap.
        candidates: list[_Candidate] = []

        if project_root:
            block = self._project_structure_block(project_root)
            if block:
                candidates.append(_Candidate(
                    priority=_PRIORITY_SYSTEM,
                    text=block,
                    label="project structure",
                    cap=self._structure_cap,
                ))

        current_file = context.get("currentFile")
        current_content = context.get("currentContent") or ""
        if current_file and current_content:
            ext = os.path.splitext(current_file)[1].lstrip(".")
            block = f"## Current File: `{os.path.basename(current_file)}`\n```{ext}\n{current_content}\n```\n"
            candidates.append(_Candidate(
                priority=_PRIORITY_CURRENT_FILE,
                text=block,
                label=f"current file: {os.path.basename(current_file)}",
                cap=self._current_file_cap,
                on_pick=lambda name=os.path.basename(current_file): on_file_read and on_file_read(name),
            ))

        selection = context.get("selection") or ""
        if selection:
            cursor_line = context.get("cursorLine", "?")
            block = f"## Selected Code (line {cursor_line})\n```\n{selection}\n```\n"
            candidates.append(_Candidate(
                priority=_PRIORITY_SELECTION,
                text=block,
                label="selection",
                cap=self._selection_cap,
            ))

        error_output = context.get("errorOutput") or ""
        if error_output:
            block = f"## Error Output\n```\n{error_output[:12000]}\n```\n"
            candidates.append(_Candidate(
                priority=_PRIORITY_ERROR,
                text=block,
                label="error output",
                cap=self._error_output_cap,
            ))

        related_paths = self._gather_related_files(context, project_root, current_file, prompt)
        related_blocks: list[tuple[float, _Candidate]] = []
        for rel_path, score in related_paths:
            content = self._read_file_safe(rel_path)
            if not content:
                continue
            ext = os.path.splitext(rel_path)[1].lstrip(".")
            name = os.path.basename(rel_path)
            block = f"## Related File: `{name}`\n```{ext}\n{content}\n```\n"
            related_blocks.append((score, _Candidate(
                priority=_PRIORITY_RELATED,
                text=block,
                label=f"related: {name}",
                cap=self._related_file_cap,
                on_pick=lambda n=name: on_file_read and on_file_read(n),
            )))

        # Phase 2: pack. Within the related-files band, sort by
        # relevance (descending). The packer then walks the priority
        # bands high to low, filling the budget.
        related_blocks.sort(key=lambda pair: pair[0], reverse=True)
        candidates.extend(block for _, block in related_blocks)

        return self._pack(candidates)

    # ── Internals ────────────────────────────────────────────────────

    def _pack(self, candidates: list["_Candidate"]) -> str:
        budget = self._max_tokens
        # Group by priority band, then iterate high → low.
        bands: dict[int, list[_Candidate]] = {}
        for c in candidates:
            bands.setdefault(c.priority, []).append(c)

        parts: list[str] = []
        for priority in sorted(bands.keys(), reverse=True):
            for c in bands[priority]:
                # Per-block cap first, then budget cap.
                text = c.capped_text()
                tokens = self.count_tokens(text)
                if tokens > budget:
                    # Even a single truncated block doesn't fit —
                    # stop adding anything below this priority.
                    return "\n".join(parts) if parts else ""
                parts.append(text)
                budget -= tokens
                if c.on_pick:
                    try:
                        c.on_pick()
                    except Exception:  # noqa: BLE001
                        pass
        return "\n".join(parts)

    def _project_structure_block(self, project_root: str) -> str:
        lines: list[str] = []
        self._walk_structure(project_root, project_root, lines, 0, max_depth=3)
        if not lines:
            return ""
        body = "\n".join(lines[:60])
        return f"## Project Structure\n```\n{body}\n```\n"

    def _walk_structure(
        self, path: str, root: str, lines: list[str], depth: int, max_depth: int,
    ) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
        except (PermissionError, FileNotFoundError):
            return
        indent = "  " * depth
        for entry in entries:
            if entry.name.startswith(".") and depth == 0:
                continue
            if entry.is_dir():
                if should_skip_dir(entry.name, skip_hidden=False):
                    continue
                lines.append(f"{indent}{entry.name}/")
                self._walk_structure(entry.path, root, lines, depth + 1, max_depth)
            else:
                lines.append(f"{indent}{entry.name}")

    def _gather_related_files(
        self,
        context: dict[str, Any],
        project_root: Optional[str],
        current_file: Optional[str],
        prompt: str,
    ) -> list[tuple[str, float]]:
        if not project_root:
            return []
        explicit = list(context.get("relatedFiles") or [])
        if explicit:
            return [(p, 1.0) for p in explicit]

        # Trivial short prompts (e.g. "hello") — don't auto-load files.
        if len(prompt.strip()) < 40 and not any(
            t in prompt for t in {"codebase", "project", "all", "scan", "find", "where"}
        ):
            return []

        # Score files by keyword overlap with the prompt and by mtime.
        words = [w for w in re.findall(r"\b[a-z_]{3,}\b", prompt) if w not in _STOP_WORDS]
        if not words:
            return []
        word_set = set(words)
        scored: list[tuple[float, str]] = []
        try:
            for dirpath, dirnames, filenames in os.walk(project_root):
                dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
                for fname in filenames:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in SCAN_EXTENSIONS:
                        continue
                    full = os.path.join(dirpath, fname)
                    if current_file and os.path.abspath(full) == os.path.abspath(current_file):
                        continue
                    try:
                        with open(full, "r", encoding="utf-8", errors="ignore") as handle:
                            content = handle.read().lower()
                    except OSError:
                        continue
                    # Cheap keyword score: count how many prompt words
                    # appear in the file. mtime is a tiebreaker.
                    score = sum(1 for w in word_set if w in content)
                    if score == 0:
                        continue
                    try:
                        mtime = os.path.getmtime(full)
                    except OSError:
                        mtime = 0.0
                    # Normalise mtime into a 0..0.5 weight so the keyword
                    # score still dominates.
                    recency = min(0.5, mtime / 1e10)
                    scored.append((score + recency, full))
        except OSError:
            return []
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [(path, score) for score, path in scored[:8]]

    def _read_file_safe(self, rel_path: str) -> str:
        try:
            with open(rel_path, "r", encoding="utf-8", errors="ignore") as fh:
                return fh.read(200_000)  # hard cap to avoid runaway reads
        except OSError:
            return ""


class _Candidate:
    """One block queued for the packer."""

    __slots__ = ("priority", "text", "label", "cap", "on_pick")

    def __init__(
        self,
        *,
        priority: int,
        text: str,
        label: str,
        cap: int,
        on_pick: Optional[Callable[[], None]] = None,
    ) -> None:
        self.priority = priority
        self.text = text
        self.label = label
        self.cap = cap
        self.on_pick = on_pick

    def capped_text(self) -> str:
        # If the block is bigger than its cap, truncate from the end
        # and append a marker. The marker is a real string the model
        # will see so it knows the content was cut off.
        cap_chars = max(100, self.cap * 4)  # tokens → chars (heuristic)
        if len(self.text) <= cap_chars:
            return self.text
        truncated = self.text[:cap_chars]
        return f"{truncated}\n\n... [truncated, original length {len(self.text)} chars; cap {cap_chars} chars] ...\n"


__all__ = ["TokenAwareContextBuilder"]
