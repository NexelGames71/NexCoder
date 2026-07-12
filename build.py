"""NexCoder build script — builds React frontend and packages Python app via PyInstaller."""

import os
import sys
import subprocess
import shutil
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(PROJECT_ROOT, "nexcoder", "ui")
BUILT_UI_DIR = os.path.join(PROJECT_ROOT, "nexcoder", "resources", "ui")


def run_command(cmd: str, cwd: str) -> None:
    """Run a terminal command and raise an error on failure."""
    print(f"Running: {cmd} in {cwd}")
    # On Windows, we need shell=True for npm.cmd, etc.
    shell = sys.platform == "win32"
    result = subprocess.run(cmd, cwd=cwd, shell=shell)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}: {cmd}")
        sys.exit(result.returncode)


def main() -> None:
    print("=== Starting NexCoder Build ===")

    # 1. Build React Frontend
    print("\n--- 1. Building React Frontend ---")
    if not os.path.exists(UI_DIR):
        print(f"Error: React UI source directory not found: {UI_DIR}")
        sys.exit(1)

    # Clean previous build
    if os.path.exists(BUILT_UI_DIR):
        print("Cleaning old UI build...")
        shutil.rmtree(BUILT_UI_DIR)

    # Run npm install and build
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    run_command(f"{npm_cmd} install", UI_DIR)
    run_command(f"{npm_cmd} run build", UI_DIR)

    if not os.path.exists(BUILT_UI_DIR):
        print(f"Error: Built React assets not found in {BUILT_UI_DIR}")
        sys.exit(1)
    print("React UI built successfully!")

    # 2. Package Python App using PyInstaller
    print("\n--- 2. Packaging Application via PyInstaller ---")
    # Determine correct python path in virtual env
    if sys.platform == "win32":
        venv_python = os.path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe")
        venv_pip = os.path.join(PROJECT_ROOT, "venv", "Scripts", "pip.exe")
        venv_pyinstaller = os.path.join(PROJECT_ROOT, "venv", "Scripts", "pyinstaller.exe")
    else:
        venv_python = os.path.join(PROJECT_ROOT, "venv", "bin", "python")
        venv_pip = os.path.join(PROJECT_ROOT, "venv", "bin", "pip")
        venv_pyinstaller = os.path.join(PROJECT_ROOT, "venv", "bin", "pyinstaller")

    # Install pyinstaller and requirements if not present
    if not os.path.exists(venv_pyinstaller):
        print("Installing build dependencies...")
        run_command(f"{venv_pip} install -r requirements.txt", PROJECT_ROOT)
        run_command(f"{venv_pip} install pyinstaller", PROJECT_ROOT)

    # Clean up previous build outputs. On Windows the previous packaged app
    # can keep dist\NexCoder locked if Explorer, QtWebEngine, or a stale shell
    # still has a handle open. In that case, keep the normal build moving by
    # using a timestamped fallback dist directory.
    dist_dir = os.path.join(PROJECT_ROOT, "dist")
    build_dir = os.path.join(PROJECT_ROOT, "build")
    output_dist_dir = dist_dir
    for d in (dist_dir, build_dir):
        if os.path.exists(d):
            print(f"Cleaning build artifacts directory: {d}")
            try:
                shutil.rmtree(d)
            except Exception as e:
                print(f"Warning: could not clean {d}: {e}")
                if d == dist_dir:
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_dist_dir = os.path.join(PROJECT_ROOT, f"dist_{stamp}")
                    print(f"Using fallback dist directory: {output_dist_dir}")

    # Run PyInstaller
    spec_file = os.path.join(PROJECT_ROOT, "nexcoder.spec")
    dist_arg = "" if output_dist_dir == dist_dir else f' --distpath "{output_dist_dir}"'
    run_command(f'"{venv_python}" -m PyInstaller --clean -y{dist_arg} "{spec_file}"', PROJECT_ROOT)

    print("\n=== NexCoder Build Complete! ===")
    print(f"Executable is located in: {output_dist_dir}")


if __name__ == "__main__":
    main()
