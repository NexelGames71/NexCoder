"""Structured final-answer synthesis for NexCoder agent tasks.

A *final answer* is the user-facing artifact produced at the end of a
read-only task (question / scan / review). It is *not* the model's raw
prose; it is a structured object the UI can render in a dedicated card.

The object shape is::

    {
        "type": "final_answer",
        "title": "Project Summary",
        "summary": "This project is a ...",
        "evidence": [
            "README.md describes ...",
            "package.json shows the project uses Next.js ...",
            "app directory contains the application routes ...",
        ],
        "files_used": ["README.md", "package.json"],
        "next_steps": [
            "Scan the app directory for page structure",
            "Inspect package scripts",
            ...
        ]
    }

The synthesis has two paths:

1. :func:`extract_final_answer_object` — parses a model response that
   contains a ``<final_answer>...</final_answer>`` block, optionally
   with a JSON object inside. Falls back to wrapping plain prose in a
   minimal final-answer envelope.

2. :func:`synthesize_from_observations` — a deterministic fallback that
   builds a final-answer object from the tool observations the loop has
   already collected. Used when the model never produces a final-answer
   block but enough context exists to answer the user's question.

The runner attaches the final-answer object to the loop result so the
UI can render it as a structured card *and* show the model prose in the
chat stream.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Final-answer XML tags. Mirrors the constants in mode_profiles so a
# future refactor keeps them in sync.
FINAL_ANSWER_OPEN = "<final_answer>"
FINAL_ANSWER_CLOSE = "</final_answer>"

# A loose JSON-object regex. We try to parse any {...} block the model
# emits, then re-wrap it. We are deliberately permissive because the
# models we target (Qwen2.5-Coder, Gemma) sometimes produce slightly
# malformed JSON.
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def extract_final_answer_object(response: str) -> dict[str, Any]:
    """Build a final-answer object from *response*.

    The function accepts three response shapes:

    - ``<final_answer>{"type":"final_answer", ...}</final_answer>`` — the
      model emitted structured JSON inside the tags. We parse it and
      normalise the required fields.
    - ``<final_answer>free-form prose</final_answer>`` — the model emitted
      prose inside the tags. We wrap it as ``summary``.
    - Bare prose with no tags — we wrap the whole response as ``summary``.

    Missing required fields are filled with sensible defaults so the
    downstream UI can always render the card.
    """
    response = (response or "").strip()
    if not response:
        return _empty_final_answer()

    inner = _strip_tags(response)
    payload = _try_parse_json_object(inner)
    if payload is not None:
        return _normalise_final_answer(payload)

    # No JSON, no tags — the whole response is the summary.
    if not _has_final_answer_tags(response):
        return _prose_only_final_answer(inner)

    return _prose_only_final_answer(inner)


def _strip_tags(text: str) -> str:
    """Return *text* with the final-answer tags removed."""
    if FINAL_ANSWER_OPEN in text and FINAL_ANSWER_CLOSE in text:
        return text.split(FINAL_ANSWER_OPEN, 1)[1].rsplit(FINAL_ANSWER_CLOSE, 1)[0].strip()
    return text.replace(FINAL_ANSWER_OPEN, "").replace(FINAL_ANSWER_CLOSE, "").strip()


def _has_final_answer_tags(text: str) -> bool:
    return FINAL_ANSWER_OPEN in text or FINAL_ANSWER_CLOSE in text


def _try_parse_json_object(text: str) -> dict[str, Any] | None:
    """Return the first JSON object in *text*, or None."""
    if not text:
        return None
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None
    candidate = match.group(0)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalise_final_answer(payload: dict[str, Any]) -> dict[str, Any]:
    """Coerce *payload* into the final-answer shape, filling defaults."""
    if payload.get("type") != "final_answer":
        payload = {**payload, "type": "final_answer"}
    if "title" not in payload or not payload["title"]:
        payload["title"] = "Answer"
    if "summary" not in payload or not payload["summary"]:
        payload["summary"] = ""
    if "evidence" not in payload or not isinstance(payload["evidence"], list):
        payload["evidence"] = []
    else:
        payload["evidence"] = [str(item) for item in payload["evidence"] if item]
    if "files_used" not in payload or not isinstance(payload["files_used"], list):
        payload["files_used"] = []
    else:
        payload["files_used"] = [str(item) for item in payload["files_used"] if item]
    if "next_steps" not in payload or not isinstance(payload["next_steps"], list):
        payload["next_steps"] = []
    else:
        payload["next_steps"] = [str(item) for item in payload["next_steps"] if item]
    return payload


def _prose_only_final_answer(prose: str) -> dict[str, Any]:
    """Wrap *prose* as a final-answer with empty structured fields."""
    return _normalise_final_answer(
        {
            "type": "final_answer",
            "title": "Answer",
            "summary": prose,
            "evidence": [],
            "files_used": [],
            "next_steps": [],
        }
    )


def _empty_final_answer() -> dict[str, Any]:
    return _prose_only_final_answer("")


# ─────────────────────────────────────────────────────────────────────
# Deterministic synthesis from tool observations
# ─────────────────────────────────────────────────────────────────────


_READ_FILE_TOOL = "read_file"
_LIST_DIRECTORY_TOOL = "list_directory"
_LIST_PROJECT_TREE_TOOL = "list_project_tree"
_SEARCH_GREP_TOOL = "search_grep"


def synthesize_from_observations(
    prompt: str,
    observations: list[dict[str, Any]],
    *,
    title: str = "Project Summary",
) -> dict[str, Any]:
    """Build a final-answer object from collected *observations*.

    *observations* is the list of ``{"tool", "args", "result"}`` dicts
    the loop has accumulated during the run. The function inspects each
    observation and pulls out:

    - ``files_used`` — the path of every file the loop read.
    - ``evidence`` — short bullet points derived from each successful
      read (first non-empty lines of the file content).
    - ``summary`` — a short synthesis paragraph stitched from the
      evidence bullets.

    The function is deliberately conservative: if the loop never read
    a file, the final-answer object has an empty ``summary`` and the
    caller should fall back to streaming the model prose instead.
    """
    files_used: list[str] = []
    evidence: list[str] = []
    seen: set[str] = set()

    for item in observations or []:
        tool = (item.get("tool") or "").strip()
        args = item.get("args") or {}
        result = item.get("result") or {}
        if not result.get("success"):
            continue

        if tool in {_READ_FILE_TOOL}:
            path = (args.get("path") or "").strip()
            if path and path not in seen:
                seen.add(path)
                files_used.append(path)
            content = (result.get("content") or "").strip()
            if content:
                snippet = _first_meaningful_lines(content, max_lines=2)
                if snippet:
                    evidence.append(f"{path}: {snippet}" if path else snippet)
        elif tool in {_LIST_DIRECTORY_TOOL, _LIST_PROJECT_TREE_TOOL}:
            path = (args.get("path") or ".").strip() or "."
            entries = result.get("entries") or []
            if entries:
                sample = ", ".join(
                    (e.get("name") or "") for e in entries[:8] if e.get("name")
                )
                if sample:
                    evidence.append(f"Listed {path}: {sample}")
        elif tool in {_SEARCH_GREP_TOOL}:
            query = (args.get("query") or "").strip()
            results = result.get("results") or []
            if query and results:
                evidence.append(
                    f"Search for {query!r} returned {len(results)} match(es)."
                )

    summary = _build_summary(prompt, evidence, files_used)
    next_steps = _suggest_next_steps(prompt, files_used, observations)

    return _normalise_final_answer(
        {
            "type": "final_answer",
            "title": title,
            "summary": summary,
            "evidence": evidence[:10],
            "files_used": files_used[:10],
            "next_steps": next_steps[:5],
        }
    )


def _first_meaningful_lines(content: str, *, max_lines: int = 2) -> str:
    """Return the first non-empty, non-comment-ish line of *content*."""
    keep = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Skip obvious comment-only lines so the evidence is informative.
        if line.startswith(("#", "//", '"""', "'''", "/*", "*")):
            continue
        keep.append(line)
        if len(keep) >= max_lines:
            break
    return " ".join(keep)[:240]


def _build_summary(
    prompt: str, evidence: list[str], files_used: list[str]
) -> str:
    if not evidence:
        return ""
    if files_used:
        head = (
            f"Inspected {len(files_used)} file(s) to answer: {prompt.strip()!r}."
        )
    else:
        head = f"Findings for: {prompt.strip()!r}."
    body = " ".join(evidence[:3])
    return f"{head} {body}".strip()


def _suggest_next_steps(
    prompt: str, files_used: list[str], observations: list[dict[str, Any]]
) -> list[str]:
    """Heuristic follow-up suggestions for read-only tasks."""
    if not files_used:
        return [
            "List the project directory to discover key files",
            "Read README.md and any manifest (package.json / pyproject.toml)",
        ]
    return [
        f"Inspect additional files referenced by {files_used[0]}",
        "Run a build or typecheck for full validation",
    ]
