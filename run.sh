#!/usr/bin/env bash
# Start Da RoastBox and open it in the default browser (macOS / Linux).
# First run: creates a Python virtual environment and installs the backend
# packages. No MongoDB, Node.js, or Yarn needed - the database is built in
# and the frontend ships prebuilt.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -x ".venv/bin/python" ]; then
  echo "==> First-time setup"
  PYEXE=""
  for v in python3.13 python3.12 python3.11 python3.14 python3; do
    if command -v "$v" >/dev/null 2>&1; then PYEXE="$v"; break; fi
  done
  if [ -z "$PYEXE" ]; then
    echo "Python was not found. Install Python 3.11-3.14 and try again." >&2
    exit 1
  fi
  echo "==> Using $("$PYEXE" --version)"
  "$PYEXE" -m venv .venv
  echo "==> Installing Python packages"
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r backend/requirements.txt
  echo "==> Setup complete"
fi

echo
echo "Starting Da RoastBox..."
echo "  Set your API keys any time with:  python3 install.py"
echo "  Settings console passphrase: roastbox"
echo
exec .venv/bin/python server.py "$@"
