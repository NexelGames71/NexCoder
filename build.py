"""NexCoder build script — builds React frontend and packages Python app via PyInstaller."""

import os
import re
import sys
import subprocess
import shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(PROJECT_ROOT, "nexcoder", "ui")
BUILT_UI_DIR = os.path.join(PROJECT_ROOT, "nexcoder", "resources", "ui")
LANGUAGE_SERVERS_DIR = os.path.join(PROJECT_ROOT, "language-servers")
UI_ASSET_REF_PATTERN = re.compile(r'(?:src|href)="\.?/([^"]+)"')


def run_command(cmd: str, cwd: str) -> None:
    """Run a terminal command and raise an error on failure."""
    print(f"Running: {cmd} in {cwd}")
    # On Windows, we need shell=True for npm.cmd, etc.
    shell = sys.platform == "win32"
    result = subprocess.run(cmd, cwd=cwd, shell=shell)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}: {cmd}")
        sys.exit(result.returncode)


def validate_ui_bundle(ui_root: str, label: str) -> None:
    """Ensure index.html does not point at missing packaged assets."""
    index_path = os.path.join(ui_root, "index.html")
    if not os.path.isfile(index_path):
        print(f"Error: {label} index.html not found: {index_path}")
        sys.exit(1)

    with open(index_path, "r", encoding="utf-8") as handle:
        html = handle.read()

    missing: list[str] = []
    for ref in UI_ASSET_REF_PATTERN.findall(html):
        if not ref.startswith("assets/"):
            continue
        asset_path = os.path.join(ui_root, *ref.split("/"))
        if not os.path.isfile(asset_path):
            missing.append(ref)

    if missing:
        print(f"Error: {label} is missing referenced assets:")
        for ref in missing:
            print(f"  - {ref}")
        sys.exit(1)


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

    # Reproduce the lockfile exactly before building.
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    run_command(f"{npm_cmd} ci", UI_DIR)
    run_command(f"{npm_cmd} run build", UI_DIR)

    if not os.path.exists(BUILT_UI_DIR):
        print(f"Error: Built React assets not found in {BUILT_UI_DIR}")
        sys.exit(1)
    validate_ui_bundle(BUILT_UI_DIR, "Built React UI")
    print("React UI built successfully!")

    # Install the exact locked language-server dependencies. The PyInstaller
    # spec bundles these modules plus the Node runtime so LSP works on clean
    # machines without a global Node installation.
    print("\n--- 2. Preparing Language Servers ---")
    if not os.path.isfile(os.path.join(LANGUAGE_SERVERS_DIR, "package-lock.json")):
        print("Error: language-servers/package-lock.json is missing")
        sys.exit(1)
    run_command(f"{npm_cmd} ci --omit=dev", LANGUAGE_SERVERS_DIR)
    if not shutil.which("node"):
        print("Error: Node.js runtime was not found for LSP packaging")
        sys.exit(1)
    print("Language servers prepared successfully!")

    # 3. Package Python App using PyInstaller
    print("\n--- 3. Packaging Application via PyInstaller ---")
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

    # NexCoder has one canonical packaging location. If a running app or
    # Explorer window locks it, fail clearly so developers do not accidentally
    # launch PyInstaller's temporary work files or ship an alternate build.
    dist_dir = os.path.join(PROJECT_ROOT, "dist")
    build_dir = os.path.join(PROJECT_ROOT, "build")
    for d in (dist_dir, build_dir):
        if os.path.exists(d):
            print(f"Cleaning build artifacts directory: {d}")
            try:
                shutil.rmtree(d)
            except Exception as e:
                print(f"Error: could not clean {d}: {e}")
                print("Close NexCoder and any Explorer windows using that "
                      "folder, then run the build again.")
                sys.exit(1)

    # Run PyInstaller
    spec_file = os.path.join(PROJECT_ROOT, "nexcoder.spec")
    run_command(
        f'"{venv_python}" -m PyInstaller --clean -y "{spec_file}"',
        PROJECT_ROOT,
    )

    packaged_ui_dir = os.path.join(
        dist_dir, "NexCoder", "_internal", "nexcoder", "resources", "ui")
    validate_ui_bundle(packaged_ui_dir, "Packaged React UI")

    print("\n=== NexCoder Build Complete! ===")
    print(f"Executable is located in: {dist_dir}")


if __name__ == "__main__":
    main()
