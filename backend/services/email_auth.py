"""Password and TLS mail primitives for optional first-party email sign-in.

No plaintext passwords or raw verification tokens are stored. No e-mail is sent
unless the feature, an explicit public origin, and encrypted SMTP are configured.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.parse import quote, urlsplit

from fastapi import HTTPException
import config

log = logging.getLogger(__name__)
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN = 32768, 8, 1, 32
SCRYPT_MAXMEM = 64 * 1024 * 1024
_hash_slots = asyncio.Semaphore(2)


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def validate_new_password(value: str) -> None:
    if not isinstance(value, str) or not 12 <= len(value) <= 128 or len(value.encode("utf-8")) > 512:
        raise HTTPException(status_code=422, detail="Use a password or passphrase between 12 and 128 characters.")


def _hash_password(value: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    result = hashlib.scrypt(value.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                            p=SCRYPT_P, dklen=SCRYPT_DKLEN, maxmem=SCRYPT_MAXMEM)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_encode(salt)}${_encode(result)}"


# An unknown email performs the same expensive work as a known email.
DUMMY_HASH = _hash_password("not-a-real-password-for-any-account", b"roastbox-dummy!!")


def _verify_password(value: str, record: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = record.split("$")
        # Do not let a corrupted DB record select excessive work factors.
        if (algorithm, int(n), int(r), int(p)) != ("scrypt", SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return False
        computed = _hash_password(value, _decode(salt)).split("$")[-1]
        return hmac.compare_digest(computed, expected)
    except (TypeError, ValueError, UnicodeError):
        return False


async def _limited_hash(function, *args):
    try:
        await asyncio.wait_for(_hash_slots.acquire(), timeout=3)
    except TimeoutError:
        raise HTTPException(status_code=429, detail="Too many sign-in requests. Try again shortly.", headers={"Retry-After": "10"})
    try:
        return await asyncio.to_thread(function, *args)
    finally:
        _hash_slots.release()


async def hash_password(value: str) -> str:
    validate_new_password(value)
    return await _limited_hash(_hash_password, value)


async def verify_password(value: str, record: str) -> bool:
    if not isinstance(value, str) or len(value) > 128 or len(value.encode("utf-8")) > 512:
        value = "invalid-oversize-password"
        record = DUMMY_HASH
    return await _limited_hash(_verify_password, value, record)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def mail_available() -> bool:
    if not config.EMAIL_AUTH_ENABLED or not config.SMTP_HOST or not config.SMTP_FROM:
        return False
    if not 1 <= config.SMTP_PORT <= 65535 or config.SMTP_TLS_MODE not in ("starttls", "ssl"):
        return False
    if bool(config.SMTP_USERNAME) != bool(config.SMTP_PASSWORD):
        return False
    if "\n" in config.SMTP_FROM or "\r" in config.SMTP_FROM:
        return False
    address = parseaddr(config.SMTP_FROM)[1]
    if "@" not in address or any(ch.isspace() for ch in address):
        return False
    try:
        origin = urlsplit(config.APP_BASE_URL)
        _ = origin.port
        if (origin.scheme not in ("https", "http") or not origin.hostname or origin.username or
                origin.password or origin.path or origin.query or origin.fragment):
            return False
        if origin.scheme == "http" and origin.hostname not in ("localhost", "127.0.0.1", "::1"):
            return False
    except ValueError:
        return False
    return True


def link_for(purpose: str, token: str) -> str:
    route = "verify" if purpose == "verify" else "reset"
    # A URL fragment is not sent to the web server or in HTTP Referer headers.
    return f"{config.APP_BASE_URL}/auth/{route}#token={quote(token, safe='')}"


def _send_mail(recipient: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = config.SMTP_FROM
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)
    tls_context = ssl.create_default_context()
    if config.SMTP_TLS_MODE == "ssl":
        connection = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=tls_context, timeout=12)
    else:
        connection = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=12)
    with connection as smtp:
        if config.SMTP_TLS_MODE == "starttls":
            smtp.ehlo()
            smtp.starttls(context=tls_context)
            smtp.ehlo()
        if config.SMTP_USERNAME:
            smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        smtp.send_message(msg)


async def send_mail(recipient: str, subject: str, body: str) -> None:
    try:
        await asyncio.to_thread(_send_mail, recipient, subject, body)
    except Exception as exc:
        # SMTP errors may include addresses or tokens; never log the message.
        log.warning("Email delivery failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Email delivery is temporarily unavailable. Please try again.")
