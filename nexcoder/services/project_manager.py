"""ProjectManager — project detection, recent projects, and configuration."""

import os
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Framework detection files
FRAMEWORK_SIGNATURES: dict[str, dict[str, str]] = {
    "package.json": {"framework": "Node.js", "language": "JavaScript/TypeScript"},
    "pyproject.toml": {"framework": "Python", "language": "Python"},
    "setup.py": {"framework": "Python", "language": "Python"},
    "Cargo.toml": {"framework": "Rust", "language": "Rust"},
    "go.mod": {"framework": "Go", "language": "Go"},
    "pom.xml": {"framework": "Maven", "language": "Java"},
    "build.gradle": {"framework": "Gradle", "language": "Java/Kotlin"},
    "build.gradle.kts": {"framework": "Gradle (Kotlin)", "language": "Kotlin"},
    "Gemfile": {"framework": "Ruby", "language": "Ruby"},
    "composer.json": {"framework": "PHP", "language": "PHP"},
    "pubspec.yaml": {"framework": "Flutter/Dart", "language": "Dart"},
    "CMakeLists.txt": {"framework": "CMake", "language": "C/C++"},
    "Makefile": {"framework": "Make", "language": "C/C++"},
}

# Package manager detection
PACKAGE_MANAGERS: dict[str, str] = {
    "package-lock.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
    "bun.lockb": "bun",
    "Pipfile.lock": "pipenv",
    "poetry.lock": "poetry",
    "uv.lock": "uv",
    "Cargo.lock": "cargo",
    "go.sum": "go",
}

# Config directory
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".nexcoder")
RECENT_PROJECTS_FILE = os.path.join(CONFIG_DIR, "recent_projects.json")
MAX_RECENT = 20


class ProjectManager:
    """Manages project detection, configuration, and recent projects."""

    def __init__(self) -> None:
        os.makedirs(CONFIG_DIR, exist_ok=True)

    def open_project(self, path: str) -> dict[str, Any]:
        """Open a project directory and detect its type.

        Returns project info dict.
        """
        abs_path = os.path.abspath(path)
        if not os.path.isdir(abs_path):
            raise NotADirectoryError(f"Not a directory: {abs_path}")

        info: dict[str, Any] = {
            "path": abs_path.replace("\\", "/"),
            "name": os.path.basename(abs_path),
            "framework": "Unknown",
            "language": "Unknown",
            "packageManager": None,
            "buildCommand": None,
            "hasGit": os.path.isdir(os.path.join(abs_path, ".git")),
        }

        # Detect framework
        for filename, meta in FRAMEWORK_SIGNATURES.items():
            if os.path.isfile(os.path.join(abs_path, filename)):
                info["framework"] = meta["framework"]
                info["language"] = meta["language"]
                break

        # Detect package manager
        for lockfile, pm in PACKAGE_MANAGERS.items():
            if os.path.isfile(os.path.join(abs_path, lockfile)):
                info["packageManager"] = pm
                break

        # Detect build command
        info["buildCommand"] = self._detect_build_command(abs_path, info)

        # Create .nexcoder directory for project config
        nexcoder_dir = os.path.join(abs_path, ".nexcoder")
        os.makedirs(nexcoder_dir, exist_ok=True)

        # Update recent projects
        self._add_recent(info)

        logger.info(f"Opened project: {info['name']} ({info['framework']})")
        return info

    def _detect_build_command(self, path: str, info: dict[str, Any]) -> str | None:
        """Detect the appropriate build/run command for the project."""
        pm = info.get("packageManager", "npm")

        # Check for package.json scripts
        pkg_json = os.path.join(path, "package.json")
        if os.path.isfile(pkg_json):
            try:
                with open(pkg_json, "r") as f:
                    pkg = json.load(f)
                scripts = pkg.get("scripts", {})
                if "dev" in scripts:
                    return f"{pm} run dev"
                if "start" in scripts:
                    return f"{pm} start"
                if "build" in scripts:
                    return f"{pm} run build"
            except Exception:
                pass

        # Python projects
        if info.get("framework") == "Python":
            if os.path.isfile(os.path.join(path, "manage.py")):
                return "python manage.py runserver"
            return "python -m main"

        # Rust
        if info.get("framework") == "Rust":
            return "cargo run"

        # Go
        if info.get("framework") == "Go":
            return "go run ."

        return None

    # ── Recent Projects ───────────────────────────────────────────────

    def get_recent_projects(self) -> list[dict[str, Any]]:
        """Get the list of recent projects."""
        if not os.path.isfile(RECENT_PROJECTS_FILE):
            return []

        try:
            with open(RECENT_PROJECTS_FILE, "r") as f:
                projects = json.load(f)
            # Filter out non-existent directories
            return [p for p in projects if os.path.isdir(p.get("path", ""))]
        except Exception:
            return []

    def _add_recent(self, project_info: dict[str, Any]) -> None:
        """Add a project to the recent list."""
        projects = self.get_recent_projects()

        # Remove if already exists
        projects = [p for p in projects if p.get("path") != project_info["path"]]

        # Add to front
        projects.insert(0, {
            "path": project_info["path"],
            "name": project_info["name"],
            "framework": project_info["framework"],
            "language": project_info["language"],
        })

        # Trim to max
        projects = projects[:MAX_RECENT]

        try:
            with open(RECENT_PROJECTS_FILE, "w") as f:
                json.dump(projects, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save recent projects: {e}")

    def remove_recent(self, path: str) -> None:
        """Remove a project from the recent list."""
        projects = self.get_recent_projects()
        projects = [p for p in projects if p.get("path") != path]

        try:
            with open(RECENT_PROJECTS_FILE, "w") as f:
                json.dump(projects, f, indent=2)
        except Exception:
            pass
