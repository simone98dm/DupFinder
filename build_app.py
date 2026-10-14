#!/usr/bin/env python3
"""Packages DupFinder as a desktop app with PyInstaller: dist/DupFinder.exe on Windows,
dist/DupFinder.app on macOS, dist/DupFinder on Linux. Nothing else is needed to run it
(7-Zip, if installed, is still used for 7z and RAR).

Usage:
    pip install pyinstaller pywebview Pillow send2trash
    python build_app.py            one-file executable (slower first start: it unpacks itself)
    python build_app.py --onedir   a folder with the executable (starts faster)
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    if subprocess.call([sys.executable, "-m", "PyInstaller", "--version"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        print("PyInstaller is missing: pip install pyinstaller pywebview Pillow send2trash")
        return 1
    npm = shutil.which("npm")
    if not npm:
        print("npm not found: install Node.js to build the interface.")
        return 1
    if not (ROOT / "frontend" / "node_modules").is_dir():
        subprocess.run([npm, "ci"], cwd=ROOT / "frontend", check=True)
    subprocess.run([npm, "run", "build"], cwd=ROOT / "frontend", check=True)

    sep = ";" if os.name == "nt" else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "DupFinder",
        "--onedir" if "--onedir" in sys.argv else "--onefile",
        "--add-data", f"{ROOT / 'dupfinder' / 'web'}{sep}dupfinder/web",
        "--collect-submodules", "dupfinder",
        str(ROOT / "dupfinder_app.py"),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    print("\nDone: the app is in", ROOT / "dist")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        print(f"Command failed ({e.returncode}): {' '.join(map(str, e.cmd))}")
        sys.exit(e.returncode)
