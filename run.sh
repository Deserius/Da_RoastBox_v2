#!/usr/bin/env bash
# Start Da RoastBox and open it in the default browser (macOS / Linux).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
[ -d .venv ] || { echo "No .venv found - running setup.sh first"; ./setup.sh; }
[ -d frontend/node_modules ] || { echo "No frontend deps - running setup.sh first"; ./setup.sh; }
cd backend
exec ../.venv/bin/python run_server.py "$@"
