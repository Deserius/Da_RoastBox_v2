"""Fallback for embedded preview proxies that strip all auth headers and cookies.

The app session is supplied in a POST body, never in a URL. The request is
routed internally through the same FastAPI app and all normal authorization,
validation and quotas still apply. Do not log request bodies in your proxy/APM.
"""
import json
from urllib.parse import unquote, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from starlette.datastructures import UploadFile

from auth_deps import get_current_user
from services.roast_engine import MAX_IMAGE_BYTES, MAX_IMAGES

router = APIRouter(prefix="/session", tags=["session"])


@router.post("/dispatch")
async def dispatch(request: Request):
    form = await request.form(max_files=MAX_IMAGES, max_fields=100)
    token = form.get("token")
    method = str(form.get("method") or "").upper()
    raw_path = str(form.get("path") or "")
    kind = str(form.get("kind") or "none")
    if not isinstance(token, str) or not token or len(token) > 512:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if method not in {"GET", "POST", "DELETE", "PUT", "PATCH"}:
        raise HTTPException(status_code=400, detail="Unsupported method")
    if len(raw_path) > 4096:
        raise HTTPException(status_code=400, detail="Invalid API path")
    target = urlsplit(raw_path)
    decoded = unquote(target.path)
    blocked = ("/api/session/", "/api/auth/session", "/api/auth/dev-login", "/api/auth/preview-login", "/api/payments/webhook")
    if (target.scheme or target.netloc or target.fragment or not target.path.startswith("/api/") or
            decoded.startswith(blocked) or "\\" in decoded or any(p in (".", "..") for p in decoded.split("/"))):
        raise HTTPException(status_code=400, detail="Invalid API path")

    # Authenticate the body token before forwarding even optional/public routes.
    scope = {"type": "http", "method": "GET", "path": "/api/auth/me", "query_string": b"",
             "scheme": "http", "server": ("internal", 80), "headers": [(b"x-roastbox-session", token.encode())]}
    await get_current_user(Request(scope))
    headers = {"X-Roastbox-Session": token}
    if request.headers.get("origin"):
        headers["Origin"] = request.headers["origin"]
    kwargs = {}
    if kind == "json":
        payload = form.get("payload") or "{}"
        if not isinstance(payload, str) or len(payload.encode()) > 64 * 1024:
            raise HTTPException(status_code=413, detail="Request body is too large")
        try:
            json.loads(payload)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid JSON request")
        kwargs["content"] = payload.encode()
        headers["Content-Type"] = "application/json"
    elif kind == "form":
        fields = {}
        files = []
        for key, value in form.multi_items():
            if key.startswith("field:") and isinstance(value, str):
                name = key[6:]
                if name in fields:
                    if not isinstance(fields[name], list):
                        fields[name] = [fields[name]]
                    fields[name].append(value)
                else:
                    fields[name] = value
            elif key.startswith("file:") and isinstance(value, UploadFile):
                data = await value.read(MAX_IMAGE_BYTES + 1)
                if len(data) > MAX_IMAGE_BYTES:
                    raise HTTPException(status_code=413, detail="Each image must be 8 MB or smaller.")
                files.append((key[5:], (value.filename or "upload", data, value.content_type or "application/octet-stream")))
        kwargs["data"] = fields
        if files:
            kwargs["files"] = files
    elif kind != "none":
        raise HTTPException(status_code=400, detail="Unsupported request body")

    # ASGITransport never leaves this process or uses a browser-facing localhost.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=request.app), base_url="http://internal") as client:
        inner = await client.request(method, target.path + ("?" + target.query if target.query else ""), headers=headers, **kwargs)
    response_headers = {"Cache-Control": "no-store"}
    for name in ("content-type", "content-disposition", "set-cookie"):
        if name in inner.headers:
            response_headers[name] = inner.headers[name]
    return Response(content=inner.content, status_code=inner.status_code, headers=response_headers)
