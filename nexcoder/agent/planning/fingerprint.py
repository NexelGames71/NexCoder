"""Stable, inexpensive project fingerprints for approval freshness checks."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess

_IGNORED = {".git", ".nexcoder", "node_modules", "dist", "build",
            "coverage", "vendor", ".cache", "venv", "__pycache__"}


def _git_value(root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, text=True,
            timeout=5, check=False)
        return completed.stdout.strip() if completed.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def project_fingerprint(project_root: str | Path,
                        relevant_files: list[str] | None = None) -> str:
    root = Path(project_root).resolve()
    digest = hashlib.sha256()
    digest.update(_git_value(root, "rev-parse", "HEAD").encode())
    digest.update(_git_value(root, "status", "--porcelain=v1", "--untracked-files=normal").encode())

    candidates: list[Path] = []
    if relevant_files:
        for value in relevant_files:
            target = (root / value).resolve()
            try:
                if os.path.commonpath([str(root), str(target)]) == str(root):
                    candidates.append(target)
            except ValueError:
                continue
    else:
        for name in ("pyproject.toml", "package.json", "package-lock.json",
                     "requirements.txt", "Cargo.toml", "go.mod"):
            candidates.append(root / name)

    for path in sorted(set(candidates), key=lambda item: str(item).lower()):
        if any(part in _IGNORED for part in path.parts):
            continue
        relative = os.path.relpath(path, root).replace("\\", "/")
        digest.update(relative.encode("utf-8", errors="replace"))
        if not path.is_file():
            digest.update(b"<missing>")
            continue
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
    return digest.hexdigest()
