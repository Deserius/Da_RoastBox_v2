#!/usr/bin/env python3
"""Run the API on 8001, frontend on 3000, then open the default browser.

The one-click installer prepares dependencies first. Ctrl+C stops only the web
processes created here. MongoDB is detached, reused, and NEVER terminated here.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pymongo import MongoClient

from dependency_discovery import discover
from prepared_runtime import prepared_tool

from launcher_common import (NODE_VERSION, MONGO_VERSION, IS_WINDOWS, AlreadyRunning,
                             ProjectLock, api_ready, app_ready, occupied,
                             open_default_browser, port_number)

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".cache" / "local-tools"
NODE = Path(os.environ.get("ROASTBOX_NODE_EXE", "")) if os.environ.get("ROASTBOX_NODE_EXE") else (prepared_tool(ROOT, "node") if IS_WINDOWS else None)
NODE = NODE or TOOLS / f"node-{NODE_VERSION}" / ("node.exe" if IS_WINDOWS else "node")


def mongo_executable():
    configured = os.environ.get("ROASTBOX_MONGOD_EXE")
    if configured and Path(configured).is_file():
        return Path(configured)
    if IS_WINDOWS:
        bundled = prepared_tool(ROOT, "mongod")
        if bundled:
            return bundled
        if os.name == "nt":
            installed = discover("mongod")
            if installed:
                return installed
    base = TOOLS / f"mongodb-{MONGO_VERSION}"
    name = "mongod.exe" if IS_WINDOWS else "mongod"
    return next((p for p in (base / name, base / "bin" / name) if p.is_file()), base / name)


def ping(uri):
    try:
        with MongoClient(uri, serverSelectionTimeoutMS=800, connectTimeoutMS=800) as client:
            client.admin.command("ping")
        return True
    except Exception:
        return False


def local_mongo_port(uri):
    # Never bootstrap an unauthenticated database for an Atlas/remote/auth URL.
    try:
        parsed = urlsplit(uri)
        if (parsed.scheme != "mongodb" or parsed.hostname not in ("localhost", "127.0.0.1") or
                parsed.username or parsed.password or parsed.query or parsed.fragment or
                parsed.path not in ("", "/") or "," in parsed.netloc):
            return None
        return parsed.port or 27017
    except ValueError:
        return None


def spawn(command, *, detached=False, **kwargs):
    if IS_WINDOWS:
        flags = subprocess.CREATE_NEW_PROCESS_GROUP
        if detached:
            flags |= subprocess.DETACHED_PROCESS
        options = {"creationflags": flags}
    else:
        options = {"start_new_session": True}
    return subprocess.Popen([str(x) for x in command], **options, **kwargs)


def stop_web_process(process):
    """Only call for our own API/frontend children, never for a database."""
    if not process or process.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        try:
            if IS_WINDOWS:
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass


# Backwards-compatible name for existing local test/import helpers.
stop = stop_web_process


def ensure_database(uri, *, external_only=False):
    if ping(uri):
        print("[1/3] Using the configured, already-running MongoDB. It will be left running.", flush=True)
        return
    port = local_mongo_port(uri)
    if external_only or port is None:
        raise RuntimeError("Configured MongoDB is not reachable. Start that database or check MONGO_URL and network access. Its credentials are not printed or changed.")
    if occupied(port):
        raise RuntimeError(f"Database port {port} is occupied but MongoDB did not answer. No process was stopped and no data was removed.")
    mongo = mongo_executable()
    if not mongo.is_file():
        raise RuntimeError("Portable MongoDB is missing. Run start.bat again without --skip-mongodb, or configure an existing database.")
    data = ROOT / ".data" / ("mongo" if port == 27017 else f"mongo-{port}")
    data.mkdir(parents=True, exist_ok=True)
    log_path = ROOT / ".data" / f"mongo-{port}.log"
    print(f"[1/3] Starting private MongoDB; preserving data at {data}", flush=True)
    # MongoDB is deliberately NOT added to the web-process cleanup list. On
    # Windows it is detached from the batch window, so closing it cannot kill DB.
    with log_path.open("a", encoding="utf-8") as log:
        process = spawn([mongo, "--dbpath", data, "--bind_ip", "127.0.0.1", "--port", str(port), "--quiet"],
                        detached=True, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"MongoDB exited ({process.returncode}). Check {log_path}. Windows may require the Microsoft C++ runtime. No database files were deleted.")
        if ping(uri):
            print("MongoDB is ready and will remain running when the web app stops.", flush=True)
            return
        time.sleep(0.4)
    raise RuntimeError(f"MongoDB is still starting. Check {log_path} and retry; it was not terminated.")


def run_local(*, ui_port=3000, api_port=8001, no_browser=False, external_db=False, startup_timeout=90):
    ui_port, api_port = port_number(ui_port, "Frontend port"), port_number(api_port, "API port")
    if ui_port == api_port:
        raise RuntimeError("Frontend and API ports must differ (defaults: 3000 and 8001).")
    url = f"http://127.0.0.1:{ui_port}"
    if app_ready(ui_port, api_port):
        print(f"Da RoastBox is already running at {url}. Reusing it without changing dependencies or data.", flush=True)
        if not no_browser:
            open_default_browser(url)
        return
    for label, port in (("Frontend", ui_port), ("API", api_port)):
        if occupied(port):
            raise RuntimeError(f"{label} port {port} is already in use. Close the conflicting web server or select another port; the launcher will not kill it.")
    if not NODE.is_file():
        raise RuntimeError("Project-local Node is missing. Double-click start.bat to install it.")
    if not (ROOT / "frontend/build/index.html").is_file():
        raise RuntimeError("Frontend build is missing. Double-click start.bat to install and build it.")
    uri = os.environ.get("MONGO_URL", "")
    if not uri:
        raise RuntimeError("Set MONGO_URL in backend/.env before starting.")
    web_processes = []
    try:
        ensure_database(uri, external_only=external_db)
        env = os.environ.copy()
        env.pop("FRONTEND_BUILD_DIR", None)
        print(f"[2/3] Starting API on 127.0.0.1:{api_port} ...", flush=True)
        api = spawn([sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1",
                     "--port", str(api_port), "--workers", "1"], cwd=ROOT / "backend", env=env)
        web_processes.append(api)
        # Browser-facing code uses same-origin /api. Only this Node proxy calls
        # 127.0.0.1:8001; no browser-side localhost backend URL is baked in.
        frontend_env = {**env, "PORT": str(ui_port), "API_PROXY_TARGET": f"http://127.0.0.1:{api_port}"}
        frontend_env.setdefault("HOST", "0.0.0.0")
        print(f"[3/3] Starting frontend at {url} ...", flush=True)
        frontend = spawn([NODE, ROOT / "scripts/serve-preview.cjs"], cwd=ROOT, env=frontend_env)
        web_processes.append(frontend)
        deadline = time.monotonic() + startup_timeout
        while time.monotonic() < deadline:
            for label, process in (("API", api), ("Frontend", frontend)):
                if process.poll() is not None:
                    raise RuntimeError(f"{label} exited ({process.returncode}). Review the messages above. MongoDB was not stopped.")
            if app_ready(ui_port, api_port):
                break
            time.sleep(0.4)
        else:
            raise RuntimeError(f"The app did not become ready within {startup_timeout} seconds. Review the messages above.")
        print(f"\nDa RoastBox is ready: {url}\nAPI: http://127.0.0.1:{api_port}\nKeep this window open. Ctrl+C stops the web servers only; MongoDB stays running.\n", flush=True)
        if not no_browser:
            open_default_browser(url)
        while True:
            for label, process in (("API", api), ("Frontend", frontend)):
                if process.poll() is not None:
                    raise RuntimeError(f"{label} stopped ({process.returncode}). MongoDB was left running.")
            time.sleep(0.5)
    finally:
        for process in reversed(web_processes):
            stop_web_process(process)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="Run without opening a browser (headless/automated use)")
    parser.add_argument("--port", type=int, help="Frontend port (default PORT or 3000)")
    parser.add_argument("--api-port", type=int, help="Backend port (default API_PORT or 8001)")
    parser.add_argument("--external-db", action="store_true", help="Do not bootstrap a portable database")
    args = parser.parse_args(argv)
    def shutdown(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    if not (ROOT / "backend/.env").is_file() or not (ROOT / "frontend/.env").is_file():
        raise RuntimeError("Configuration is missing. Double-click start.bat to prepare it without overwriting existing files.")
    load_dotenv(ROOT / "backend/.env")
    ui_port = args.port if args.port is not None else os.environ.get("PORT", "3000")
    api_port = args.api_port if args.api_port is not None else os.environ.get("API_PORT", "8001")
    with ProjectLock(ROOT / ".cache" / "app.lock"):
        run_local(ui_port=ui_port, api_port=api_port, no_browser=args.no_browser, external_db=args.external_db)


if __name__ == "__main__":
    try:
        main()
    except AlreadyRunning as exc:
        print(str(exc), flush=True)
    except KeyboardInterrupt:
        print("\nWeb servers stopped. MongoDB and all saved data were left intact.", flush=True)
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"Could not start: {exc}\nSee docs/LOCAL_INSTALL.md.", file=sys.stderr)
        raise SystemExit(1)
