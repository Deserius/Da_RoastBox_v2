"""Operator-entered provider credentials, stored encrypted and applied at runtime.

The environment stays authoritative: a non-empty environment value always wins,
because that is what an operator declared at deploy time. A value saved here only
fills a gap, which is what makes it safe to enable in a disposable preview.

Every getter is defensive. A provider call must never fail because the override
lookup failed, so a database error degrades to "no override" and the caller keeps
whatever the environment provided.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from crypto_utils import decrypt, encrypt
from db import runtime_settings_collection

log = logging.getLogger(__name__)


def _env(key: str):
    """Read the deploy-time value for one field without importing it eagerly.

    ``config`` is imported here rather than at module scope because
    ``config`` must stay importable on its own; the lookup is a dict access,
    so doing it per call costs nothing.
    """
    import config

    return getattr(config, key, None)


def _explicit_env(key: str) -> bool:
    """True when the operator declared this value in the environment.

    Some settings carry a built-in default (for example
    ``ROAST_WRITER_PROVIDER`` defaults to ``openrouter``), so comparing
    against the config attribute cannot tell "declared" from "defaulted".
    Only an explicitly exported variable outranks the console.
    """
    import os

    return bool((os.environ.get(key) or "").strip())


# field key -> human label. Order drives the console UI.
SECRET_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("OPENAI_API_KEY", "OpenAI API key"),
    ("OPENROUTER_API_KEY", "OpenRouter API key"),
    ("ELEVENLABS_API_KEY", "ElevenLabs API key"),
    ("EMERGENT_LLM_KEY", "Emergent LLM gateway key"),
    ("STRIPE_API_KEY", "Stripe secret key"),
    ("STRIPE_WEBHOOK_SECRET", "Stripe webhook signing secret"),
    ("BLOB_READ_WRITE_TOKEN", "Vercel Blob read/write token"),
)

SECRET_KEYS = tuple(key for key, _ in SECRET_FIELDS)
_FIELD_LABELS = dict(SECRET_FIELDS)

# Non-secret switches an operator may flip from the console.
SETTING_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("AI_DEFAULT_PROVIDER", "AI provider (openai | emergent)"),
    ("ROAST_WRITER_PROVIDER", "Writer provider (openrouter | existing)"),
    ("STORAGE_BACKEND", "Media storage (emergent | local | vercel_blob)"),
)
SETTING_KEYS = tuple(key for key, _ in SETTING_FIELDS)

_ALLOWED: Dict[str, Tuple[str, ...]] = {
    "AI_DEFAULT_PROVIDER": ("openai", "emergent"),
    "ROAST_WRITER_PROVIDER": ("openrouter", "existing"),
    "STORAGE_BACKEND": ("emergent", "local", "vercel_blob"),
}

_DOC_ID = "provider_credentials"

# In-process cache so a hot provider path does not hit Mongo on every call.
# Busted on every write, and cheap enough to rebuild that a stale entry is
# corrected on the next request.
_cache: Dict[str, Any] = {"secret": {}, "setting": {}, "loaded": False}


def _invalidate() -> None:
    _cache["loaded"] = False


async def _load() -> None:
    """Refresh the cache from Mongo. Any failure leaves the previous snapshot."""
    if _cache["loaded"]:
        return
    try:
        doc = await runtime_settings_collection.find_one({"_id": _DOC_ID})
    except Exception:  # pragma: no cover - defensive: never break a provider call
        log.warning("Runtime settings unavailable; falling back to environment", exc_info=True)
        return
    secret: Dict[str, str] = {}
    setting: Dict[str, str] = {}
    if isinstance(doc, dict):
        for key in SECRET_KEYS:
            token = doc.get(key)
            if not isinstance(token, str) or not token:
                continue
            try:
                plain = decrypt(token)
            except Exception:
                # A rotated JWT_SECRET makes old ciphertext unreadable. Treat it
                # as "not set" rather than crashing, and say so once in the log.
                log.warning("Stored %s could not be decrypted; ignoring it", key)
                continue
            if plain:
                secret[key] = plain
        for key in SETTING_KEYS:
            value = doc.get(key)
            if isinstance(value, str) and value.strip():
                setting[key] = value.strip().lower()
    _cache["secret"], _cache["setting"], _cache["loaded"] = secret, setting, True


def clear_cache() -> None:
    """Public hook so tests and the seed path can force a reload."""
    _invalidate()


async def secret(key: str) -> str:
    """Effective secret: the environment value if present, else the stored one."""
    env_value = _env(key)
    if isinstance(env_value, str) and env_value.strip():
        return env_value
    await _load()
    return _cache["secret"].get(key, "")


async def secret_map(keys: Iterable[str]) -> Dict[str, str]:
    """Batch form of :func:`secret` for callers needing several values."""
    return {key: await secret(key) for key in keys}


def secret_cached(key: str) -> str:
    """Synchronous effective secret for hot paths that cannot await.

    Returns the environment value when set, else the last known console value.
    The cache is hydrated at startup and updated on every write, so a value
    entered in the console is live before the next provider call.
    """
    env_value = _env(key)
    if isinstance(env_value, str) and env_value.strip():
        return env_value
    return _cache["secret"].get(key, "")


def setting_cached(key: str, default: Optional[str] = None) -> Optional[str]:
    """Synchronous counterpart to :func:`setting`."""
    env_value = _env(key)
    if isinstance(env_value, str) and env_value.strip():
        return env_value.strip().lower()
    return _cache["setting"].get(key, default)


async def hydrate() -> None:
    """Load stored values once at startup so sync callers see them immediately."""
    _invalidate()
    await _load()
    log.info("Runtime settings hydrated: %d secret(s), %d setting(s)",
             len(_cache["secret"]), len(_cache["setting"]))



async def setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Effective non-secret setting, mirroring :func:`secret` precedence."""
    env_value = _env(key)
    if isinstance(env_value, str) and env_value.strip():
        return env_value.strip().lower()
    await _load()
    return _cache["setting"].get(key, default)


