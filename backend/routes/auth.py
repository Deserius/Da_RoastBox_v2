"""Authentication via Emergent Managed Google Auth.

The frontend uses the original managed Google consent service. Emergent returns a
short-lived session_id in the callback fragment; the backend exchanges it with the
original provider endpoint, then issues a separate, revocable app session.
"""
import secrets
import re
import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Response, Request, Depends
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from db import users_collection, sessions_collection
from models import User
from auth_deps import get_current_user, validate_cookie_origin
from config import ALLOW_DEV_LOGIN, ENABLE_PREVIEW_LOGIN
from services.app_sessions import issue_app_session

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

EMERGENT_AUTH_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


class SessionRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=4096)


@router.post("/session")
async def create_session(body: SessionRequest, response: Response):
    """Exchange the managed provider's one-time ID for a local app session."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(
                EMERGENT_AUTH_URL,
                headers={"X-Session-ID": body.session_id},
            )
        except httpx.RequestError:
            log.warning("Google sign-in provider is unreachable", exc_info=True)
            raise HTTPException(status_code=502, detail="Sign-in provider is unavailable")
        if r.status_code != 200:
            if 400 <= r.status_code < 500:
                raise HTTPException(status_code=401, detail="Sign-in session is invalid or expired")
            log.warning("Google sign-in provider returned HTTP %s", r.status_code)
            raise HTTPException(status_code=502, detail="Sign-in provider is unavailable")
        try:
            data = r.json()
        except (ValueError, TypeError):
            raise HTTPException(status_code=502, detail="Sign-in provider returned an invalid response")

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Sign-in provider returned an invalid response")
    email = data.get("email")
    provider_token = data.get("session_token")
    if (not isinstance(email, str) or not email.strip() or "@" not in email
            or len(email) > 320 or any(ch.isspace() for ch in email.strip())):
        raise HTTPException(status_code=502, detail="Sign-in provider returned an incomplete profile")
    email = email.strip().casefold()
    if not isinstance(provider_token, str) or not provider_token.strip():
        raise HTTPException(status_code=502, detail="Sign-in provider returned an incomplete session")
    # Emergent's current contract does not always include this flag. If it does,
    # never link an explicitly unverified identity to an existing account.
    verified = data.get("email_verified")
    if verified is False or (isinstance(verified, str) and verified.lower() == "false"):
        raise HTTPException(status_code=401, detail="Google email address is not verified")

    name = data.get("name") if isinstance(data.get("name"), str) else None
    picture = data.get("picture") if isinstance(data.get("picture"), str) else None
    # Preserve legacy mixed-case Google accounts. Never merge if an old
    # database already contains two accounts differing only by email case.
    matches = await users_collection.find({"email": re.compile(r"^" + re.escape(email) + r"$", re.IGNORECASE)}).limit(2).to_list(length=2)
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="This email matches more than one account. Contact support.")
    user_doc = matches[0] if matches else None
    if not user_doc:
        new_user = User(email=email, name=name, picture=picture)
        try:
            await users_collection.insert_one(new_user.model_dump())
            user = new_user
        except DuplicateKeyError:
            # Simultaneous first logins for the same email must converge on one account.
            user_doc = await users_collection.find_one({"email": email})
            if not user_doc:
                raise HTTPException(status_code=500, detail="Could not create the account")
            user_doc.pop("_id", None)
            user = User(**user_doc)
    else:
        user_doc.pop("_id", None)
        user = User(**user_doc)

    # Preserve the user's credits and purchases while refreshing their Google profile.
    if user.name != name or user.picture != picture:
        await users_collection.update_one(
            {"id": user.id}, {"$set": {"name": name, "picture": picture}}
        )
        user.name, user.picture = name, picture

    # Do not expose the provider's credential as our application session. Existing
    # session records still work; new logins receive a fresh, revocable random token.
    session_token = await issue_app_session(user.id, response)
    return {
        "user": {
            "id": user.id, "email": user.email, "name": user.name,
            "picture": user.picture, "credits": user.credits,
        },
        "session_token": session_token,
    }


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
        "credits": current_user.credits,
        "is_preview": current_user.is_preview,
        "has_byok_openai": current_user.has_byok_openai,
        "has_byok_elevenlabs": current_user.has_byok_elevenlabs,
        "premium_personas_unlocked": current_user.premium_personas_unlocked,
        "premium_voices_unlocked": current_user.premium_voices_unlocked,
        "roast_battle_unlocked": current_user.roast_battle_unlocked,
        "nsfw_edgier_unlocked": current_user.nsfw_edgier_unlocked,
        "lifetime_founder": current_user.lifetime_founder,
        "plan_tier": current_user.plan_tier,
        "plan_until": current_user.plan_until,
        "last_free_roast_date": current_user.last_free_roast_date,
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    # Revoke the custom header, Bearer and cookie if they differ, so a stale
    # credential cannot silently sign back in after logout.
    tokens = set()
    app_token = (request.headers.get("X-Roastbox-Session") or "").strip()
    if app_token:
        tokens.add(app_token)
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        tokens.add(authorization.split(" ", 1)[1])
    cookie = request.cookies.get("session_token")
    if cookie:
        if cookie not in tokens:
            validate_cookie_origin(request)
        tokens.add(cookie)
    tokens.discard("")
    if tokens:
        await sessions_collection.delete_many({"session_token": {"$in": list(tokens)}})
    response.delete_cookie("session_token", path="/", secure=True, httponly=True, samesite="lax")
    return {"status": "ok"}


class DevLoginRequest(BaseModel):
    email: str
    name: Optional[str] = None


# Dev/test login for E2E without OAuth. Disabled unless ALLOW_DEV_LOGIN=true. Turn OFF in production.
@router.post("/dev-login")
async def dev_login(body: DevLoginRequest, response: Response):
    if not ALLOW_DEV_LOGIN:
        raise HTTPException(status_code=404, detail="Not found")

    user_doc = await users_collection.find_one({"email": body.email})
    if not user_doc:
        new_user = User(email=body.email, name=body.name or body.email.split("@")[0])
        await users_collection.insert_one(new_user.model_dump())
        user = new_user
    else:
        user_doc.pop("_id", None)
        user = User(**user_doc)

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    await sessions_collection.update_one(
        {"session_token": token},
        {"$set": {"user_id": user.id, "expires_at": expires_at}},
        upsert=True,
    )
    response.set_cookie("session_token", token, httponly=True, secure=True, samesite="lax", max_age=604800, path="/")
    return {"user": {"id": user.id, "email": user.email, "credits": user.credits}, "session_token": token}


@router.post("/preview-login")
async def preview_login(response: Response):
    """Isolated, disposable test account; never enables arbitrary-email impersonation.

    This is disabled by default and intended only for an isolated preview database.
    The credits and unlocks are for testing and do not represent payments.
    """
    if not ENABLE_PREVIEW_LOGIN:
        raise HTTPException(status_code=404, detail="Not found")

    user = User(
        email=f"preview-{secrets.token_hex(16)}@example.invalid",
        name="Preview Guest",
        credits=100,
        is_preview=True,
        premium_personas_unlocked=True,
        premium_voices_unlocked=True,
        roast_battle_unlocked=True,
        nsfw_edgier_unlocked=True,
    )
    await users_collection.insert_one(user.model_dump())
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    await sessions_collection.insert_one({"session_token": token, "user_id": user.id, "expires_at": expires_at})
    response.set_cookie("session_token", token, httponly=True, secure=True, samesite="lax", max_age=604800, path="/")
    return {"user": {"id": user.id, "email": user.email, "credits": user.credits}, "session_token": token}
