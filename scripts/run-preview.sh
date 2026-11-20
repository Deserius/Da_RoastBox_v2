#!/usr/bin/env bash
# Run the cloned app locally after dependencies and MongoDB have been installed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python scripts/init_env.py --preview
python - <<'PY'
import os
from dotenv import load_dotenv
from pymongo import MongoClient
load_dotenv('backend/.env')
try:
    MongoClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=3000).admin.command('ping')
except Exception as exc:
    raise SystemExit(f'MongoDB is not reachable. Start MongoDB or configure MONGO_URL in backend/.env. ({exc})')
PY
(
  cd "$ROOT/backend"
  exec uvicorn server:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8001}"
) &
API_PID=$!
(
  cd "$ROOT/frontend"
  export HOST="${HOST:-0.0.0.0}" PORT="${PORT:-3000}" BROWSER=none DISABLE_EMERGENT_OVERLAY=true
  export API_PROXY_TARGET="${API_PROXY_TARGET:-http://127.0.0.1:${API_PORT:-8001}}"
  exec corepack yarn start
) &
UI_PID=$!
cleanup() { kill "$API_PID" "$UI_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
printf '\nDa RoastBox running at http://localhost:%s\n' "${PORT:-3000}"
wait -n "$API_PID" "$UI_PID"
