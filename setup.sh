#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Da RoastBox — one-command local setup (macOS / Linux). Windows uses setup.bat.
#
# Why this script exists
#   The bundled `install.sh` runs `yarn install --frozen-lockfile`, which fails:
#   frontend/package.json pins two @emergentbase dev packages to tarballs on
#   assets.emergent.sh, a host that no longer resolves. Those packages only
#   provide the Emergent dev overlay and visual editor, and craco.config.js
#   already loads them defensively. So this drops just those two
#   devDependencies, installs with yarn, then puts package.json back.
#
#   yarn is required rather than preferred: the repo pins 46 transitive
#   versions via the yarn-only `resolutions` field, and npm's different hoisting
#   produces a tree that will not build (ajv 6 where ajv-keywords needs ajv 8).
#
# Usage:  ./setup.sh          install backend + frontend
#         ./setup.sh --run    install, then start both servers
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RUN_AFTER=0
[ "${1:-}" = "--run" ] && RUN_AFTER=1

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33mWARNING:\033[0m %s\n' "$*"; }
fail() { printf '\n\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# If anything aborts after we strip the overlay devDeps, put package.json back.
# Without this a failed install strands the user with a modified package.json.
PKG_BAK="frontend/package.json.bak"
restore_pkg() {
  if [ -f "$PKG_BAK" ]; then
    mv -f "$PKG_BAK" frontend/package.json 2>/dev/null || true
  fi
  if [ -f "frontend/yarn.lock.bak" ]; then
    mv -f "frontend/yarn.lock.bak" frontend/yarn.lock 2>/dev/null || true
  fi
}
trap restore_pkg EXIT INT TERM

# --- Python ---------------------------------------------------------------
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 &&
    "$c" -c 'import sys; assert (3,11) <= sys.version_info[:2] <= (3,13)' 2>/dev/null; then
    PY="$c"
    break
  fi
done
[ -n "$PY" ] || fail "Python 3.11, 3.12 or 3.13 is required (3.10 and older lack wheels for several pinned packages). Install one from https://www.python.org/downloads/ and rerun."

say "Using $($PY --version)"
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --quiet --upgrade pip || fail "Could not upgrade pip. Check your internet connection or proxy."

say "Installing backend dependencies"
[ -f backend/requirements.txt ] || fail "backend/requirements.txt is missing — the archive is incomplete."
pip install --quiet -r backend/requirements.txt ||
  fail "Backend dependency install failed. Scroll up for the failing package. Common causes: no internet, a proxy, or a missing build tool."

# --- Node ----------------------------------------------------------------
command -v node >/dev/null 2>&1 ||
  fail "Node.js 18+ is required. Install Node 20 or 22 LTS from https://nodejs.org and rerun."

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
say "Using Node $(node --version)"
[ "$NODE_MAJOR" -ge 18 ] ||
  fail "Node $(node --version) is too old. Install Node 20 or 22 LTS from https://nodejs.org and rerun."
[ "$NODE_MAJOR" -ge 25 ] &&
  warn "Node $(node --version) is newer than this project was built against. If the frontend misbehaves, install Node 20 or 22 LTS."

command -v yarn >/dev/null 2>&1 ||
  fail "yarn is required to install the frontend (the repo's pinned dependency tree depends on yarn's 'resolutions' field; npm produces a tree that will not build).
       Install it with one of:
           npm install -g yarn
           corepack enable && corepack prepare yarn@1.22.22 --activate"

# --- Frontend ------------------------------------------------------------
cd frontend
cp -f package.json package.json.bak

say "Removing the two unreachable @emergentbase dev packages"
python ../scripts/prepare_package_json.py package.json ||
  fail "Could not rewrite frontend/package.json."

# Some networks cannot reach registry.yarnpkg.com, and yarn 1 ignores
# --registry for URLs the lockfile already resolved. Swapping the host to
# registry.npmjs.org is safe: identical tarballs, identical sha1 fragments.
LOCK_BAK="yarn.lock.bak"
cp -f yarn.lock "$LOCK_BAK"
python ../scripts/fix_lockfile_registry.py yarn.lock

say "Installing frontend dependencies (this takes a few minutes)"
if ! yarn install --ignore-engines --non-interactive; then
  rest=0
  if [ -f "$LOCK_BAK" ]; then
    mv -f "$LOCK_BAK" yarn.lock
    rest=1
    say "Retrying against registry.yarnpkg.com"
    yarn install --ignore-engines --non-interactive || rest=0
  fi
  [ "$rest" = "1" ] || fail "yarn install failed. Scroll up for the real error. Common causes: no internet, a proxy, or antivirus locking node_modules."
fi
# Restore the committed lockfile: the rewritten copy was only needed for the
# install itself, and the repo should be left exactly as it shipped.
if [ -f "$LOCK_BAK" ]; then mv -f "$LOCK_BAK" yarn.lock; fi

mv -f package.json.bak package.json
cd ..

# --- .env ----------------------------------------------------------------
say "Preparing backend/.env"
python scripts/make_env.py || fail "Could not create backend/.env."

# --- Database ------------------------------------------------------------
say "Checking for a database on port 27017"
DB_UP=0
if command -v nc >/dev/null 2>&1 && nc -z 127.0.0.1 27017 2>/dev/null; then
  DB_UP=1
elif (exec 3<>/dev/tcp/127.0.0.1/27017) 2>/dev/null; then
  DB_UP=1
fi

if [ "$DB_UP" = "1" ]; then
  say "Setup complete — a database answered on port 27017"
else
  say "Setup complete — but nothing is answering on port 27017"
  cat <<'MSG'

The app cannot start until you provide a MongoDB.

  Local, with Docker:
      docker run -d -p 27017:27017 --name roastbox-mongo mongo:7

  Local, without Docker (macOS):
      brew tap mongodb/brew && brew install mongodb-community@7.0
      brew services start mongodb-community@7.0

  Free hosted cluster (easiest, no install):
      Sign up at https://www.mongodb.com/cloud/atlas/register,
      create an M0 cluster, add a database user, allow your IP, then copy the
      "mongodb+srv://..." connection string into backend/.env as MONGO_URL.

MSG
fi

say "How to start the app"
cat <<'MSG'

  Terminal 1 — backend
      cd backend && ../.venv/bin/uvicorn server:app --reload --port 8001

  Terminal 2 — frontend
      cd frontend && yarn start

  Then open http://localhost:3000 and choose "Browse as guest".

  Settings -> "Connect your services" (passphrase: roastbox) is where you paste
  your OpenRouter / OpenAI / ElevenLabs / Stripe / Google keys.

  ROASTBOX_DRY_RUN=true in backend/.env lets roasts generate with no internet
  access. Set it to false after adding a real provider key so live AI is used.

MSG

if [ "$RUN_AFTER" = "1" ]; then
  say "Starting both servers (Ctrl-C stops them)"
  (cd backend && ../.venv/bin/uvicorn server:app --port 8001) &
  BACKEND_PID=$!
  trap 'kill $BACKEND_PID 2>/dev/null || true; restore_pkg' EXIT INT TERM
  (cd frontend && yarn start)
fi
