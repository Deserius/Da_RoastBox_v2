"""Bounded dependency discovery. Never recursively scan drives or read credentials."""
from __future__ import annotations
import ctypes
import os
from pathlib import Path
import re
import shutil
import subprocess

_NAMES = {"node": "node.exe", "mongod": "mongod.exe", "ffmpeg": "ffmpeg.exe"}
_OVERRIDES = {"node": "ROASTBOX_NODE_EXE", "mongod": "ROASTBOX_MONGOD_EXE", "ffmpeg": "IMAGEIO_FFMPEG_EXE"}


def fixed_drives():
    if os.name != "nt":
        return []
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    return [Path(f"{chr(65 + index)}:/") for index in range(26)
            if mask & (1 << index) and ctypes.windll.kernel32.GetDriveTypeW(f"{chr(65 + index)}:\\") == 3]


def candidates(kind, *, env=None, drives=None):
    if kind not in _NAMES:
        raise ValueError("Unknown dependency")
    env = os.environ if env is None else env
    result = []
    if env.get(_OVERRIDES[kind]):
        result.append(Path(env[_OVERRIDES[kind]]))
    found = shutil.which(_NAMES[kind], path=env.get("PATH", ""))
    if found:
        result.append(Path(found))
    if os.name == "nt":
        import winreg
        keys = {"node": (r"SOFTWARE\Node.js", "InstallPath"),
                "mongod": (r"SOFTWARE\MongoDB\Server\8.0", "InstallPath")}
        if kind in keys:
            key, value = keys[kind]
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        folder = Path(winreg.QueryValueEx(handle, value)[0])
                        result.append(folder / ("bin" if kind == "mongod" else "") / _NAMES[kind])
                except OSError:
                    pass
    for drive in (fixed_drives() if drives is None else drives):
        drive = Path(drive)
        relative = {
            "node": ("Program Files/nodejs/node.exe", "Tools/nodejs/node.exe", "nodejs/node.exe"),
            "mongod": ("Program Files/MongoDB/Server/8.0/bin/mongod.exe", "Tools/MongoDB/bin/mongod.exe"),
            "ffmpeg": ("Tools/ffmpeg/bin/ffmpeg.exe", "ffmpeg/bin/ffmpeg.exe"),
        }[kind]
        result.extend(drive / name for name in relative)
    seen = set()
    for path in result:
        key = str(path).casefold()
        if key not in seen and path.is_file():
            seen.add(key)
            yield path


def discover(kind, *, expected_node="22.23.4", env=None, drives=None):
    for path in candidates(kind, env=env, drives=drives):
        try:
            output = subprocess.run([str(path), "--version" if kind != "ffmpeg" else "-version"],
                                    capture_output=True, text=True, timeout=8, check=False)
            if output.returncode:
                continue
            text = output.stdout + output.stderr
            if kind == "node" and text.strip().removeprefix("v") != expected_node:
                continue  # Reproducible compatibility pin, not arbitrary global latest.
            if kind == "mongod" and not re.search(r"\bv8\.0\.\d+\b", text):
                continue
            if kind == "ffmpeg" and "ffmpeg version" not in text:
                continue
            return path
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            continue
    return None
