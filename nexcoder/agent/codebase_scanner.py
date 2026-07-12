"""Deterministic codebase scanner for NexCoder Agent scan tasks."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from nexcoder.agent.path_filters import should_skip_dir

TEXT_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".txt",
    ".css",
    ".html",
    ".rs",
    ".go",
}

CONFIG_FILES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Gemfile",
    "composer.json",
    "pubspec.yaml",
    "CMakeLists.txt",
    "Makefile",
}

PACKAGE_MANAGERS = {
    "package-lock.json": "npm",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "bun.lockb": "bun",
    "Pipfile.lock": "pipenv",
    "poetry.lock": "poetry",
    "uv.lock": "uv",
    "Cargo.lock": "cargo",
    "go.sum": "go",
}

SOURCE_DIR_NAMES = {"src", "app", "lib", "nexcoder", "server", "client", "frontend", "backend"}
TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs"}
README_NAMES = {"README", "README.md", "readme.md"}
SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".rs", ".go"}


class CodebaseScanner:
    """Scans a project locally without involving the chat model."""

    def run(
        self,
        project_root: str,
        on_status: Callable[[str, str], None] | None = None,
    ) -> dict[str, Any]:
        root = Path(project_root).resolve()
        if not root.is_dir():
            raise NotADirectoryError(f"Not a directory: {root}")

        status = on_status or (lambda _status, _message: None)

        status("running", "Listing project tree")
        all_files = self._list_project_files(root)
        status("complete", f"Listed {len(all_files)} project file(s)")

        status("running", "Indexing readable files")
        readable_files = [path for path in all_files if path.suffix.lower() in TEXT_EXTENSIONS]
        status("complete", f"Indexed {len(readable_files)} readable file(s)")

        config_files = [path for path in all_files if path.name in CONFIG_FILES]
        readme_files = [path for path in all_files if path.name in README_NAMES]
        important_files = self._important_files(root, all_files, config_files, readme_files)

        for path in important_files:
            rel_path = path.relative_to(root).as_posix()
            status("running", f"Reading {rel_path}...")
            self._safe_read_preview(path)
            status("complete", f"Read {rel_path}")

        status("running", "Detecting project type")
        detected = self._detect_project(root, all_files, config_files, readme_files)
        status("complete", "Detected project type")

        status("running", "Checking project warnings")
        warnings = self._build_warnings(detected, readable_files)
        status("complete", "Checked project warnings")

        status("running", "Summarizing project")
        overview = self._build_overview(root, all_files, important_files, detected, warnings)
        status("complete", "Summarized project")

        project_map = {
            "root": root.as_posix(),
            "files_scanned": len(readable_files),
            "detected": detected,
            "important_files": [path.relative_to(root).as_posix() for path in important_files],
            "warnings": warnings,
            "overview": overview,
        }

        status("running", "Saving project map")
        self._save_project_map(root, project_map)

        status("complete", "Created project map")
        return {
            "success": True,
            "response": self._format_report(project_map),
            "project_map": project_map,
            "mode": "scan",
        }

    def _list_project_files(self, root: Path) -> list[Path]:
        files: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                name for name in dirnames
                if not should_skip_dir(name)
            ]
            for filename in filenames:
                files.append(Path(dirpath) / filename)
        return sorted(files, key=lambda path: path.relative_to(root).as_posix().lower())

    def _important_files(
        self,
        root: Path,
        all_files: list[Path],
        config_files: list[Path],
        readme_files: list[Path],
    ) -> list[Path]:
        important = list(config_files) + list(readme_files)
        entry_names = {
            "index.html",
            "main.py",
            "app.py",
            "server.py",
            "index.js",
            "index.ts",
            "main.js",
            "main.ts",
            "main.tsx",
            "script.js",
            "styles.css",
        }
        entry_files = [
            path for path in all_files
            if path.name in entry_names or path.relative_to(root).as_posix() in entry_names
        ]
        important.extend(entry_files[:8])
        docs = [path for path in all_files if "docs" in path.relative_to(root).parts and path.suffix.lower() == ".md"]
        important.extend(docs[:8])

        if not important:
            important = [path for path in all_files if path.suffix.lower() in TEXT_EXTENSIONS][:8]

        deduped: list[Path] = []
        seen: set[Path] = set()
        for path in important:
            if path not in seen:
                seen.add(path)
                deduped.append(path)
        return deduped

    def _detect_project(
        self,
        root: Path,
        all_files: list[Path],
        config_files: list[Path],
        readme_files: list[Path],
    ) -> dict[str, Any]:
        names = {path.name for path in all_files}
        language = "Unknown"
        framework = "Not detected"

        if "package.json" in names:
            language = "JavaScript/TypeScript"
            framework = self._detect_node_framework(root / "package.json")
        elif "pyproject.toml" in names or "requirements.txt" in names or "setup.py" in names:
            language = "Python"
            framework = "Python"
        elif "Cargo.toml" in names:
            language = "Rust"
            framework = "Rust"
        elif "go.mod" in names:
            language = "Go"
            framework = "Go"
        else:
            extensions = {path.suffix.lower() for path in all_files}
            if ".html" in extensions:
                web_languages = [
                    label for extension, label in (
                        (".html", "HTML"),
                        (".css", "CSS"),
                        (".js", "JavaScript"),
                        (".ts", "TypeScript"),
                    )
                    if extension in extensions
                ]
                language = "/".join(web_languages)
                framework = "Static site"

        package_manager = "Not detected"
        for filename, manager in PACKAGE_MANAGERS.items():
            if filename in names:
                package_manager = manager
                break

        source_dir = self._find_first_dir(root, SOURCE_DIR_NAMES)
        if not source_dir and framework == "Static site":
            source_dir = "."
        tests = self._find_first_dir(root, TEST_DIR_NAMES)
        entry_points = self._detect_entry_points(root, all_files)

        return {
            "language": language,
            "framework": framework,
            "package_manager": package_manager,
            "source_directory": source_dir or "Not found",
            "tests": tests or "Not found",
            "documentation": "Found" if readme_files or any("docs" in path.parts for path in all_files) else "Not found",
            "entry_points": entry_points or [],
            "config_files": [path.relative_to(root).as_posix() for path in config_files],
        }

    def _detect_node_framework(self, package_json: Path) -> str:
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            return "Node.js"

        deps = {
            **data.get("dependencies", {}),
            **data.get("devDependencies", {}),
        }
        for package_name, framework in (
            ("next", "Next.js"),
            ("vite", "Vite"),
            ("react", "React"),
            ("vue", "Vue"),
            ("svelte", "Svelte"),
            ("electron", "Electron"),
        ):
            if package_name in deps:
                return framework
        return "Node.js"

    def _find_first_dir(self, root: Path, names: set[str]) -> str | None:
        for child in root.iterdir():
            if child.is_dir() and child.name in names:
                return child.name
        return None

    def _detect_entry_points(self, root: Path, all_files: list[Path]) -> list[str]:
        candidates = {
            "main.py",
            "app.py",
            "server.py",
            "index.js",
            "index.ts",
            "index.html",
            "main.js",
            "script.js",
            "main.tsx",
            "main.ts",
            "src/main.tsx",
            "src/App.tsx",
            "nexcoder/main.py",
        }
        found: list[str] = []
        for path in all_files:
            rel = path.relative_to(root).as_posix()
            if rel in candidates or path.name in candidates:
                found.append(rel)
        return found[:8]

    def _build_warnings(self, detected: dict[str, Any], readable_files: list[Path]) -> list[str]:
        warnings: list[str] = []
        has_source_files = any(path.suffix.lower() in SOURCE_EXTENSIONS for path in readable_files)
        if (
            detected["framework"] == "Not detected"
            and detected["package_manager"] == "Not detected"
            and detected["source_directory"] == "Not found"
            and detected["tests"] == "Not found"
            and not has_source_files
        ):
            warnings.append(
                "This does not look like a full source-code project yet. "
                "It currently appears to contain documentation files only."
            )
        elif not readable_files:
            warnings.append("No readable source or documentation files were detected.")
        return warnings

    def _build_overview(
        self,
        root: Path,
        all_files: list[Path],
        important_files: list[Path],
        detected: dict[str, Any],
        warnings: list[str],
    ) -> dict[str, Any]:
        package_info = self._read_package_info(root / "nexcoder" / "ui" / "package.json")
        root_package_info = self._read_package_info(root / "package.json")
        pyproject_info = self._read_pyproject_info(root / "pyproject.toml")
        readme_about = self._read_readme_about(root)

        name = (
            pyproject_info.get("name")
            or package_info.get("name")
            or root_package_info.get("name")
            or root.name
        )
        description = (
            pyproject_info.get("description")
            or package_info.get("description")
            or root_package_info.get("description")
            or readme_about
            or "No project description was found in README.md, package.json, or pyproject.toml."
        )

        stack = [
            value for value in (
                detected.get("language"),
                detected.get("framework"),
                f"{detected.get('package_manager')} package manager"
                if detected.get("package_manager") not in {None, "", "Not detected"} else None,
            )
            if value and value != "Not detected"
        ]

        notes = self._build_notes(root, all_files, detected, warnings)
        return {
            "name": name,
            "description": description,
            "stack": stack,
            "notes": notes,
            "key_files": [path.relative_to(root).as_posix() for path in important_files[:8]],
        }

    def _read_package_info(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return {
            "name": str(data.get("name") or "").strip(),
            "description": str(data.get("description") or "").strip(),
        }

    def _read_pyproject_info(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return {}

        info: dict[str, str] = {}
        for key in ("name", "description"):
            value = self._extract_toml_string(text, key)
            if value:
                info[key] = value
        return info

    def _extract_toml_string(self, text: str, key: str) -> str:
        prefix = f"{key} ="
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(prefix):
                continue
            raw = stripped.removeprefix(prefix).strip()
            if len(raw) >= 2 and raw[0] in {"\"", "'"} and raw[-1] == raw[0]:
                return raw[1:-1].strip()
            return raw.strip()
        return ""

    def _read_readme_about(self, root: Path) -> str:
        for name in README_NAMES:
            path = root / name
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            paragraph = self._first_meaningful_markdown_paragraph(text)
            if paragraph:
                return paragraph
        return ""

    def _first_meaningful_markdown_paragraph(self, text: str) -> str:
        lines: list[str] = []
        in_code = False
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("```"):
                in_code = not in_code
                continue
            if in_code or not line:
                if lines:
                    break
                continue
            if line.startswith("#"):
                continue
            lines.append(line)
        return " ".join(lines)[:500]

    def _build_notes(
        self,
        root: Path,
        all_files: list[Path],
        detected: dict[str, Any],
        warnings: list[str],
    ) -> list[str]:
        notes: list[str] = []
        if detected.get("entry_points"):
            notes.append(f"Main entry points: {', '.join(detected['entry_points'][:5])}")
        if detected.get("source_directory") != "Not found":
            notes.append(f"Primary source directory appears to be `{detected['source_directory']}`.")
        if detected.get("tests") != "Not found":
            notes.append(f"Tests are present under `{detected['tests']}`.")
        else:
            notes.append("No test directory was detected.")
        if any((root / name).exists() for name in ("build.py", "nexcoder.spec")):
            notes.append("This project includes a PyInstaller packaging path for the desktop app.")
        if (root / "models" / "server.py").exists():
            notes.append("A local OpenAI-compatible model server is included under `models/server.py`.")
        if warnings:
            notes.extend(warnings)
        return notes

    def _safe_read_preview(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:2000]
        except Exception:
            return ""

    def _save_project_map(self, root: Path, project_map: dict[str, Any]) -> None:
        nexcoder_dir = root / ".nexcoder"
        nexcoder_dir.mkdir(exist_ok=True)
        (nexcoder_dir / "project_map.json").write_text(
            json.dumps(project_map, indent=2),
            encoding="utf-8",
        )

    def _format_report(self, project_map: dict[str, Any]) -> str:
        detected = project_map["detected"]
        lines = [
            "Project Scan Complete",
            "",
            "Root:",
            project_map["root"],
            "",
            "Files scanned:",
            str(project_map["files_scanned"]),
            "",
            "Detected:",
            f"- Language: {detected['language']}",
            f"- Framework: {detected['framework']}",
            f"- Package manager: {detected['package_manager']}",
            f"- Source directory: {detected['source_directory']}",
            f"- Tests: {detected['tests']}",
            f"- Documentation: {detected['documentation']}",
        ]

        if detected.get("entry_points"):
            lines.append(f"- Entry points: {', '.join(detected['entry_points'])}")

        lines.extend(["", "Important files:"])
        if project_map["important_files"]:
            lines.extend(f"- {path}" for path in project_map["important_files"])
        else:
            lines.append("- None found")

        if project_map["warnings"]:
            lines.extend(["", "Warning:"])
            lines.extend(project_map["warnings"])

        return "\n".join(lines)
