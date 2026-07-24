"""Detect the project's own build/test/lint commands from its config.

The validation loop is only as good as the commands it runs. Rather
than letting the model guess (`npm test` in a pytest repo), we read the
project's configuration and hand the model the real commands.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Script names worth surfacing from package.json, in display order.
_INTERESTING_SCRIPTS = ("build", "test", "lint", "typecheck", "check",
                        "format", "dev", "start")

MAX_MAKE_TARGETS = 8


def detect_project_commands(project_root: str | Path) -> list[tuple[str, str]]:
    """Return ``(label, command)`` pairs detected from project config.

    User overrides (settings → env) always come first: when the user
    told us the build/test/lint command, that beats detection.
    """
    import os
    root = Path(project_root)
    commands: list[tuple[str, str]] = []
    for label, env in (("build", "NEXCODER_CMD_BUILD"),
                       ("test", "NEXCODER_CMD_TEST"),
                       ("lint", "NEXCODER_CMD_LINT")):
        override = os.getenv(env, "").strip()
        if override:
            commands.append((label, override))

    package_json = root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = data.get("scripts") or {}
            for name in _INTERESTING_SCRIPTS:
                if name in scripts:
                    commands.append((f"npm {name}", f"npm run {name}"))
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            text = pyproject.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if "[tool.pytest" in text or (root / "tests").is_dir():
            commands.append(("python tests", "python -m pytest tests -q"))
        if "[tool.ruff" in text:
            commands.append(("lint", "python -m ruff check ."))
        if "[tool.mypy" in text:
            commands.append(("typecheck", "python -m mypy ."))
    elif (root / "pytest.ini").is_file() or (root / "tests").is_dir():
        if any((root / n).is_file()
               for n in ("requirements.txt", "setup.py", "setup.cfg",
                         "pytest.ini")):
            commands.append(("python tests", "python -m pytest tests -q"))

    if (root / "Cargo.toml").is_file():
        commands.append(("rust build", "cargo build"))
        commands.append(("rust tests", "cargo test"))

    if (root / "go.mod").is_file():
        commands.append(("go build", "go build ./..."))
        commands.append(("go tests", "go test ./..."))

    makefile = root / "Makefile"
    if makefile.is_file():
        try:
            text = makefile.read_text(encoding="utf-8", errors="replace")
            targets = re.findall(r"^([A-Za-z0-9_.-]+):", text, re.MULTILINE)
            seen: set[str] = set()
            for target in targets:
                if target in seen or target.startswith("."):
                    continue
                seen.add(target)
                commands.append((f"make {target}", f"make {target}"))
                if len(seen) >= MAX_MAKE_TARGETS:
                    break
        except OSError:
            pass

    # De-duplicate by command, first label wins.
    unique: list[tuple[str, str]] = []
    seen_cmds: set[str] = set()
    for label, cmd in commands:
        if cmd not in seen_cmds:
            seen_cmds.add(cmd)
            unique.append((label, cmd))
    return unique


def render_project_commands(commands: list[tuple[str, str]]) -> str:
    """Render for the system prompt, or "" when nothing was detected."""
    if not commands:
        return ""
    lines = [f"- {label}: `{cmd}`" for label, cmd in commands]
    return ("# Known project commands (detected from project config — "
            "use these to verify your work instead of guessing)\n"
            + "\n".join(lines))
