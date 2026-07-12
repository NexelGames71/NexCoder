"""Conservative planning for reviewable project file organization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any


STRUCTURE_INTENT = re.compile(
    r"\b(?:organize|reorganize|structure|restructure|move|relocate|rename|put|place)\b",
    re.IGNORECASE,
)
EXPLICIT_MOVE = re.compile(
    r"\b(?:move|relocate|rename)\s+[`'\"]?"
    r"(?P<source>[A-Za-z0-9_.()\-/\\]+\.[A-Za-z0-9]+)[`'\"]?\s+"
    r"(?:to|into|as)\s+[`'\"]?"
    r"(?P<destination>[A-Za-z0-9_.()\-/\\]+(?:\.[A-Za-z0-9]+)?)[`'\"]?",
    re.IGNORECASE,
)
NATURAL_MOVE = re.compile(
    r"\b(?:put|place)\s+(?P<source>.+?)\s+(?:to|into|in)\s+"
    r"(?P<destination>.+?)(?=$|[.!?;,])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FileMove:
    source: str
    destination: str


def is_structure_request(prompt: str) -> bool:
    return bool(STRUCTURE_INTENT.search(prompt or ""))


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip().strip("`'\".,;:").lstrip("./")


def _available_files(
    project_root: Path,
    pending_changes: list[dict[str, Any]],
) -> set[str]:
    files = {
        item.relative_to(project_root).as_posix()
        for item in project_root.rglob("*")
        if item.is_file()
    }
    for patch in pending_changes:
        path = _normalize(str(patch.get("file") or ""))
        action = patch.get("action")
        if path and action not in {"delete", "rmdir", "mkdir"}:
            files.add(path)
        source = _normalize(str(patch.get("source") or ""))
        if source:
            files.discard(source)
    return files


def _resolve_source(description: str, available_files: set[str]) -> str | None:
    value = _normalize(description)
    if value in available_files:
        return value

    words = re.sub(r"\b(?:the|a|an|file|document)\b", " ", value, flags=re.IGNORECASE)
    key = re.sub(r"\s+", " ", words).strip().lower()
    if not key:
        return None

    matches = []
    for candidate in available_files:
        path = Path(candidate)
        if key in {candidate.lower(), path.name.lower(), path.stem.lower()}:
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _folder_destination(description: str, source: str) -> str:
    value = re.sub(
        r"^(?:the|a|an)\s+|\s+(?:folder|directory)$",
        "",
        description.strip(),
        flags=re.IGNORECASE,
    )
    destination = _normalize(value)
    if destination and not Path(destination).suffix:
        destination = f"{destination.rstrip('/')}/{Path(source).name}"
    return destination


def _explicit_moves(prompt: str, available_files: set[str]) -> list[FileMove]:
    moves: list[FileMove] = []
    seen: set[tuple[str, str]] = set()
    for match in EXPLICIT_MOVE.finditer(prompt or ""):
        source = _normalize(match.group("source"))
        destination = _normalize(match.group("destination"))
        if not source or not destination or source == destination:
            continue
        pair = (source.lower(), destination.lower())
        if pair not in seen:
            seen.add(pair)
            moves.append(FileMove(source, destination))
    for match in NATURAL_MOVE.finditer(prompt or ""):
        source = _resolve_source(match.group("source"), available_files)
        if not source:
            continue
        destination = _folder_destination(match.group("destination"), source)
        if not destination or source == destination:
            continue
        pair = (source.lower(), destination.lower())
        if pair not in seen:
            seen.add(pair)
            moves.append(FileMove(source, destination))
    return moves


def _available_root_files(
    project_root: Path,
    pending_changes: list[dict[str, Any]],
) -> set[str]:
    files = {
        item.name
        for item in project_root.iterdir()
        if item.is_file()
    }
    for patch in pending_changes:
        path = _normalize(str(patch.get("file") or ""))
        if path and "/" not in path and patch.get("action") not in {"delete", "rmdir"}:
            files.add(path)
        source = _normalize(str(patch.get("source") or ""))
        if source and "/" not in source:
            files.discard(source)
    return files


def _conventional_destination(filename: str) -> str | None:
    lower = filename.lower()
    suffix = Path(lower).suffix
    if suffix in {".css", ".scss", ".sass", ".less"}:
        return f"assets/css/{filename}"
    if suffix in {".js", ".mjs", ".cjs"}:
        if lower.endswith(".config.js") or lower in {
            "vite.config.js", "next.config.js", "eslint.config.js", "webpack.config.js",
        }:
            return None
        return f"assets/js/{filename}"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg", ".ico"}:
        return f"assets/images/{filename}"
    if suffix in {".woff", ".woff2", ".ttf", ".otf", ".eot"}:
        return f"assets/fonts/{filename}"
    if suffix in {".mp3", ".wav", ".ogg", ".mp4", ".webm"}:
        return f"assets/media/{filename}"
    return None


def plan_file_moves(
    prompt: str,
    project_root: str | Path,
    pending_changes: list[dict[str, Any]] | None = None,
) -> list[FileMove]:
    """Return explicit moves or a conservative root-asset organization plan."""
    if not is_structure_request(prompt):
        return []
    root = Path(project_root).resolve()
    changes = pending_changes or []
    explicit = _explicit_moves(prompt, _available_files(root, changes))
    if explicit:
        return explicit
    # A targeted natural-language move that cannot be resolved safely must
    # not fall through to broad conventional organization. That would move
    # unrelated files and hide the ambiguity from the user.
    if NATURAL_MOVE.search(prompt or ""):
        return []

    moves: list[FileMove] = []
    for filename in sorted(_available_root_files(root, changes), key=str.lower):
        destination = _conventional_destination(filename)
        if destination:
            moves.append(FileMove(filename, destination))
    return moves
