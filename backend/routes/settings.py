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
from services import runtime_settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

UNLOCK_MINUTES = 60


def console_available() -> bool:
    """The console needs an explicit opt-in and a passphrase to compare against."""
    return bool(ALLOW_RUNTIME_SETTINGS and RUNTIME_SETTINGS_PASSPHRASE)


def _is_operator(user: User) -> bool:
    """Only disposable preview accounts, or an explicit allowlist, may operate this.

    A real customer account must never reach this page even with the passphrase,
    because the stored credentials would then be spendable by a stranger. Note
    that ``ENABLE_PREVIEW_LOGIN`` only means preview sign-in exists; it must not
    be read as "every account is an operator".
    """
    if RUNTIME_SETTINGS_ADMINS:
        identity = {(user.id or "").lower(), (user.email or "").lower()}
        return bool(identity & set(RUNTIME_SETTINGS_ADMINS))
    return bool(user.is_preview)


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
        raise HTTPException(status_code=403, detail="The settings console is limited to preview accounts.")
    if await _unlock_expiry(user) is None:
        raise HTTPException(status_code=403, detail="Settings console is locked. Enter the passphrase to unlock.")


class UnlockBody(BaseModel):
    passphrase: str = ""


class SaveBody(BaseModel):
    api_key: Optional[str] = None
    keys: Optional[dict] = None


@router.get("/console")
async def console_state(current_user: User = Depends(get_current_user)):
    """Report what is configured and whether the console is unlocked."""
    if not console_available():
        raise HTTPException(status_code=404, detail="Not found")
    if not _is_operator(current_user):
        raise HTTPException(status_code=403, detail="The settings console is limited to preview accounts.")
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
        raise HTTPException(status_code=403, detail="The settings console is limited to preview accounts.")
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


@router.put("/console")
async def save_console(body: SaveBody, current_user: User = Depends(get_current_user)):
    """Save supplied credentials. Blank values clear a console-stored value."""
    await _require_operator(current_user)
    payload = dict(body.keys or {})
    if body.api_key is not None:
        payload.setdefault("OPENAI_API_KEY", body.api_key)
    if not payload:
        raise HTTPException(status_code=400, detail="No settings provided")
    try:
        changed = await runtime_settings.save(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if not changed:
        raise HTTPException(status_code=400, detail="Nothing was saved. Environment values take precedence.")
    log.info("Runtime settings updated: %s", ", ".join(changed))
    snapshot = await runtime_settings.effective_snapshot()
    return {"status": "ok", "changed": changed, **snapshot}


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
