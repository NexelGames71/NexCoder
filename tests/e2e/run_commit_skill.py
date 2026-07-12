"""Acceptance: --skill commit produces a conventional commit.

Usage: venv\\Scripts\\python.exe tests\\e2e\\run_commit_skill.py
Requires the local model server to be running.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def git(workdir, *args):
    return subprocess.run(["git", *args], cwd=workdir, capture_output=True, text=True)


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="nexcoder_commit_"))
    git(workdir, "init")
    git(workdir, "config", "user.email", "e2e@nexcoder.local")
    git(workdir, "config", "user.name", "NexCoder E2E")
    (workdir / "greet.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
    git(workdir, "add", "-A")
    git(workdir, "commit", "-m", "chore: seed")
    (workdir / "greet.py").write_text(
        "def greet(name='world'):\n    return f'hello {name}'\n", encoding="utf-8")
    print(f"Workdir: {workdir}")
    proc = subprocess.run(
        [sys.executable, "-m", "nexcoder.cli", "--engine", "v2", "--auto",
         "--project", str(workdir), "--skill", "commit",
         "Commit the current changes."],
        timeout=900)
    log = git(workdir, "log", "-1", "--pretty=%s").stdout.strip()
    count = git(workdir, "rev-list", "--count", "HEAD").stdout.strip()
    pattern = r"^(feat|fix|docs|refactor|test|chore)(\(.+\))?: .+"
    if proc.returncode != 0 or count != "2" or not re.match(pattern, log):
        print(f"FAIL: exit={proc.returncode}, commits={count}, message={log!r}")
        return 1
    print(f"PASS: commit message {log!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
