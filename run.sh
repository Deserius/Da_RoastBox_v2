#!/usr/bin/env bash
# Start Da RoastBox and open it in the default browser (macOS / Linux).
# All first-run setup (virtual environment, package install) is handled by
# server.py itself - this just finds a Python interpreter and hands off to it.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PYEXE=""
for v in python3.13 python3.12 python3.11 python3.14 python3; do
  if command -v "$v" >/dev/null 2>&1; then PYEXE="$v"; break; fi
done
if [ -z "$PYEXE" ]; then
  echo "Python was not found. Install Python 3.11-3.14 and try again." >&2
  exit 1
fi

exec "$PYEXE" server.py "$@"
