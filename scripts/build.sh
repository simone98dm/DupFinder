#!/bin/sh
# Packages the desktop app on macOS (dist/DupFinder.app) or Linux (dist/DupFinder/DupFinder).
# --onedir: PyInstaller does not support one-file .app bundles, and the folder starts faster anyway.
set -eu
. "$(dirname "$0")/venv.sh"
"$VENV_PY" -m pip install pyinstaller
exec "$VENV_PY" build_app.py --onedir
