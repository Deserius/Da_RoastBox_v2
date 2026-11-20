"""Generated media storage.

The original Emergent Object Storage integration is retained as the default.
An explicitly selected local backend supports development and independent
installations; its files must be backed up separately in production.
"""
import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import requests

from services.runtime_settings import secret_cached
from config import (
    INTEGRATION_PROXY_URL, AUDIO_DIR,
    STORAGE_BACKEND, LOCAL_STORAGE_DIR,
)

log = logging.getLogger(__name__)
STORAGE_URL = INTEGRATION_PROXY_URL.rstrip("/") + "/objstore/api/v1/storage"
APP_PREFIX = "da-roastbox"
_storage_key: Optional[str] = None


def _init(force: bool = False) -> str:
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    emergent_key = secret_cached("EMERGENT_LLM_KEY")
    if not emergent_key:
        raise RuntimeError("EMERGENT_LLM_KEY is required for Emergent Object Storage")
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": emergent_key}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _put(path: str, data: bytes, content_type: str) -> dict:
    for attempt in range(2):
        resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                            headers={"X-Storage-Key": _init(force=attempt > 0), "Content-Type": content_type},
                            data=data, timeout=120)
        if resp.status_code == 404 and attempt == 0:
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("storage put failed")


def _get(path: str) -> Tuple[bytes, str]:
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": _init()}, timeout=60)
    if resp.status_code == 404:
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": _init(force=True)}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "audio/mpeg")


def _local_path(path: str) -> Path:
    root = LOCAL_STORAGE_DIR.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError("Invalid storage path")
    return target


def _local_put(path: str, data: bytes) -> None:
    target = _local_path(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Atomic replacement avoids readers seeing a partially written image or video.
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(data)
        os.replace(tmp_path, target)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _local_get(path: str) -> bytes:
    return _local_path(path).read_bytes()


def audio_path(filename: str) -> str:
    return f"{APP_PREFIX}/audio/{filename}"


async def init_storage() -> bool:
    try:
        if STORAGE_BACKEND == "local":
            LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        else:
            await asyncio.to_thread(_init)
        return True
    except Exception as e:
        log.error("Object storage init failed: %s", e)
        return False


async def save_audio(filename: str, data: bytes) -> None:
    """Write a local read cache and a durable copy in the selected backend."""
    if Path(filename).name != filename:
        raise ValueError("Invalid audio filename")
    (AUDIO_DIR / filename).write_bytes(data)
    try:
        if STORAGE_BACKEND == "local":
            await asyncio.to_thread(_local_put, audio_path(filename), data)
        else:
            await asyncio.to_thread(_put, audio_path(filename), data, "audio/mpeg")
    except Exception as e:
        if STORAGE_BACKEND == "local":
            raise  # A local durable-storage failure must not silently create a paid, temporary result.
        log.warning("Object storage upload failed for %s: %s (local copy kept)", filename, e)


async def put_blob(path: str, data: bytes, content_type: str) -> None:
    key = f"{APP_PREFIX}/{path}"
    if STORAGE_BACKEND == "local":
        await asyncio.to_thread(_local_put, key, data)
    else:
        await asyncio.to_thread(_put, key, data, content_type)


async def get_blob(path: str) -> Optional[bytes]:
    try:
        key = f"{APP_PREFIX}/{path}"
        if STORAGE_BACKEND == "local":
            return await asyncio.to_thread(_local_get, key)
        data, _ = await asyncio.to_thread(_get, key)
        return data
    except Exception:
        return None


async def load_audio(filename: str) -> Optional[bytes]:
    if Path(filename).name != filename:
        return None
    local = AUDIO_DIR / filename
    if local.exists():
        return local.read_bytes()
    try:
        if STORAGE_BACKEND == "local":
            data = await asyncio.to_thread(_local_get, audio_path(filename))
        else:
            data, _ = await asyncio.to_thread(_get, audio_path(filename))
    except Exception:
        return None
    local.write_bytes(data)
    return data
