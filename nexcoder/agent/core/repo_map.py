"""Repo map: lightweight file + symbol index injected into agent prompts."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from nexcoder.agent.core.walk import iter_project_files

MAX_FILES = 800
MAX_SYMBOLS = 20
SOURCE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".java", ".kt", ".kts", ".go", ".rs", ".cs", ".cpp", ".cc",
    ".c", ".h", ".hpp", ".rb", ".php", ".swift", ".vue", ".svelte",
}
JS_SYMBOL_PATTERN = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?"
    r"(?:(class)\s+([A-Za-z_$][\w$]*)|(?:async\s+)?(function)\s+([A-Za-z_$][\w$]*))",
    re.MULTILINE)


def _python_symbols(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    symbols: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            symbols.append(f"class {node.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(f"def {node.name}")
    return symbols[:MAX_SYMBOLS]


def _js_symbols(text: str) -> list[str]:
    symbols: list[str] = []
    for match in JS_SYMBOL_PATTERN.finditer(text):
        if match.group(1):
            symbols.append(f"class {match.group(2)}")
        elif match.group(3):
            symbols.append(f"function {match.group(4)}")
        if len(symbols) >= MAX_SYMBOLS:
            break
    return symbols


def build_repo_map(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    files: list[dict[str, Any]] = []
    for path in iter_project_files(root):
        if len(files) >= MAX_FILES:
            break
        if path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        symbols = (_python_symbols(text) if path.suffix.lower() == ".py"
                   else _js_symbols(text))
        files.append({"path": path.relative_to(root).as_posix(), "symbols": symbols})
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "files": files}


def save_repo_map(project_root: str | Path, repo_map: dict[str, Any]) -> Path:
    folder = Path(project_root) / ".nexcoder"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "repo_map.json"
    path.write_text(json.dumps(repo_map, indent=2), encoding="utf-8")
    return path


def load_repo_map(project_root: str | Path) -> dict[str, Any] | None:
    path = Path(project_root) / ".nexcoder" / "repo_map.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def render_repo_map(repo_map: dict[str, Any], token_budget: int = 1500) -> str:
    lines = ["# Project map"]
    for item in repo_map.get("files", []):
        symbols = ", ".join(item.get("symbols") or [])
        lines.append(f"{item['path']}" + (f" — {symbols}" if symbols else ""))
    text = "\n".join(lines)
    char_budget = token_budget * 3
    if len(text) > char_budget:
        text = text[:char_budget] + "\n[map truncated]"
    return text
