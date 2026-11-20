"""Authenticate a locally stored app session via app header, Bearer, or cookie."""
from fastapi import Depends, HTTPException, Request
import logging
from typing import Optional
from datetime import datetime, timezone
from db import sessions_collection, users_collection
from models import User
from config import APP_BASE_URL, CORS_ORIGINS

log = logging.getLogger(__name__)


def active_plan_tier(tier: str, until: Optional[str]) -> str:
    """A 30-day plan must not keep tier-only discounts after its expiry."""
    if tier not in ("plus", "vip") or not until:
        return "free"
    try:
        expiry = until if isinstance(until, datetime) else datetime.fromisoformat(until)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return tier if expiry > datetime.now(timezone.utc) else "free"
    except (ValueError, TypeError):
        return "free"


def validate_cookie_origin(request: Request) -> None:
    """Reject cross-site state changes authenticated only by ambient cookies."""
    if request.method.upper() in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    if not origin:
        if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
            raise HTTPException(status_code=403, detail="Cross-site cookie request rejected")
        return  # non-browser clients may omit Origin
    trusted = {entry for entry in CORS_ORIGINS if entry != "*"}
    if APP_BASE_URL:
        trusted.add(APP_BASE_URL)
    trusted.add(f"{request.url.scheme}://{request.url.netloc}")
    if origin.rstrip("/") not in trusted:
        raise HTTPException(status_code=403, detail="Cross-site cookie request rejected")


async def get_current_user(request: Request) -> User:
    # The custom app header survives preview proxies that reserve Authorization.
    # Bearer and cookie sessions remain supported for existing clients.
    token: Optional[str] = (request.headers.get("X-Roastbox-Session") or "").strip() or None
    auth = request.headers.get("Authorization") or ""
    if not token and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
    if not token:
        token = request.cookies.get("session_token")
        if token:
            validate_cookie_origin(request)
    if not token:
        # Log transport presence only, never credentials, to diagnose restrictive preview proxies.
        log.info("No app session (app_header=%s, bearer=%s, cookie=%s)",
                 bool(request.headers.get("X-Roastbox-Session")),
                 auth.startswith("Bearer "), bool(request.cookies.get("session_token")))
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = await sessions_collection.find_one({"session_token": token})
    if not session:
        log.info("App session not found (app_header=%s, bearer=%s, cookie=%s)",
                 bool(request.headers.get("X-Roastbox-Session")),
                 auth.startswith("Bearer "), bool(request.cookies.get("session_token")))
        raise HTTPException(status_code=401, detail="Invalid session")

    expires = session.get("expires_at")
    try:
        expiry = expires if isinstance(expires, datetime) else datetime.fromisoformat(expires)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid session expiry")
    if expiry <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    user = await users_collection.find_one({"id": session["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    user.pop("_id", None)
    current = User(**user)
    # Keep separately stored unlocks intact; only time-limited tier benefits end.
    current.plan_tier = active_plan_tier(current.plan_tier, current.plan_until)
    return current


async def get_current_user_optional(request: Request) -> Optional[User]:
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


async def get_optional_user(request: Request) -> Optional[User]:
    return await get_current_user_optional(request)
