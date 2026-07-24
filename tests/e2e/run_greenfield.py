"""Acceptance 1: empty folder -> complete product page, unattended.

Usage: venv\\Scripts\\python.exe tests\\e2e\\run_greenfield.py
Requires the local model server (models/start_api.bat) to be running.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

PROMPT = ("Build a responsive product page: index.html, styles.css, script.js. "
          "Include exactly three elements with class product-card and a theme "
          "button with id theme-toggle. The button must toggle the dark-theme "
          "class on document.body, and styles.css must style .dark-theme. "
          "Plan with todo_write first, then verify the behavior when done.")


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="nexcoder_greenfield_"))
    print(f"Workdir: {workdir}")
    proc = subprocess.run(
        [sys.executable, "-m", "nexcoder.cli", "--auto",
         "--project", str(workdir), PROMPT],
        timeout=1800)
    expected = ["index.html", "styles.css", "script.js"]
    missing = [name for name in expected if not (workdir / name).is_file()]
    verifier = Path(__file__).with_name("verify_product_page.mjs")
    behavior = subprocess.run(
        ["node", str(verifier), str(workdir)],
        capture_output=True, text=True, timeout=30,
    ) if not missing else None
    if (proc.returncode != 0 or missing or behavior is None
            or behavior.returncode != 0):
        print(f"FAIL: exit={proc.returncode}, missing={missing}")
        if behavior is not None:
            print((behavior.stdout + behavior.stderr)[-3000:])
        return 1
    print(behavior.stdout.strip())
    print("PASS: files created and theme behavior verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
