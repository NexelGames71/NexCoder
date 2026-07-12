"""ErrorParser — parses terminal error output across multiple languages."""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)


# Error patterns for different languages / tools
ERROR_PATTERNS: list[dict[str, Any]] = [
    # Python traceback
    {
        "name": "python_traceback",
        "pattern": re.compile(
            r'File "([^"]+)", line (\d+)(?:, in (\w+))?\n\s+(.+)\n(\w+(?:Error|Exception|Warning)): (.+)',
            re.MULTILINE,
        ),
        "extractor": lambda m: {
            "file": m.group(1),
            "line": int(m.group(2)),
            "function": m.group(3) or "",
            "code": m.group(4).strip(),
            "error_type": m.group(5),
            "message": m.group(6).strip(),
            "language": "python",
        },
    },
    # Python simple error (last line)
    {
        "name": "python_error",
        "pattern": re.compile(
            r'^(\w+(?:Error|Exception)): (.+)$',
            re.MULTILINE,
        ),
        "extractor": lambda m: {
            "error_type": m.group(1),
            "message": m.group(2).strip(),
            "language": "python",
        },
    },
    # TypeScript / JavaScript
    {
        "name": "typescript_error",
        "pattern": re.compile(
            r'([^\s]+\.(?:ts|tsx|js|jsx)):(\d+):(\d+)\s*[-–]\s*(?:error\s+)?(TS\d+):\s*(.+)',
            re.MULTILINE,
        ),
        "extractor": lambda m: {
            "file": m.group(1),
            "line": int(m.group(2)),
            "column": int(m.group(3)),
            "error_code": m.group(4),
            "message": m.group(5).strip(),
            "language": "typescript",
        },
    },
    # ESLint
    {
        "name": "eslint_error",
        "pattern": re.compile(
            r'([^\s]+\.(?:ts|tsx|js|jsx))\n\s+(\d+):(\d+)\s+(error|warning)\s+(.+?)\s+(\S+)$',
            re.MULTILINE,
        ),
        "extractor": lambda m: {
            "file": m.group(1),
            "line": int(m.group(2)),
            "column": int(m.group(3)),
            "severity": m.group(4),
            "message": m.group(5).strip(),
            "rule": m.group(6),
            "language": "eslint",
        },
    },
    # Rust compiler
    {
        "name": "rust_error",
        "pattern": re.compile(
            r'error\[E(\d+)\]: (.+)\n\s*--> ([^:]+):(\d+):(\d+)',
            re.MULTILINE,
        ),
        "extractor": lambda m: {
            "error_code": f"E{m.group(1)}",
            "message": m.group(2).strip(),
            "file": m.group(3),
            "line": int(m.group(4)),
            "column": int(m.group(5)),
            "language": "rust",
        },
    },
    # Go compiler
    {
        "name": "go_error",
        "pattern": re.compile(
            r'([^\s]+\.go):(\d+):(\d+):\s*(.+)',
            re.MULTILINE,
        ),
        "extractor": lambda m: {
            "file": m.group(1),
            "line": int(m.group(2)),
            "column": int(m.group(3)),
            "message": m.group(4).strip(),
            "language": "go",
        },
    },
    # Java / Kotlin
    {
        "name": "java_error",
        "pattern": re.compile(
            r'([^\s]+\.(?:java|kt)):(\d+):\s*(error|warning):\s*(.+)',
            re.MULTILINE,
        ),
        "extractor": lambda m: {
            "file": m.group(1),
            "line": int(m.group(2)),
            "severity": m.group(3),
            "message": m.group(4).strip(),
            "language": "java",
        },
    },
    # C / C++ (gcc / clang)
    {
        "name": "cpp_error",
        "pattern": re.compile(
            r'([^\s]+\.(?:c|cpp|cc|h|hpp)):(\d+):(\d+):\s*(error|warning|note):\s*(.+)',
            re.MULTILINE,
        ),
        "extractor": lambda m: {
            "file": m.group(1),
            "line": int(m.group(2)),
            "column": int(m.group(3)),
            "severity": m.group(4),
            "message": m.group(5).strip(),
            "language": "cpp",
        },
    },
    # npm / node errors
    {
        "name": "npm_error",
        "pattern": re.compile(
            r'npm (?:ERR!|error)\s+(.+)',
            re.MULTILINE,
        ),
        "extractor": lambda m: {
            "message": m.group(1).strip(),
            "language": "npm",
        },
    },
]


class ErrorParser:
    """Parses terminal error output into structured error objects."""

    def parse(self, output: str) -> list[dict[str, Any]]:
        """Parse terminal output for errors. Returns list of error objects."""
        errors: list[dict[str, Any]] = []

        for pattern_def in ERROR_PATTERNS:
            for match in pattern_def["pattern"].finditer(output):
                try:
                    error = pattern_def["extractor"](match)
                    error["parser"] = pattern_def["name"]
                    errors.append(error)
                except Exception as e:
                    logger.debug(f"Error parsing match with {pattern_def['name']}: {e}")

        return errors

    def get_fix_suggestions(self, error: dict[str, Any]) -> list[str]:
        """Generate fix suggestions based on error type."""
        suggestions: list[str] = []
        error_type = error.get("error_type", "")
        message = error.get("message", "").lower()
        language = error.get("language", "")

        # Python-specific suggestions
        if language == "python":
            if error_type == "ModuleNotFoundError":
                module = message.replace("no module named ", "").strip("'\"")
                suggestions.append(f"Install the missing module: pip install {module}")
            elif error_type == "ImportError":
                suggestions.append("Check import path and installed packages")
            elif error_type == "SyntaxError":
                suggestions.append("Check for missing colons, brackets, or indentation")
            elif error_type == "IndentationError":
                suggestions.append("Fix indentation (use consistent spaces/tabs)")
            elif error_type == "TypeError":
                suggestions.append("Check argument types and function signatures")
            elif error_type == "NameError":
                suggestions.append("Variable or function is not defined — check spelling and scope")
            elif error_type == "AttributeError":
                suggestions.append("Check if the object has the referenced attribute/method")
            elif error_type == "KeyError":
                suggestions.append("Key not found in dictionary — use .get() for safe access")

        # TypeScript suggestions
        elif language == "typescript":
            if "cannot find module" in message:
                suggestions.append("Install missing dependency with npm/yarn")
            elif "not assignable" in message:
                suggestions.append("Check type compatibility")
            elif "property" in message and "does not exist" in message:
                suggestions.append("Add the missing property to the type/interface")

        # Generic
        if not suggestions:
            suggestions.append("Review the error message and fix the code at the indicated location")

        return suggestions

    def format_for_ai(self, errors: list[dict[str, Any]]) -> str:
        """Format parsed errors as context for AI prompts."""
        if not errors:
            return ""

        parts = ["## Errors Found\n"]
        for i, error in enumerate(errors, 1):
            file_info = error.get("file", "unknown")
            line = error.get("line", "?")
            message = error.get("message", "Unknown error")
            error_type = error.get("error_type", error.get("severity", "error"))

            parts.append(f"{i}. **{error_type}** in `{file_info}:{line}`")
            parts.append(f"   {message}\n")

        return "\n".join(parts)
