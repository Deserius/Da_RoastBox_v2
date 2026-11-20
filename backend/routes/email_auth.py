"""Optional, verified email/password sign-in alongside the managed Google flow.

Registration emails a one-time link; the mailbox owner chooses the password
*after* opening it. This prevents pre-registration with an attacker-known
password. An already verified Google account is linked only after mailbox proof.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import config
from auth_deps import validate_cookie_origin
from db import (users_collection, sessions_collection, email_credentials_collection,
                email_tokens_collection, email_rate_limits_collection)
from models import User
from services.app_sessions import issue_app_session
from services import email_auth as auth

router = APIRouter(prefix="/auth/email", tags=["email authentication"])
GENERIC = "If the address can be used, an email with next steps will arrive shortly."
INVALID_LINK = "This link is invalid, expired, or already used. Request a new one."


class EmailRequest(BaseModel):
    email: EmailStr


class LoginRequest(EmailRequest):
    password: str = Field(min_length=1, max_length=128)


class TokenPasswordRequest(BaseModel):
    token: str = Field(min_length=30, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    password: str = Field(min_length=12, max_length=128)


def _normal_email(value: EmailStr) -> str:
    return str(value).strip().casefold()


def _now():
    return datetime.now(timezone.utc)


def _private_key(scope: str, value: str, bucket: int) -> str:
    data = f"{scope}\0{value}\0{bucket}".encode("utf-8")
    return hmac.new(config.JWT_SECRET.encode("utf-8"), data, hashlib.sha256).hexdigest()


async def _rate(scope: str, value: str, limit: int, window: int) -> None:
    now = _now()
    bucket = int(now.timestamp()) // window
    key = _private_key(scope, value, bucket)
    update = {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": now + timedelta(seconds=window * 2)}}
    try:
        record = await email_rate_limits_collection.find_one_and_update(
            {"_id": key}, update, upsert=True, return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        record = await email_rate_limits_collection.find_one_and_update(
            {"_id": key}, update, return_document=ReturnDocument.AFTER)
    if record and record.get("count", 0) > limit:
        raise HTTPException(status_code=429, detail="Too many requests. Please wait and try again.",
                            headers={"Retry-After": str(window)})


async def _limit(request: Request, action: str, address_or_token: str, *, ip_limit: int, key_limit: int, window: int):
    # Do not trust an arbitrary X-Forwarded-For header. Configure the trusted
    # proxy chain so ASGI request.client is the real client in production.
    ip = request.client.host if request.client else "unknown"
    await _rate(f"{action}:ip", ip, ip_limit, window)
    await _rate(f"{action}:key", address_or_token, key_limit, window)


def _require_enabled() -> None:
    if not config.EMAIL_AUTH_ENABLED:
        raise HTTPException(status_code=503, detail="Email sign-in is not configured.")


def _require_mail() -> None:
    _require_enabled()
    if not auth.mail_available():
        raise HTTPException(status_code=503, detail="Email delivery is not configured.")


async def _issue_token(email: str, purpose: str, user_id: str | None = None) -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    hashed = auth.token_hash(raw)
    await email_tokens_collection.insert_one({"_id": hashed, "email": email, "purpose": purpose,
        "user_id": user_id, "created_at": _now(), "expires_at": _now() + timedelta(minutes=30)})
    return raw, hashed


async def _matching_users(email: str):
    return await users_collection.find({"email": re.compile(r"^" + re.escape(email) + r"$", re.IGNORECASE)}).limit(2).to_list(length=2)


@router.get("/status")
async def status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"login_available": config.EMAIL_AUTH_ENABLED, "registration_available": auth.mail_available(),
            "recovery_available": auth.mail_available(),
            # Drives the sign-in screen: whether Google sign-in is offered, and
            # whether the operator supplied their own OAuth client.
            "google_login_available": bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET),
            "google_auth_url": config.GOOGLE_AUTH_URL,
            "preview_login_available": config.ENABLE_PREVIEW_LOGIN,
            "dev_login_available": config.ALLOW_DEV_LOGIN}


@router.post("/register", status_code=202)
async def register(body: EmailRequest, request: Request, response: Response):
    _require_mail()
    validate_cookie_origin(request)
    email = _normal_email(body.email)
    await _limit(request, "register", email, ip_limit=12, key_limit=3, window=3600)
    existing = await email_credentials_collection.find_one({"email": email}, {"_id": 1})
    hashed = None
    if existing:
        message = ("A request was made to create an email sign-in for this address. "
                   "If you already have one, sign in or use password recovery. "
                   "If you did not request this, you can ignore this email.\n\nDa RoastBox")
    else:
        token, hashed = await _issue_token(email, "verify")
        message = ("Someone requested an email sign-in for Da RoastBox. "
                   "Only the owner of this mailbox can choose the password. "
                   "Open the link below within 30 minutes to continue:\n\n"
                   f"{auth.link_for('verify', token)}\n\n"
                   "If you did not request this, ignore this email; no account will be created.\n\nDa RoastBox")
    try:
        await auth.send_mail(email, "Your Da RoastBox sign-in request", message)
    except HTTPException:
        if hashed: await email_tokens_collection.delete_one({"_id": hashed})
        raise
    response.headers["Cache-Control"] = "no-store"
    return {"message": GENERIC}


@router.post("/verify")
async def verify(body: TokenPasswordRequest, request: Request, response: Response):
    _require_enabled()
    validate_cookie_origin(request)
    hashed = auth.token_hash(body.token)
    await _limit(request, "verify", hashed, ip_limit=30, key_limit=8, window=900)
    candidate = await email_tokens_collection.find_one({"_id": hashed, "purpose": "verify", "expires_at": {"$gt": _now()}})
    if not candidate:
        raise HTTPException(status_code=400, detail=INVALID_LINK)
    password_hash = await auth.hash_password(body.password)
    # Consume atomically: a link cannot be redeemed twice, even concurrently.
    token = await email_tokens_collection.find_one_and_delete({"_id": hashed, "purpose": "verify", "expires_at": {"$gt": _now()}})
    if not token:
        raise HTTPException(status_code=400, detail=INVALID_LINK)
    email = token["email"]
    if await email_credentials_collection.find_one({"email": email}, {"_id": 1}):
        raise HTTPException(status_code=400, detail=INVALID_LINK)
    matches = await _matching_users(email)
    if len(matches) > 1 or (matches and matches[0].get("is_preview")):
        raise HTTPException(status_code=409, detail="This email cannot be linked automatically. Contact support.")
    if matches:
        user_doc = matches[0]
    else:
        user = User(email=email, name=email.split("@", 1)[0])
        try:
            await users_collection.insert_one(user.model_dump())
            user_doc = user.model_dump()
        except DuplicateKeyError:
            # A concurrent Google signup for the same normalized email wins;
            # mailbox verification still proves the owner can add this method.
            matches = await _matching_users(email)
            if len(matches) != 1 or matches[0].get("is_preview"):
                raise HTTPException(status_code=409, detail="This email cannot be linked automatically. Contact support.")
            user_doc = matches[0]
    try:
        await email_credentials_collection.insert_one({"email": email, "user_id": user_doc["id"],
            "password_hash": password_hash, "verified_at": _now(), "password_changed_at": _now()})
    except DuplicateKeyError:
        # A second registration link must never overwrite an existing password.
        raise HTTPException(status_code=400, detail=INVALID_LINK)
    await email_tokens_collection.delete_many({"email": email, "purpose": "verify"})
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Email verified. You can now sign in with your password."}


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    _require_enabled()
    validate_cookie_origin(request)
    email = _normal_email(body.email)
    await _limit(request, "login", email, ip_limit=30, key_limit=8, window=900)
    credential = await email_credentials_collection.find_one({"email": email})
    valid = await auth.verify_password(body.password, credential["password_hash"] if credential else auth.DUMMY_HASH)
    user_doc = await users_collection.find_one({"id": credential["user_id"]}) if credential and valid else None
    if not valid or not user_doc or user_doc.get("is_preview"):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    user_doc.pop("_id", None)
    user = User(**user_doc)
    session_token = await issue_app_session(user.id, response)
    response.headers["Cache-Control"] = "no-store"
    return {"user": {"id": user.id, "email": user.email, "name": user.name,
                     "picture": user.picture, "credits": user.credits}, "session_token": session_token}


@router.post("/forgot", status_code=202)
async def forgot(body: EmailRequest, request: Request, response: Response):
    _require_mail()
    validate_cookie_origin(request)
    email = _normal_email(body.email)
    await _limit(request, "forgot", email, ip_limit=12, key_limit=3, window=3600)
    credential = await email_credentials_collection.find_one({"email": email})
    hashed = None
    if credential:
        token, hashed = await _issue_token(email, "reset", credential["user_id"])
        message = ("Someone requested a new Da RoastBox password. Open the link below within 30 minutes "
                   "to choose a new password:\n\n"
                   f"{auth.link_for('reset', token)}\n\n"
                   "If you did not request this, ignore this email; your password will not change.\n\nDa RoastBox")
    else:
        message = ("A password recovery request was made for this address. If you use Google sign-in, "
                   "continue with Google or create an email sign-in first. "
                   "If you did not request this, you can ignore this email.\n\nDa RoastBox")
    try:
        await auth.send_mail(email, "Your Da RoastBox password request", message)
    except HTTPException:
        if hashed: await email_tokens_collection.delete_one({"_id": hashed})
        raise
    response.headers["Cache-Control"] = "no-store"
    return {"message": GENERIC}


@router.post("/reset")
async def reset(body: TokenPasswordRequest, request: Request, response: Response):
    _require_enabled()
    validate_cookie_origin(request)
    hashed = auth.token_hash(body.token)
    await _limit(request, "reset", hashed, ip_limit=30, key_limit=8, window=900)
    candidate = await email_tokens_collection.find_one({"_id": hashed, "purpose": "reset", "expires_at": {"$gt": _now()}})
    if not candidate:
        raise HTTPException(status_code=400, detail=INVALID_LINK)
    password_hash = await auth.hash_password(body.password)
    token = await email_tokens_collection.find_one_and_delete({"_id": hashed, "purpose": "reset", "expires_at": {"$gt": _now()}})
    if not token:
        raise HTTPException(status_code=400, detail=INVALID_LINK)
    result = await email_credentials_collection.update_one({"email": token["email"], "user_id": token["user_id"]},
        {"$set": {"password_hash": password_hash, "password_changed_at": _now()}})
    if not result.matched_count:
        raise HTTPException(status_code=400, detail=INVALID_LINK)
    # Force re-authentication everywhere after a password reset, and invalidate
    # any other outstanding recovery links for this account.
    await sessions_collection.delete_many({"user_id": token["user_id"]})
    await email_tokens_collection.delete_many({"email": token["email"], "purpose": "reset"})
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Password updated. Please sign in again."}
