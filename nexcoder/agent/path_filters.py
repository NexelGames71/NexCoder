"""Shared path filters for project scans and agent tools."""

from __future__ import annotations

import re


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".nexcoder",
    ".claude",
    ".codex",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    "coverage",
    "htmlcov",
    ".turbo",
    ".cache",
}

GENERATED_DIR_PATTERNS = (
    re.compile(r"^dist[_-]\d{8}(?:[_-]\d{6})?$", re.IGNORECASE),
    re.compile(r"^build[_-]\d{8}(?:[_-]\d{6})?$", re.IGNORECASE),
)


def is_generated_dir(name: str) -> bool:
    """Return True when a directory name is generated build output."""
    return name in SKIP_DIRS or any(pattern.match(name) for pattern in GENERATED_DIR_PATTERNS)


def should_skip_dir(name: str, *, skip_hidden: bool = True) -> bool:
    """Return True when a directory should be ignored by scans/searches."""
    if skip_hidden and name.startswith("."):
        return True
    return is_generated_dir(name)


def has_skipped_part(parts: tuple[str, ...]) -> bool:
    """Return True when any relative path segment should be ignored."""
    return any(should_skip_dir(part, skip_hidden=False) for part in parts)
