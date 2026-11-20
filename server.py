#!/usr/bin/env python3
"""Da RoastBox - double-click this file to run the app.

This checks everything the app needs, fixes what it safely can, starts the
server, and opens the app in your default browser. No MongoDB, Node.js, or
Yarn install is required for normal use:

* The database is built in and stores its data in backend/local_storage/.
* The frontend ships prebuilt and is served by this same process.

First time here? Run this once to set your API keys (OpenAI, OpenRouter,
ElevenLabs, Stripe, Google) in a small window that verifies and saves them:

    python install.py

Then run this file:

    python server.py

All flags are passed straight through, e.g.:
    python server.py --port 8002 --no-browser
    python server.py --check      (diagnose only, change nothing)
    python server.py --fix        (repair backend/.env, then start)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"

if __name__ == "__main__":
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    import run_server

    raise SystemExit(run_server.main(sys.argv[1:]))
