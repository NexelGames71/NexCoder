"""Acceptance 1: empty folder -> complete product page, unattended.

Usage: venv\\Scripts\\python.exe tests\\e2e\\run_greenfield.py
Requires the local model server (models/start_api.bat) to be running.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

PROMPT = ("Build a responsive product page: index.html, styles.css, script.js. "
          "Dark theme, three product cards, working theme toggle. "
          "Plan with todo_write first, verify the files exist when done.")


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="nexcoder_greenfield_"))
    print(f"Workdir: {workdir}")
    proc = subprocess.run(
        [sys.executable, "-m", "nexcoder.cli", "--engine", "v2", "--auto",
         "--project", str(workdir), PROMPT],
        timeout=1800)
    expected = ["index.html", "styles.css", "script.js"]
    missing = [name for name in expected if not (workdir / name).is_file()]
    if proc.returncode != 0 or missing:
        print(f"FAIL: exit={proc.returncode}, missing={missing}")
        return 1
    print("PASS: all files created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
