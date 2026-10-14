# Sourced by run.sh and build.sh (macOS and Linux): creates .venv with the optional extras on first use
# and sets VENV_PY. PYTHON=python3.12 scripts/run.sh picks another interpreter.
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "$PY not found: install Python 3.8 or later."; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "npm not found: install Node.js 20.19 or later (https://nodejs.org)."; exit 1; }

VENV_PY=.venv/bin/python
if [ ! -f .venv/.installed ]; then
  if [ ! -x "$VENV_PY" ]; then
    echo "Creating .venv…"
    "$PY" -m venv .venv || { echo "Could not create .venv (Debian/Ubuntu: sudo apt install python3-venv)."; exit 1; }
  fi
  # Linux: pywebview needs a GUI toolkit; the Qt one comes from pip, GTK would need system packages
  case "$(uname -s)" in Linux) WEBVIEW="pywebview[qt]" ;; *) WEBVIEW="pywebview" ;; esac
  "$VENV_PY" -m pip install --upgrade pip
  if "$VENV_PY" -m pip install "$WEBVIEW" Pillow send2trash; then
    touch .venv/.installed
  else
    echo "Warning: optional extras not installed (retried next time): DupFinder opens in the browser."
  fi
fi

command -v 7z >/dev/null 2>&1 || command -v 7zz >/dev/null 2>&1 || [ -x /opt/homebrew/bin/7zz ] || [ -x /usr/local/bin/7zz ] ||
  echo "Note: 7-Zip not found, 7z and RAR archives are skipped (macOS: brew install sevenzip; Debian/Ubuntu: sudo apt install 7zip)."
