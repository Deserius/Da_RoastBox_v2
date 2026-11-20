#!/usr/bin/env python3
"""Da RoastBox - double-click this file to run the app.

This checks everything the app needs, fixes what it safely can, starts the
server, and opens the app in your default browser. No MongoDB, Node.js, or
Yarn install is required for normal use:

* The database is built in and stores its data in backend/local_storage/.
* The frontend ships prebuilt and is served by this same process.

If you're not already inside a Python virtual environment, running this file
creates one at .venv (next to this file) on first use, installs the backend
packages into it, then re-launches itself inside that environment. This is
what makes "just run server.py" work the same whether you double-click it,
run `python server.py`, or run `py server.py` with a bare system Python that
has nothing installed yet.

First time here? Run this once to set your API keys (OpenAI, OpenRouter,
ElevenLabs, Stripe, Google) in a small window that verifies and saves them:

    python install.py

Then run this file:

    python server.py

All flags are passed straight through, e.g.:
    python server.py --port 8002 --no-browser
    python server.py --check      (diagnose only, change nothing - never creates a venv)
    python server.py --fix        (repair backend/.env, then start)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
VENV = ROOT / ".venv"
THIS_FILE = Path(__file__).resolve()


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def _already_in_a_venv() -> bool:
    """True when the running interpreter is some virtual environment, ours or not.

    We only auto-create and relaunch into our own .venv when running under a
    bare system interpreter. If the caller already activated their own venv
    (or this is a container/CI image with its own isolation), we trust it
    instead of forcing a second one on top of it.
    """
    base = getattr(sys, "base_prefix", None) or getattr(sys, "real_prefix", None) or sys.prefix
    return Path(sys.prefix).resolve() != Path(base).resolve()


def _packages_importable(python: Path) -> bool:
    probe = (
        "import fastapi, uvicorn, pydantic, motor, pymongo, mongomock, mongomock_motor, "
        "openai, stripe, elevenlabs, dotenv, multipart, cryptography"
    )
    result = subprocess.run([str(python), "-c", probe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def _bootstrap_and_relaunch(argv: list[str]) -> int:
    """Create .venv if missing, install backend requirements if missing, then re-run this file inside it."""
    vpy = _venv_python()

    if not vpy.exists():
        print("==> First run: creating a Python virtual environment (.venv)...", flush=True)
        created = subprocess.run([sys.executable, "-m", "venv", str(VENV)])
        if created.returncode != 0 or not vpy.exists():
            print(
                "\nCould not create .venv. Check that the folder is writable and that\n"
                "antivirus is not blocking python.exe, then try again.\n",
                file=sys.stderr,
            )
            return 1

    if not _packages_importable(vpy):
        print("==> Installing backend packages (a few minutes the first time)...", flush=True)
        subprocess.run([str(vpy), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
        installed = subprocess.run([str(vpy), "-m", "pip", "install", "-r", str(BACKEND / "requirements.txt")])
        if installed.returncode != 0:
            print(
                "\nCould not install the Python packages. See the error above.\n"
                f'You can retry by hand with:  "{vpy}" -m pip install -r backend\\requirements.txt\n',
                file=sys.stderr,
            )
            return 1
        print("==> Setup complete\n", flush=True)

    result = subprocess.run([str(vpy), str(THIS_FILE), *argv])
    return result.returncode


if __name__ == "__main__":
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))

    args = sys.argv[1:]
    # --check is a promise to "change nothing" - never create or install into a venv for it.
    # ROASTBOX_SKIP_VENV lets a container/CI image that manages its own interpreter opt out.
    skip_bootstrap = "--check" in args or _already_in_a_venv() or os.environ.get("ROASTBOX_SKIP_VENV") == "1"

    if not skip_bootstrap:
        raise SystemExit(_bootstrap_and_relaunch(args))

    import run_server

    raise SystemExit(run_server.main(args))
