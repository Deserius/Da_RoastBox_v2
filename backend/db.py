"""Database connection and collections.

Da RoastBox needs no database server to be installed. By default
(``MONGO_URL`` unset, blank, or ``embedded``) it runs against a built-in,
zero-install database: a real MongoDB-compatible engine (mongomock) that
lives in this process and is snapshotted to a single file under
``backend/local_storage/`` so data survives restarts. Every route in this
project talks to it through the exact same Motor-style async API it would
use against a real server, so nothing else in the codebase needs to know
the difference.

Point ``MONGO_URL`` at a real ``mongodb://`` or ``mongodb+srv://`` connection
string (for example a free MongoDB Atlas cluster, or a local `mongod`) to use
a real MongoDB server instead — useful for multi-device sync or large
datasets. That path is unchanged from before.
"""
from __future__ import annotations

import atexit
import logging
import pickle
import threading
from pathlib import Path

from config import MONGO_URL, DB_NAME

log = logging.getLogger(__name__)

EMBEDDED_MODE = not MONGO_URL.strip().lower().startswith(("mongodb://", "mongodb+srv://"))

_snapshot_lock = threading.Lock()
_snapshot_path: "Path | None" = None
_store = None  # mongomock DatabaseStore, only set in embedded mode

if EMBEDDED_MODE:
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    db = client[DB_NAME]
    _store = db.delegate._store  # mongomock.store.DatabaseStore (in-process, mutable)

    ROOT_DIR = Path(__file__).resolve().parent
    _snapshot_path = ROOT_DIR / "local_storage" / "roastbox_embedded_db.pkl"
    _snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_snapshot() -> None:
        if not _snapshot_path.exists():
            return
        try:
            with open(_snapshot_path, "rb") as fh:
                snapshot = pickle.load(fh)
        except Exception:
            log.exception(
                "Could not read the local database file (%s); starting with an "
                "empty database. The previous file is left in place in case it "
                "can be recovered by hand.", _snapshot_path,
            )
            return
        for name, docs in snapshot.items():
            coll_store = _store[name]
            coll_store.create()
            for doc in docs:
                coll_store._documents[doc["_id"]] = doc
        log.info("Loaded local database from %s (%d collection(s))", _snapshot_path, len(snapshot))

    def save_snapshot() -> None:
        """Write every document to disk. Safe to call often; it is a plain file write."""
        if _store is None:
            return
        with _snapshot_lock:
            try:
                snapshot = {
                    name: list(_store[name]._documents.values())
                    for name in _store.list_created_collection_names()
                }
                tmp_path = _snapshot_path.with_suffix(".tmp")
                with open(tmp_path, "wb") as fh:
                    pickle.dump(snapshot, fh, protocol=pickle.HIGHEST_PROTOCOL)
                tmp_path.replace(_snapshot_path)
            except Exception:
                log.exception("Could not save the local database to %s", _snapshot_path)

    _load_snapshot()
    atexit.register(save_snapshot)

else:
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    def save_snapshot() -> None:  # pragma: no cover - no-op against a real server
        pass


_autosave_task = None


async def start_autosave(interval_seconds: int = 20) -> None:
    """Periodically flush the embedded database to disk. No-op for a real server."""
    global _autosave_task
    if not EMBEDDED_MODE or _autosave_task is not None:
        return
    import asyncio

    async def _loop():
        while True:
            await asyncio.sleep(interval_seconds)
            await asyncio.to_thread(save_snapshot)

    _autosave_task = asyncio.create_task(_loop())


async def stop_autosave() -> None:
    import asyncio

    global _autosave_task
    if _autosave_task is not None:
        _autosave_task.cancel()
        try:
            await _autosave_task
        except (asyncio.CancelledError, Exception):
            pass
        _autosave_task = None
    await _flush_async()


async def _flush_async() -> None:
    import asyncio

    await asyncio.to_thread(save_snapshot)


users_collection = db["users"]
sessions_collection = db["sessions"]
roasts_collection = db["roasts"]
credits_collection = db["credit_transactions"]
payments_collection = db["payment_transactions"]
voice_previews_collection = db["voice_previews"]
# Additional punchline samples live separately so the original one-per-persona
# preview cache and its existing unique index remain compatible.
voice_preview_samples_collection = db["voice_preview_samples"]
voice_preview_leases_collection = db["voice_preview_leases"]
reels_collection = db["reels"]
preview_usage_collection = db["preview_hosted_usage"]
email_credentials_collection = db["email_credentials"]
email_tokens_collection = db["email_tokens"]
email_rate_limits_collection = db["email_auth_rate_limits"]
# Operator-entered provider credentials. Values are Fernet-encrypted; the
# environment always wins when it already defines a non-empty value.
runtime_settings_collection = db["runtime_settings"]


async def ensure_indexes():
    await users_collection.create_index("id", unique=True)
    await users_collection.create_index("email", unique=True)
    await sessions_collection.create_index("session_token", unique=True)
    await email_credentials_collection.create_index("email", unique=True)
    await email_credentials_collection.create_index("user_id", unique=True)
    await email_tokens_collection.create_index("expires_at", expireAfterSeconds=0)
    await email_tokens_collection.create_index([("email", 1), ("purpose", 1)])
    await email_rate_limits_collection.create_index("expires_at", expireAfterSeconds=0)
    await roasts_collection.create_index([("user_id", 1), ("created_at", -1)])
    await roasts_collection.create_index([("billing_version", 1), ("billing_state", 1), ("billing_staged_at", 1)])
    await roasts_collection.create_index([("user_id", 1), ("transcript.audio_url", 1)])
    await payments_collection.create_index("stripe_session_id", unique=True)
    await payments_collection.create_index([("user_id", 1), ("created_at", -1)])
    await credits_collection.create_index("user_id")
    await credits_collection.create_index([("user_id", 1), ("created_at", -1)])
    await roasts_collection.create_index("share_id", unique=True, sparse=True)
    await voice_previews_collection.create_index("persona_id", unique=True)
    await voice_preview_samples_collection.create_index([("persona_id", 1), ("sample", 1)], unique=True)
    await voice_preview_samples_collection.create_index("filename")
    await voice_preview_leases_collection.create_index("expires_at", expireAfterSeconds=0)
    await reels_collection.create_index("id", unique=True)
    await reels_collection.create_index("roast_id")
    await reels_collection.create_index([("status", 1), ("refund_pending", 1)])
