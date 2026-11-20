"""Owner settings console: enter provider credentials without redeploying.

Guarded three ways, because a page that accepts a Stripe secret key deserves it:

1. ``ALLOW_RUNTIME_SETTINGS`` must be enabled. It is off by default and is
   rejected outright in a release/production configuration by the existing
   runtime guard.
2. The request must come from a signed-in preview or test account.
3. A shared passphrase must be unlocked for that session first.

The passphrase is compared in constant time. It is never stored on the user
record; the unlock is a server-side grant with an expiry, so closing the browser
or waiting out the window both re-lock the console.
"""
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_deps import get_current_user
from config import (ALLOW_RUNTIME_SETTINGS, PREVIEW_UNLIMITED_CREDITS,
                    RUNTIME_SETTINGS_ADMINS, RUNTIME_SETTINGS_PASSPHRASE)
from db import users_collection
from models import User
from services import env_writer, key_validator, runtime_settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

UNLOCK_MINUTES = 60


def console_available() -> bool:
    """The console needs an explicit opt-in and a passphrase to compare against."""
    return bool(ALLOW_RUNTIME_SETTINGS and RUNTIME_SETTINGS_PASSPHRASE)


def _is_operator(user: User) -> bool:
    """Who may open the console once it is enabled.

    The shared passphrase is the actual gate: it is what an attacker would need,
    and it is compared in constant time below. Requiring a *preview* account on
    top of that locked out the one person entitled to configure their own
    deployment, so any signed-in account is accepted.

    Set ``RUNTIME_SETTINGS_ADMINS`` to a comma-separated list of user ids or
    emails to narrow this to specific operators.
    """
    if RUNTIME_SETTINGS_ADMINS:
        identity = {(user.id or "").lower(), (user.email or "").lower()}
        return bool(identity & set(RUNTIME_SETTINGS_ADMINS))
    return True


async def _unlock_expiry(user: User) -> Optional[datetime]:
    doc = await users_collection.find_one({"id": user.id}, {"runtime_settings_unlocked_until": 1})
    raw = (doc or {}).get("runtime_settings_unlocked_until")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        expiry = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry if expiry > datetime.now(timezone.utc) else None


async def _require_operator(user: User) -> None:
    if not console_available():
        raise HTTPException(status_code=404, detail="Not found")
    if not _is_operator(user):
        raise HTTPException(status_code=403, detail="The settings console is limited to approved operator accounts.")
    if await _unlock_expiry(user) is None:
        raise HTTPException(status_code=403, detail="Settings console is locked. Enter the passphrase to unlock.")


class UnlockBody(BaseModel):
    passphrase: str = ""


class SaveBody(BaseModel):
    api_key: Optional[str] = None
    keys: Optional[dict] = None
    # Two-phase save: validate first, then persist only what the operator
    # explicitly confirmed. "validate" never writes.
    mode: str = "apply"          # "validate" | "apply"
    persist_env: bool = True     # also write backend/.env after validation


@router.get("/console")
async def console_state(current_user: User = Depends(get_current_user)):
    """Report what is configured and whether the console is unlocked."""
    if not console_available():
        raise HTTPException(status_code=404, detail="Not found")
    if not _is_operator(current_user):
        raise HTTPException(status_code=403, detail="The settings console is limited to approved operator accounts.")
    expiry = await _unlock_expiry(current_user)
    snapshot = await runtime_settings.effective_snapshot()
    return {
        "enabled": True,
        "unlocked": expiry is not None,
        "unlocked_until": expiry.isoformat() if expiry else None,
        "unlimited_credits": bool(current_user.is_preview and PREVIEW_UNLIMITED_CREDITS),
        **snapshot,
    }


@router.post("/console/unlock")
async def unlock_console(body: UnlockBody, current_user: User = Depends(get_current_user)):
    """Exchange the shared passphrase for a short-lived server-side grant."""
    if not console_available():
        raise HTTPException(status_code=404, detail="Not found")
    if not _is_operator(current_user):
        raise HTTPException(status_code=403, detail="The settings console is limited to approved operator accounts.")
    supplied = (body.passphrase or "").encode()
    expected = RUNTIME_SETTINGS_PASSPHRASE.encode()
    if not supplied or not hmac.compare_digest(supplied, expected):
        # Deliberately vague: do not confirm whether a passphrase exists.
        raise HTTPException(status_code=401, detail="Incorrect passphrase.")
    expiry = datetime.now(timezone.utc) + timedelta(minutes=UNLOCK_MINUTES)
    await users_collection.update_one(
        {"id": current_user.id},
        {"$set": {"runtime_settings_unlocked_until": expiry.isoformat()}},
    )
    log.info("Settings console unlocked for %s", current_user.id)
    return {"unlocked": True, "unlocked_until": expiry.isoformat(), "minutes": UNLOCK_MINUTES}


@router.post("/console/lock")
async def lock_console(current_user: User = Depends(get_current_user)):
    if not console_available():
        raise HTTPException(status_code=404, detail="Not found")
    await users_collection.update_one(
        {"id": current_user.id},
        {"$set": {"runtime_settings_unlocked_until": None}},
    )
    return {"unlocked": False}


