"""Issue the same revocable application session for each verified sign-in method."""
import secrets
from datetime import datetime, timedelta, timezone

from db import sessions_collection


async def issue_app_session(user_id, response):
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    await sessions_collection.insert_one({"session_token": token, "user_id": user_id, "expires_at": expires_at})
    response.set_cookie(
        key="session_token", value=token, httponly=True, secure=True,
        samesite="lax", max_age=7 * 24 * 60 * 60, path="/",
    )
    return token
