"""Project-local installer scratch space and actionable disk-full diagnostics.

Only creates installer-owned cache directories. Never deletes user or system data,
purges global package caches, or changes the parent shell's environment.
"""
from __future__ import annotations

import errno
import os
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path

GIB = 1024 ** 3
MIB = 1024 ** 2
INSTALLER_VERSION = "1.2.3"


class DiskSpaceError(RuntimeError):
    """Storage is unavailable; retry after freeing space, not deleting the DB."""


def installation_environment(root: Path, base=None):
    """Redirect pip/venv/Yarn/npm scratch/cache off the Windows profile drive."""
    cache = root / ".cache"
    temporary = cache / "install-temp"
    values = {
        "TEMP": str(temporary), "TMP": str(temporary), "TMPDIR": str(temporary),
        "PIP_CACHE_DIR": str(cache / "pip"), "PIP_NO_CACHE_DIR": "1",
        "YARN_CACHE_FOLDER": str(cache / "yarn"),
        "NPM_CONFIG_CACHE": str(cache / "npm"),
    }
    # Avoid duplicate mixed-case environment names in a Windows child process.
    env = {k: v for k, v in (os.environ if base is None else base).items()
           if k.upper() not in values}
    env.update(values)
    for path in (temporary, cache / "yarn", cache / "npm"):
        path.mkdir(parents=True, exist_ok=True)
    return env


def is_space_error(error):
    if isinstance(error, OSError) and (
        error.errno in (errno.ENOSPC, getattr(errno, "EDQUOT", 122))
        or getattr(error, "winerror", None) in (39, 112, 1295)
    ):
        return True
    text = str(error)
    if isinstance(error, subprocess.CalledProcessError):
        text += str(error.output or "") + str(error.stderr or "")
    text = text.lower()
    return any(marker in text for marker in (
        "no space left on device", "[errno 28]", "enospc", "winerror 112",
        "winerror 39", "not enough space on the disk", "disk quota exceeded",
    ))


def space_message(root: Path, stage, required=None):
    try:
        free = f"{shutil.disk_usage(root).free / GIB:.2f} GiB"
    except OSError:
        free = "unavailable"
    headline = (f"Insufficient disk space for {stage}." if required is not None
                else f"Storage became full during {stage}.")
    needed = f"\nThis step needs at least {required / GIB:.2f} GiB free before it starts." if required is not None else ""
    return (f"{headline}\nProject folder: {root}\nProject-drive free space now: {free}{needed}\n"
            "Python installation temp files and package caches are kept in this project's .cache folder; "
            "pip's duplicate download cache is disabled.\n"
            "For a complete fresh setup, aim for at least 4 GiB free on the project drive. "
            "Windows/system prerequisites also need working space on the system drive.\n"
            "Free space, then run start.bat again; partially installed packages can be resumed. "
            "Do not delete .data/mongo, backend/local_storage or any .env files. "
            "No database, media, configuration or global cache was deleted by this check.")


def require_space(root: Path, amount, stage):
    if shutil.disk_usage(root).free < amount:
        raise DiskSpaceError(space_message(root, stage, amount))


def announce_storage(root: Path):
    print(f"Installer v{INSTALLER_VERSION}: project-local temp/cache; pip download cache disabled.", flush=True)
    print(f"Temporary files: {root / '.cache' / 'install-temp'}", flush=True)
    print(f"Yarn/npm caches: {root / '.cache'}", flush=True)
    print(f"Project-drive free space: {shutil.disk_usage(root).free / GIB:.2f} GiB", flush=True)


def run_pip_install(command, *, cwd, env, root):
    """Stream pip output normally; recognize its actual disk-full error on exit.

    Kept separate from long-running server launches so signal/console behavior for
    the user's web servers is unchanged. Only the last 100 lines are kept in RAM.
    """
    tail = deque(maxlen=100)
    with subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace") as process:
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            tail.append(line)
        result = process.wait()
    if result:
        output = "".join(tail)
        if is_space_error(output):
            raise DiskSpaceError(space_message(root, "Python package installation"))
        raise subprocess.CalledProcessError(result, command, output=output)
