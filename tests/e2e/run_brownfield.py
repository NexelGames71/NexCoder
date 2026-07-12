"""Acceptance 2: seeded failing test -> agent fixes it until green.

Usage: venv\\Scripts\\python.exe tests\\e2e\\run_brownfield.py
Requires the local model server to be running.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "brownfield"
PROMPT = ("The test suite is failing. Run 'python -m pytest -q' to see the "
          "failure, find the bug, fix it with edit_file, and re-run the tests "
          "until they pass.")


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="nexcoder_brownfield_"))
    shutil.copytree(FIXTURE, workdir, dirs_exist_ok=True)
    print(f"Workdir: {workdir}")
    proc = subprocess.run(
        [sys.executable, "-m", "nexcoder.cli", "--engine", "v2", "--auto",
         "--project", str(workdir), PROMPT],
        timeout=1800)
    verify = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                            cwd=workdir, capture_output=True, text=True)
    if proc.returncode != 0 or verify.returncode != 0:
        print(f"FAIL: agent exit={proc.returncode}, pytest exit={verify.returncode}")
        print(verify.stdout[-2000:])
        return 1
    print("PASS: tests green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
