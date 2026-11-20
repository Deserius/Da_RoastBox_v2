"""Additional password gate for an isolated beta, not a replacement for app auth.

Enabled only by APP_ENV=beta. Uses a pre-provisioned scrypt verifier and signing
key; never invents/resets the owner's existing password or writes credentials.
The gate protects pages and APIs. The signed Stripe webhook still performs its
own signature verification; only liveness/readiness and that POST bypass it.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import hashlib
import hmac
import html
import secrets
import time
from urllib.parse import parse_qs

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

COOKIE_NAME = "__Host-roastbox-beta"
COOKIE_TTL = 4 * 60 * 60
GATE_PATH = "/_beta/access"
MAX_FORM_BYTES = 2048


def password_verifier(password: str, *, salt: bytes | None = None) -> str:
    """For an explicit provisioning tool/test only; not called at app startup."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + salt.hex() + "$" + digest.hex()


def parse_verifier(value: str) -> tuple[bytes, bytes]:
    parts = value.split("$")
    if len(parts) != 6 or parts[:4] != ["scrypt", "16384", "8", "1"]:
        raise ValueError("BETA_ACCESS_PASSWORD_HASH must use the documented scrypt verifier format")
    try:
        salt, digest = bytes.fromhex(parts[4]), bytes.fromhex(parts[5])
    except ValueError:
        raise ValueError("Invalid beta password verifier") from None
    if len(salt) != 16 or len(digest) != 32:
        raise ValueError("Invalid beta password verifier")
    return salt, digest


class BetaAccessMiddleware:
    def __init__(self, app, *, password_hash: str, signing_key: str, origin: str):
        self.app = app
        self.salt, self.digest = parse_verifier(password_hash)
        if len(signing_key) < 32:
            raise ValueError("A persistent BETA_ACCESS_SIGNING_KEY of at least 32 characters is required")
        self.key = signing_key.encode()
        self.origin = origin.rstrip("/")
        self.failures = OrderedDict()
        self.kdf_slots = asyncio.Semaphore(1)  # Bound password-memory overlap on Free.

    def _cookie(self) -> str:
        unsigned = f"v1.{int(time.time())}.{secrets.token_hex(16)}"
        return unsigned + "." + hmac.new(self.key, unsigned.encode(), hashlib.sha256).hexdigest()

    def _valid_cookie(self, cookie: str | None) -> bool:
        if not cookie or len(cookie) > 180:
            return False
        parts = cookie.split(".")
        if len(parts) != 4 or parts[0] != "v1" or len(parts[2]) != 32:
            return False
        try:
            age = time.time() - int(parts[1])
            if not 0 <= age < COOKIE_TTL:
                return False
            unsigned = ".".join(parts[:3])
            expected = hmac.new(self.key, unsigned.encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, parts[3])
        except (ValueError, TypeError):
            return False

    def _origin_ok(self, request: Request) -> bool:
        origin = request.headers.get("origin")
        if origin:
            return origin.rstrip("/") == self.origin
        return request.headers.get("sec-fetch-site", "").lower() != "cross-site"

    def _client_bucket(self, scope) -> str:
        # Never trust a client-supplied X-Forwarded-For. Configure trusted proxies
        # at the ASGI server before relying on scope['client'] for edge traffic.
        peer = str((scope.get("client") or ("unknown", 0))[0])
        return hmac.new(self.key, peer.encode(), hashlib.sha256).hexdigest()

    def _page(self, error: str = "", status: int = 200) -> HTMLResponse:
        alert = f'<p role="alert">{html.escape(error)}</p>' if error else ""
        return HTMLResponse("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>Da RoastBox — Private Beta</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#100d19;color:#f5efff;font:16px system-ui}main{margin:20px;padding:30px;max-width:370px;border:1px solid #654277;border-radius:20px;background:#21162c}input,button{box-sizing:border-box;width:100%;padding:13px;margin-top:12px;border-radius:10px;border:1px solid #9779aa;font:inherit}button{background:#e07124;color:#130b08;font-weight:700;cursor:pointer}p{line-height:1.5;color:#d1c1da}</style></head><body><main><h1>Private beta access</h1><p>This extra password protects the test site. You will still sign in to your own account and confirm 21+ consent inside the app.</p>""" + alert + f"""<form method="post" action="{GATE_PATH}"><label for="password">Beta access password</label><input id="password" name="password" type="password" required maxlength="512" autocomplete="current-password"><button type="submit">Continue securely</button></form></main></body></html>""", status_code=status,
                            headers={"Cache-Control": "private, no-store"})

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            # No websocket beta interface is currently supported. Fail closed.
            return await send({"type": "websocket.close", "code": 1008})
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path, method = scope.get("path", ""), scope.get("method", "")
        if (path in {"/api/health", "/api/ready"} and method in {"GET", "HEAD"}) or (path == "/api/payments/webhook" and method == "POST"):
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        if path == GATE_PATH:
            if method == "GET":
                return await self._page()(scope, receive, send)
            if method != "POST":
                return await Response(status_code=405, headers={"Allow": "GET, POST"})(scope, receive, send)
            if not self._origin_ok(request):
                return await JSONResponse({"detail": "Cross-site access request rejected"}, status_code=403)(scope, receive, send)
            if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/x-www-form-urlencoded":
                return await JSONResponse({"detail": "Unsupported access form"}, status_code=415)(scope, receive, send)
            bucket, now = self._client_bucket(scope), time.monotonic()
            failures, until = self.failures.get(bucket, (0, 0))
            if failures >= 5 and now < until:
                return await JSONResponse({"detail": "Too many password attempts. Try again in five minutes."}, status_code=429, headers={"Retry-After": "300"})(scope, receive, send)
            if now >= until:
                failures = 0
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > MAX_FORM_BYTES:
                    return await JSONResponse({"detail": "Access form is too large"}, status_code=413)(scope, receive, send)
            try:
                values = parse_qs(raw.decode("utf-8"), max_num_fields=2, keep_blank_values=True)
                passwords = values.get("password", [])
                password = passwords[0] if len(passwords) == 1 else ""
            except (ValueError, UnicodeError):
                password = ""
            if not password or len(password.encode()) > 512:
                valid = False
            else:
                async with self.kdf_slots:
                    digest = await asyncio.to_thread(hashlib.scrypt, password.encode(), salt=self.salt, n=16384, r=8, p=1, dklen=32)
                valid = hmac.compare_digest(digest, self.digest)
            if not valid:
                self.failures[bucket] = (failures + 1, now + 300)
                self.failures.move_to_end(bucket)
                while len(self.failures) > 2048:
                    self.failures.popitem(last=False)
                return await self._page("Incorrect access password.", 401)(scope, receive, send)
            self.failures.pop(bucket, None)
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(COOKIE_NAME, self._cookie(), max_age=COOKIE_TTL, secure=True,
                                httponly=True, samesite="lax", path="/")
            return await response(scope, receive, send)
        if not self._valid_cookie(request.cookies.get(COOKIE_NAME)):
            if path.startswith("/api/"):
                response = JSONResponse({"detail": "Private beta access password required", "code": "beta_access_required"}, status_code=401)
            else:
                response = self._page()
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)