async def effective_snapshot() -> Dict[str, Dict[str, Any]]:
    """Describe every managed field for the console.

    Secrets are reported as a boolean plus whether they came from the
    environment or from the console. Plaintext never leaves the backend.
    """
    await _load()
    secrets_out: Dict[str, Any] = {}
    for key, label in SECRET_FIELDS:
        from_env = _explicit_env(key)
        stored = _cache["secret"].get(key, "")
        secrets_out[key] = {
            "label": label,
            "configured": from_env or bool(stored),
            "source": "environment" if from_env else ("console" if stored else None),
            "editable": not from_env,
            "hint": _mask(stored) if stored and not from_env else None,
        }
    settings_out: Dict[str, Any] = {}
    for key, label in SETTING_FIELDS:
        from_env = _explicit_env(key)
        settings_out[key] = {
            "label": label,
            "value": ((_env(key) or "").strip().lower() if from_env else _cache["setting"].get(key)),
            "source": "environment" if from_env else ("console" if key in _cache["setting"] else None),
            "editable": not from_env,
            "choices": list(_ALLOWED.get(key, ())),
        }
    return {"secrets": secrets_out, "settings": settings_out}


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"


async def save(payload: Dict[str, Optional[str]]) -> List[str]:
    """Persist supplied values. Blank string clears a console-stored value."""
    update: Dict[str, Any] = {}
    problem = None
    for key in SECRET_KEYS:
        if key not in payload:
            continue
        raw = payload.get(key)
        if raw is None:
            continue
        value = raw.strip()
        if not value:
            update[key] = None
            continue
        if _explicit_env(key):
            # Saving here would be silently ignored, so refuse rather than
            # leaving the operator believing they rotated a live credential.
            problem = f"{_FIELD_LABELS.get(key, key)} is set by the environment and takes precedence."
            continue
        update[key] = encrypt(value)
    for key in SETTING_KEYS:
        if key not in payload:
            continue
        raw = payload.get(key)
        if raw is None:
            continue
        value = raw.strip().lower()
        if not value:
            update[key] = None
            continue
        if value not in _ALLOWED.get(key, ()):
            problem = f"{key} must be one of {', '.join(_ALLOWED.get(key, ()))}."
            continue
        if _explicit_env(key):
            problem = f"{key} is set by the environment and takes precedence."
            continue
        update[key] = value

    if not update:
        if problem:
            raise ValueError(problem)
        return []

    await runtime_settings_collection.update_one(
        {"_id": _DOC_ID}, {"$set": update}, upsert=True
    )
    _invalidate()
    return sorted(update.keys())


async def clear(keys: Optional[Iterable[str]] = None) -> int:
    """Remove console-stored values. ``None`` clears every console value."""
    await _load()
    targets = [k for k in (keys if keys is not None else list(SECRET_KEYS) + list(SETTING_KEYS))
               if k in SECRET_KEYS or k in SETTING_KEYS]
    if not targets:
        return 0
    result = await runtime_settings_collection.update_one(
        {"_id": _DOC_ID}, {"$set": {key: None for key in targets}}, upsert=True
    )
    _invalidate()
    return len(targets) if result.matched_count or result.upserted_id else 0
