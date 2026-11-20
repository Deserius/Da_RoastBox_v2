"""Standard-library-only helpers shared by bootstrap and local launcher."""
from __future__ import annotations

import json
import os
import socket
import sys
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

NODE_VERSION = "22.23.4"
MONGO_VERSION = "8.0.34"
YARN_VERSION = "1.22.22"
IS_WINDOWS = sys.platform == "win32"
# Corporate HTTP proxy settings must not send localhost readiness checks away.
_LOCAL_HTTP = build_opener(ProxyHandler({}))


def port_number(value, name="Port"):
    try:
        number = int(value)
    except (ValueError, TypeError):
        raise RuntimeError(f"{name} must be a number between 1 and 65535.") from None
    if not 1 <= number <= 65535:
        raise RuntimeError(f"{name} must be between 1 and 65535.")
    return number


def occupied(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def read_url(url, *, timeout=1.0, limit=65536):
    with _LOCAL_HTTP.open(url, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError("Service is not ready")
        return response.read(limit)


def api_ready(port):
    try:
        base = f"http://127.0.0.1:{port}"
        health = json.loads(read_url(base + "/api/health"))
        identity = json.loads(read_url(base + "/api/"))
        return health.get("status") == "ok" and identity.get("message") == "Da RoastBox API live"
    except (URLError, OSError, ValueError, TypeError, AttributeError):
        return False


def app_ready(ui_port, api_port):
    if not api_ready(api_port):
        return False
    try:
        base = f"http://127.0.0.1:{ui_port}"
        health = json.loads(read_url(base + "/api/health"))
        html = read_url(base + "/").lower()
        return health.get("status") == "ok" and b"<html" in html and b"da roastbox" in html
    except (URLError, OSError, ValueError, TypeError, AttributeError):
        return False


def open_default_browser(url):
    """ShellExecute on Windows respects the user's registered default browser."""
    try:
        if IS_WINDOWS:
            os.startfile(url)
            return True
        if webbrowser.open(url, new=2, autoraise=True):
            return True
    except Exception:
        pass
    print(f"Automatic browser launch was unavailable. Open {url} in your browser.", flush=True)
    return False


class AlreadyRunning(RuntimeError):
    pass


class ProjectLock:
    """OS-released file lock, not a PID probe or a kill command.

    A stale on-disk lock file is harmless after a crash. No process is killed to
    acquire this lock. Windows lock descriptors are not inherited by children.
    """
    def __init__(self, path):
        self.path = Path(path)
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        if self.file.seek(0, 2) == 0:
            self.file.write(b"\0")
            self.file.flush()
        self.file.seek(0)
        try:
            if IS_WINDOWS:
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            raise AlreadyRunning("Another setup or launcher window is already running. Keep that window open; no duplicate installation was started.") from None
        return self

    def __exit__(self, *_args):
        if self.file is not None:
            try:
                self.file.seek(0)
                if IS_WINDOWS:
                    import msvcrt
                    msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            finally:
                self.file.close()
                self.file = None