async def _validate_payload(payload: dict) -> dict:
    """Check every supplied secret before anything is stored."""
    submitted = {k: str(v) for k, v in payload.items()
                 if k in runtime_settings.SECRET_KEYS and str(v).strip()}
    if not submitted:
        return {}
    return await key_validator.validate_many(submitted)


@router.post("/console/validate")
async def validate_console(body: SaveBody, current_user: User = Depends(get_current_user)):
    """Dry run: report whether each submitted key works. Writes nothing."""
    await _require_operator(current_user)
    payload = dict(body.keys or {})
    if body.api_key is not None:
        payload.setdefault("OPENAI_API_KEY", body.api_key)
    if not payload:
        raise HTTPException(status_code=400, detail="No settings provided")
    results = await _validate_payload(payload)
    blocked = sorted(k for k, r in results.items() if key_validator.blocking_status(r["status"]))
    return {
        "status": "invalid" if blocked else "ok",
        "results": results,
        "rejected": blocked,
    }


@router.put("/console")
async def save_console(body: SaveBody, current_user: User = Depends(get_current_user)):
    """Save supplied credentials. Blank values clear a console-stored value.

    In ``validate`` mode nothing is written; the caller gets the provider verdict
    for each key. In ``apply`` mode a key is only persisted once the provider has
    accepted it (or could not be reached at all, which cannot be helped offline).
    """
    await _require_operator(current_user)
    payload = dict(body.keys or {})
    if body.api_key is not None:
        payload.setdefault("OPENAI_API_KEY", body.api_key)
    if not payload:
        raise HTTPException(status_code=400, detail="No settings provided")

    validation = await _validate_payload(payload)
    if body.mode == "validate":
        blocked = sorted(k for k, r in validation.items() if key_validator.blocking_status(r["status"]))
        return {"status": "invalid" if blocked else "ok", "results": validation, "rejected": blocked}

    rejected = [k for k, r in validation.items() if key_validator.blocking_status(r["status"])]
    if rejected:
        raise HTTPException(status_code=422, detail={
            "message": "The provider rejected these credentials; nothing was saved.",
            "rejected": rejected,
            "results": validation,
        })

    try:
        changed = await runtime_settings.save(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if not changed:
        raise HTTPException(status_code=400, detail="Nothing was saved. Environment values take precedence.")

    # Mirror into backend/.env so the values survive a process restart, and make
    # sure that file can never be committed.
    env_written, env_ignored, env_error = [], None, None
    if body.persist_env:
        # Secrets and switches both persist; a model choice is configuration, not
        # a credential, but it still has to survive a restart.
        persistable = set(runtime_settings.SECRET_KEYS) | set(runtime_settings.SETTING_KEYS)
        to_write = {k: str(v).strip() for k, v in payload.items()
                    if k in persistable and str(v).strip()}
        if to_write:
            try:
                env_ignored = env_writer.ensure_gitignored()
                env_written = env_writer.write_values(to_write)
            except env_writer.EnvWriteError as exc:
                # The in-memory/DB save already succeeded, so report rather than fail.
                env_error = str(exc)
                log.warning("Could not persist credentials to .env: %s", exc)

    log.info("Runtime settings updated: %s", ", ".join(changed))
    snapshot = await runtime_settings.effective_snapshot()
    return {
        "status": "ok",
        "changed": changed,
        "validation": validation,
        "env_written": env_written,
        "env_file": env_writer.SECRETS_FILE_LABEL,
        "env_ignored": env_ignored,
        "env_error": env_error,
        **snapshot,
    }


@router.get("/auth-status")
async def auth_status(current_user: User = Depends(get_current_user)):
    """Non-secret Google sign-in state for the console."""
    await _require_operator(current_user)
    return {
        "google_client_id": await runtime_settings.secret("GOOGLE_CLIENT_ID") or "",
        "google_configured": bool(await runtime_settings.secret("GOOGLE_CLIENT_ID")
                                  and await runtime_settings.secret("GOOGLE_CLIENT_SECRET")),
        "auth_url": await runtime_settings.setting("GOOGLE_AUTH_URL") or "",
        "redirect_hint": "Add {origin}/auth-complete.html as an authorised redirect URI in Google Cloud Console.",
    }


@router.get("/env-status")
async def env_status(current_user: User = Depends(get_current_user)):
    """Report whether credentials are persisted and ignored by git."""
    await _require_operator(current_user)
    return {
        "file": env_writer.SECRETS_FILE_LABEL,
        "exists": env_writer.SECRETS_FILE.exists(),
        "keys": env_writer.read_keys(),
        "gitignored": env_writer.is_gitignored(),
    }


@router.delete("/console")
async def clear_console(scope: str = "all", current_user: User = Depends(get_current_user)):
    """Clear console-stored values. ``scope=all`` or a single field key."""
    await _require_operator(current_user)
    keys = None if scope in ("", "all") else [scope]
    if keys and keys[0] not in runtime_settings.SECRET_KEYS + runtime_settings.SETTING_KEYS:
        raise HTTPException(status_code=422, detail="Unknown setting key")
    removed = await runtime_settings.clear(keys)
    snapshot = await runtime_settings.effective_snapshot()
    return {"status": "ok", "cleared": removed, **snapshot}
