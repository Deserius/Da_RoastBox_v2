#!/usr/bin/env python3
"""Start Da RoastBox, diagnose what is wrong, and open the browser.

Why this exists
---------------
``uvicorn server:app`` fails with a bare traceback for every avoidable
misconfiguration: a missing module, a missing ``backend/.env``, a port already
in use. This launcher checks each of those first, fixes what it safely can,
and prints a short instruction for anything it cannot.

No database server, no Node.js, and no Yarn are required to run the app:

* The database is built in (see ``db.py``) and needs nothing installed.
  Set ``MONGO_URL`` in ``backend/.env`` to a real MongoDB/Atlas connection
  string only if you specifically want one.
* The frontend ships prebuilt (``frontend/build``). This launcher serves it
  from the same process and port as the API, so there is only one server to
  run. Pass ``--dev`` to use the Node/Yarn frontend dev server instead, for
  editing frontend source.

To set API keys (OpenAI, OpenRouter, ElevenLabs, Stripe, Google), run
``python install.py`` from the project root — a small desktop window that
verifies each key and saves it straight into ``backend/.env``.

Usage
-----
    python server.py                   # from the project root (recommended)
    python run_server.py               # same thing, from backend/
    python run_server.py --port 8001 --no-browser
    python run_server.py --fix         # repair .env/dependencies, then start
    python run_server.py --check       # diagnose only, change nothing
    python run_server.py --dev         # run the Node/Yarn frontend dev server too

Run it with the project venv:
    ..\\.venv\\Scripts\\python run_server.py      (from backend\\, Windows)
    ../.venv/bin/python run_server.py            (from backend/, macOS/Linux)
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent
ENV_FILE = BACKEND / ".env"
ENV_EXAMPLE = BACKEND / ".env.example"
FRONTEND_BUILD = ROOT / "frontend" / "build"

# Modules that must import before uvicorn can load server:app. Checked up front
# so the user gets a package name instead of a 40-line traceback.
REQUIRED = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("pydantic", "pydantic"),
    ("pymongo", "pymongo"),
    ("motor", "motor"),
    ("mongomock", "mongomock"),
    ("mongomock_motor", "mongomock-motor"),
    ("openai", "openai"),
    ("stripe", "stripe"),
    ("elevenlabs", "elevenlabs"),
    ("dotenv", "python-dotenv"),
    ("multipart", "python-multipart"),
    ("cryptography", "cryptography"),
]

OK = "  [ok]   "
WARN = "  [warn] "
FAIL = "  [fail] "
INFO = "  ...    "


def say(marker: str, text: str) -> None:
    print(marker + text, flush=True)


def rule(title: str = "") -> None:
    print("\n" + ("=" * 62), flush=True)
    if title:
        print("  " + title, flush=True)
        print("=" * 62, flush=True)


# --------------------------------------------------------------------- checks
def check_python() -> list[str]:
    problems = []
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 11):
        problems.append(
            f"Python {major}.{minor} is too old. Install 3.11 or newer "
            "(3.13 or 3.14 recommended) and recreate .venv."
        )
    else:
        say(OK, f"Python {major}.{minor}.{sys.version_info[2]}")
    return problems


def check_modules() -> list[str]:
    missing = []
    for module, package in REQUIRED:
        if importlib.util.find_spec(module) is None:
            missing.append(package)
    if missing:
        say(FAIL, "Missing Python packages: " + ", ".join(sorted(set(missing))))
        return [
            "Install the backend dependencies with this exact interpreter, then run this again:",
            f'    "{sys.executable}" -m pip install -r "{BACKEND / "requirements.txt"}"',
            "Or just run the project's server.py from the project root - it creates a",
            "virtual environment and installs everything automatically:",
            f"    python {rel(ROOT / 'server.py')}",
        ]
    say(OK, f"All {len(REQUIRED)} required packages import")
    return []


def _fix_command() -> str:
    """The correct re-run command for how this process was actually started.

    __name__ is "__main__" only when this file was launched directly
    (``python backend/run_server.py``); the root server.py imports this
    module by name instead, so __name__ is "run_server" there. Getting this
    wrong tells someone running via server.py to run a file one level removed
    from where they are.
    """
    if __name__ == "__main__":
        return "python run_server.py --fix"
    return f"python {rel(ROOT / 'server.py')} --fix"


def check_env(fix: bool) -> list[str]:
    if ENV_FILE.exists():
        say(OK, f"{rel(ENV_FILE)} found")
        return []
    if not fix:
        say(FAIL, f"{rel(ENV_FILE)} is missing")
        return [
            "Create it, then run this again:",
            f"    {_fix_command()}      (generates a working .env)",
            "Or set your API keys with the key manager, which creates it for you:",
            "    python install.py",
        ]
    say(WARN, f"{rel(ENV_FILE)} missing - generating one from .env.example")
    generator = ROOT / "scripts" / "make_env.py"
    if generator.exists():
        rc = subprocess.call([sys.executable, str(generator)])
        if rc == 0 and ENV_FILE.exists():
            say(OK, f"{rel(ENV_FILE)} generated")
            return []
    # Fallback if the helper is absent: copy the example and add a secret.
    import secrets

    text = ENV_EXAMPLE.read_text(encoding="utf-8") if ENV_EXAMPLE.exists() else ""
    lines = [ln for ln in text.splitlines()
             if not ln.strip().startswith(("MONGO_URL=", "DB_NAME=", "JWT_SECRET="))]
    lines += [
        "", "# --- generated by run_server.py ---",
        "MONGO_URL=embedded",
        "DB_NAME=da_roastbox",
        f"JWT_SECRET={secrets.token_hex(32)}",
    ]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    say(OK, f"{rel(ENV_FILE)} generated")
    return []


def check_env_values() -> list[str]:
    """Read .env without importing the app, and flag values that break startup."""
    problems = []
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        values[key.strip()] = val.strip()

    jwt = values.get("JWT_SECRET", "")
    if not jwt:
        problems.append("JWT_SECRET is empty in backend/.env - sign-in will fail. "
                        "Run with --fix to regenerate, or set any long random string.")
    elif len(jwt) < 32:
        say(WARN, f"JWT_SECRET is only {len(jwt)} characters; use 32 or more.")
    else:
        say(OK, "JWT_SECRET present")
    return problems


def check_port(port: int) -> list[str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        if s.connect_ex(("127.0.0.1", port)) == 0:
            say(WARN, f"Port {port} is already in use")
            return [
                f"Something is already listening on port {port}.",
                f"Stop it, or start on another port:  python run_server.py --port {port + 1}",
                f"    Find it:  netstat -ano | findstr :{port}",
            ]
    say(OK, f"Port {port} is free")
    return []


def mongo_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def check_database() -> list[str]:
    """Report the database mode. Only a *local* real-MongoDB choice can block startup."""
    mongo_url = ""
    try:
        for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if s.startswith(("MONGO_URL=", "MONGODB_URL=")):
                mongo_url = s.split("=", 1)[1].strip()
    except OSError:
        pass

    if not mongo_url or mongo_url.lower() == "embedded":
        say(OK, "Database: built-in, no installation needed (backend/local_storage/)")
        return []
    if mongo_url.startswith("mongodb+srv://"):
        say(OK, "Database: remote MongoDB (Atlas) configured in .env")
        return []
    if mongo_url.startswith(("mongodb://localhost", "mongodb://127.0.0.1")):
        host_port = mongo_url.split("//", 1)[1].split("/", 1)[0]
        host, _, port_s = host_port.partition(":")
        port = int(port_s or 27017)
        if mongo_reachable(host or "127.0.0.1", port):
            say(OK, f"Database: local MongoDB reachable on {host or '127.0.0.1'}:{port}")
            return []
        say(FAIL, f"MONGO_URL points at {mongo_url} but nothing is listening there")
        return [
            f"backend/.env sets MONGO_URL to a local MongoDB that is not running.",
            "Either start that MongoDB, or switch back to the built-in database",
            "by setting MONGO_URL=embedded in backend/.env (recommended; no install needed).",
        ]
    say(OK, "Database: remote MongoDB configured in .env")
    return []


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


# ------------------------------------------------------------- first-run GUI
def _has_display() -> bool:
    """Best-effort guess at whether a desktop session is available for Tk.

    Windows always has one (Tk talks to the native GUI, not X11). On Linux/macOS
    we look for the environment variables a desktop session sets; a headless
    server/container/sandbox has neither, so we skip trying to pop a window
    that would just fail.
    """
    if os.name == "nt":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _read_env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        values[key.strip()] = val
    return values


def has_a_provider_key() -> bool:
    """True once at least one AI provider credential is actually filled in."""
    values = _read_env_values()
    return bool(values.get("OPENROUTER_API_KEY") or values.get("OPENAI_API_KEY") or values.get("EMERGENT_LLM_KEY"))


def launch_key_setup_gui() -> None:
    """Open install.py's GUI and wait for it to close before continuing.

    install.py pre-populates any key already saved in backend/.env (showing
    it as already saved, not blank), so re-running this on an existing,
    partially-configured install just lets someone fill the rest in or
    re-verify - it never throws away what is already there. That same window
    is what writes the final backend/.env, via its own Save/Save All buttons.
    """
    installer = ROOT / "install.py"
    if not installer.exists():
        say(WARN, "install.py is missing - cannot open the key setup window")
        return
    say(INFO, "No AI provider key is configured yet - opening the key setup window...")
    say(INFO, "Enter at least one of OpenAI or OpenRouter, click Verify, then Save (or Save All) and close it.")
    try:
        subprocess.run([sys.executable, str(installer)])
    except OSError as exc:
        say(WARN, f"Could not open the key setup window automatically ({exc})")
        say(INFO, "Run it yourself any time:  python install.py")


# -------------------------------------------------------------------- runtime
def wait_for(url: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as r:
                if r.status < 500:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.4)
    return False


def frontend_dev_ready() -> bool:
    for port in (3000, 3001):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=1.0):
                return True
        except (urllib.error.URLError, OSError):
            continue
    return False


def start_frontend_dev_server() -> subprocess.Popen | None:
    """Only used with --dev, for editing frontend source. Not needed otherwise."""
    frontend = ROOT / "frontend"
    if not (frontend / "package.json").exists():
        return None
    if not (frontend / "node_modules").exists():
        say(WARN, "frontend/node_modules is missing - skipping the dev server")
        say(INFO, "Install it once:  cd frontend && yarn install --ignore-engines")
        return None
    yarn = shutil.which("yarn")
    if not yarn:
        say(WARN, "yarn is not on PATH - skipping the dev server")
        return None

    env = dict(os.environ)
    env.setdefault("BROWSER", "none")      # we open the browser ourselves
    env.setdefault("PORT", "3000")
    env.setdefault("HOST", "0.0.0.0")
    creation = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(
            [yarn, "start"], cwd=str(frontend), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, creationflags=creation,
        )
    except OSError as exc:
        say(FAIL, f"Could not start the frontend dev server: {exc}")
        return None
    say(INFO, "Frontend dev server starting (first compile takes a minute)")

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            if any(k in line for k in ("Compiled", "Failed to compile", "error", "Error")):
                print("  frontend | " + line.rstrip(), flush=True)

    threading.Thread(target=pump, daemon=True).start()
    return proc


def open_browser_when_ready(url: str, backend_health: str, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if wait_for(backend_health, 2):
            break
        time.sleep(0.5)
    try:
        webbrowser.open(url)
        say(OK, f"Opened {url} in your default browser")
    except Exception as exc:  # noqa: BLE001 - browser choice is best effort
        say(WARN, f"Could not open a browser automatically ({exc})")
        say(INFO, f"Open it yourself: {url}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Start Da RoastBox and open the browser.")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8001")))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--backend-only", action="store_true", help="do not serve the frontend at all")
    ap.add_argument("--dev", action="store_true",
                     help="run the Node/Yarn frontend dev server on :3000 instead of the prebuilt build")
    ap.add_argument("--fix", action="store_true", help="repair .env before starting")
    ap.add_argument("--check", action="store_true", help="diagnose only, then exit")
    ap.add_argument("--reload", action="store_true", help="auto-reload on file changes")
    ap.add_argument("--no-key-setup-gui", action="store_true",
                     help="never auto-open the key setup window, even on a first run with no keys configured")
    args = ap.parse_args(argv)

    os.chdir(BACKEND)
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))

    rule("Da RoastBox - startup checks")
    problems: list[str] = []
    problems += check_python()
    problems += check_modules()
    if not problems:
        # Treat a missing .env the same as --fix here: a first run should not
        # dead-end with an instruction to re-run a flag, it should just get a
        # working .env (then the key setup window below fills in the keys).
        problems += check_env(args.fix or not ENV_FILE.exists())

    # First run (or an existing .env nobody has put a real key into yet): open
    # the same GUI "python install.py" uses, pre-populated with whatever is
    # already saved, and let that window write the final backend/.env. Skipped
    # for --check (it promises to change nothing) and on a headless machine
    # with no desktop session, where a Tk window could never appear anyway.
    if not problems and not args.check and not args.no_key_setup_gui and not has_a_provider_key():
        if _has_display():
            launch_key_setup_gui()
        else:
            say(WARN, "No AI provider key is configured yet, and no desktop session was found to ask for one")
            say(INFO, "Set at least one key with:  python install.py")
            say(INFO, "(or set OPENROUTER_API_KEY / OPENAI_API_KEY directly in backend/.env)")

    if ENV_FILE.exists():
        problems += check_env_values()
    problems += check_port(args.port)
    db_notes = check_database()

    blocking = [p for p in problems if p]
    if blocking:
        rule("Fix these before the server can start")
        for line in blocking:
            print("  " + line if line else "", flush=True)
        print(flush=True)
        return 1

    if db_notes:
        rule("Database")
        for line in db_notes:
            print("  " + line if line else "", flush=True)
        print(flush=True)
        return 1

    serve_build = not args.backend_only and not args.dev
    if serve_build and not (FRONTEND_BUILD / "index.html").is_file():
        # This ships committed to git specifically so it survives a plain `git
        # clone` or a GitHub "Download ZIP" (both skip anything gitignored).
        # Missing here means a non-standard checkout; try to self-heal only
        # when the tools to do so are already present, without reaching out
        # to install anything new (that path is setup.bat/setup.sh's job).
        frontend_dir = ROOT / "frontend"
        node_modules = frontend_dir / "node_modules"
        yarn = shutil.which("yarn")
        if yarn and node_modules.is_dir():
            say(WARN, f"{rel(FRONTEND_BUILD)} not found - building it now (node_modules is already installed)")
            built = subprocess.run([yarn, "build"], cwd=str(frontend_dir),
                                    env={**os.environ, "CI": "false"})
            if built.returncode != 0:
                say(FAIL, "Frontend build failed; see the output above")
        else:
            say(WARN, f"{rel(FRONTEND_BUILD)} not found - the API will run without a frontend")
            say(INFO, "Build it once:  cd frontend && yarn install --ignore-engines && yarn build")

    if serve_build:
        if (FRONTEND_BUILD / "index.html").is_file():
            os.environ["FRONTEND_BUILD_DIR"] = str(FRONTEND_BUILD)
            say(OK, f"Frontend: serving prebuilt {rel(FRONTEND_BUILD)} from this same server")
        else:
            serve_build = False

    if args.check:
        rule("All checks passed")
        return 0

    # Import the app here so an import error is reported cleanly.
    try:
        import server  # noqa: F401  - imported for its side effects
    except ModuleNotFoundError as exc:
        rule("Import failed")
        print(f"  Missing module: {exc.name}", flush=True)
        print(
            "  The package it belongs to is not installed. Reinstall with this exact interpreter:\n"
            f'      "{sys.executable}" -m pip install -r "{BACKEND / "requirements.txt"}"\n'
            "  Or just run the project's server.py from the project root instead - it sets\n"
            "  up a virtual environment and installs everything automatically:\n"
            f"      python {rel(ROOT / 'server.py')}",
            flush=True,
        )
        return 1
    except Exception as exc:  # noqa: BLE001 - configuration errors land here
        rule("Startup failed")
        print(f"  {type(exc).__name__}: {exc}", flush=True)
        print("  This is usually a bad value in backend/.env.", flush=True)
        return 1

    frontend_proc = None
    if args.dev and not frontend_dev_ready():
        frontend_proc = start_frontend_dev_server()
    elif args.dev:
        say(OK, "A frontend dev server is already running")

    app_url = f"http://localhost:3000" if args.dev else f"http://{args.host or '127.0.0.1'}:{args.port}"
    if not args.no_browser:
        threading.Thread(
            target=open_browser_when_ready,
            args=(app_url, f"http://127.0.0.1:{args.port}/api/health", 120),
            daemon=True,
        ).start()

    rule(f"Starting Da RoastBox on http://{args.host}:{args.port}")
    if serve_build:
        print(f"  App + API together:  http://{args.host}:{args.port}", flush=True)
    elif args.dev:
        print(f"  App (dev server):    http://localhost:3000", flush=True)
        print(f"  API:                 http://{args.host}:{args.port}", flush=True)
    else:
        print(f"  API only:            http://{args.host}:{args.port}", flush=True)
    print("  Settings console passphrase: roastbox", flush=True)
    print("  Set your API keys any time with:  python install.py", flush=True)
    print("  Press Ctrl-C to stop.\n", flush=True)

    import uvicorn

    try:
        uvicorn.run(
            "server:app", host=args.host, port=args.port,
            reload=args.reload, log_level="info",
        )
    except KeyboardInterrupt:
        say(INFO, "Stopped")
    finally:
        if frontend_proc and frontend_proc.poll() is None:
            say(INFO, "Stopping the frontend dev server")
            frontend_proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
