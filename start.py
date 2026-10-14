#!/usr/bin/env python3
"""Builds the React frontend and starts DupFinder.

Usage:
    python start.py                       builds the interface and opens DupFinder (own window with pywebview)
    python start.py D:\\Foto --port 9000   arguments are passed to `python -m dupfinder`

Requires Node.js (npm) for the build. On first run it installs the frontend dependencies.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"


def main() -> int:
    npm = shutil.which("npm")
    if not npm:
        print("npm not found: install Node.js (https://nodejs.org) to build the frontend.")
        return 1
    if not (FRONTEND / "node_modules").is_dir():
        print("Installing frontend dependencies…", flush=True)
        cmd = "ci" if (FRONTEND / "package-lock.json").is_file() else "install"
        subprocess.run([npm, cmd, "--no-audit", "--no-fund"], cwd=FRONTEND, check=True)
    print("Building the frontend…", flush=True)
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)
    try:
        return subprocess.call([sys.executable, "-m", "dupfinder", *sys.argv[1:]], cwd=ROOT)
    except KeyboardInterrupt:      # Ctrl+C: the backend shuts down on its own
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        print(f"Command failed ({e.returncode}): {' '.join(map(str, e.cmd))}")
        sys.exit(e.returncode)
