"""GitHandler — Git operations using GitPython."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GitHandler:
    """Handles git operations for the IPC bridge."""

    def status(self, root: str) -> dict[str, Any]:
        """Get git status: changed, staged, untracked files."""
        try:
            from git import Repo, InvalidGitRepositoryError
        except ImportError:
            return {"error": "GitPython not installed", "isRepo": False}

        try:
            repo = Repo(root)
        except InvalidGitRepositoryError:
            return {"isRepo": False, "changed": [], "staged": [], "untracked": []}

        changed = []
        staged = []
        untracked = list(repo.untracked_files)

        # Staged (index vs HEAD)
        if repo.head.is_valid():
            for diff in repo.index.diff(repo.head.commit):
                staged.append({
                    "path": diff.a_path or diff.b_path,
                    "change_type": diff.change_type,
                })

        # Unstaged (working tree vs index)
        for diff in repo.index.diff(None):
            changed.append({
                "path": diff.a_path or diff.b_path,
                "change_type": diff.change_type,
            })

        return {
            "isRepo": True,
            "branch": self.branch(root),
            "changed": changed,
            "staged": staged,
            "untracked": untracked,
            "isDirty": repo.is_dirty(untracked_files=True),
        }

    def diff(self, root: str, staged: bool = False) -> str:
        """Get unified diff output."""
        try:
            from git import Repo, InvalidGitRepositoryError

            repo = Repo(root)
            if staged:
                if repo.head.is_valid():
                    return repo.git.diff("--staged")
                return ""
            return repo.git.diff()
        except Exception as e:
            logger.error(f"Git diff error: {e}")
            return ""

    def stage(self, root: str, files: list[str]) -> None:
        """Stage files (git add)."""
        from git import Repo

        repo = Repo(root)
        repo.index.add(files)

    def unstage(self, root: str, files: list[str]) -> None:
        """Unstage files (git reset)."""
        from git import Repo

        repo = Repo(root)
        if repo.head.is_valid():
            repo.index.reset(repo.head.commit, paths=files)

    def commit(self, root: str, message: str) -> str:
        """Create a git commit. Returns the commit hash."""
        from git import Repo

        repo = Repo(root)
        commit = repo.index.commit(message)
        return str(commit.hexsha)

    def branch(self, root: str) -> str:
        """Get the current branch name."""
        try:
            from git import Repo, InvalidGitRepositoryError

            repo = Repo(root)
            if repo.head.is_detached:
                return f"HEAD ({str(repo.head.commit)[:7]})"
            return str(repo.active_branch)
        except Exception:
            return ""

    def branches(self, root: str) -> list[str]:
        """Get all local branch names."""
        try:
            from git import Repo

            repo = Repo(root)
            return [str(b) for b in repo.branches]
        except Exception:
            return []

    def log(self, root: str, count: int = 20) -> list[dict[str, Any]]:
        """Get recent commits."""
        try:
            from git import Repo

            repo = Repo(root)
            if not repo.head.is_valid():
                return []

            commits = []
            for commit in repo.iter_commits(max_count=count):
                commits.append({
                    "hash": str(commit.hexsha),
                    "short_hash": str(commit.hexsha)[:7],
                    "message": commit.message.strip(),
                    "author": str(commit.author),
                    "date": commit.committed_datetime.isoformat(),
                    "files_changed": len(commit.stats.files),
                })
            return commits
        except Exception as e:
            logger.error(f"Git log error: {e}")
            return []

    def init(self, root: str) -> None:
        """Initialize a git repository."""
        from git import Repo

        Repo.init(root)
