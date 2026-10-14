#!/bin/sh
# Starts DupFinder on macOS and Linux: prepares .venv on first run, builds the interface and opens the app.
# Usage: scripts/run.sh [folders…] [--browser] [--port N] …   (same options as python -m dupfinder --help)
set -eu
. "$(dirname "$0")/venv.sh"
exec "$VENV_PY" start.py "$@"
