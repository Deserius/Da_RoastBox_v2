"""Release-mode configuration checks and privacy-preserving request telemetry.

No network calls, secret generation, or database writes happen in this module.
Development defaults preserve Arena's iframe and the existing local services.
"""
from __future__ import annotations
import ipaddress

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import re
import time
from typing import Mapping
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4


def enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def csv(value: str | None) -> tuple[str, ...]:
    return tuple(x.strip() for x in (value or "").split(",") if x.strip())


def safe_https_origin(value: str) -> bool:
    try:
        p = urlsplit(value)
        _ = p.port
        return bool(p.scheme == "https" and p.hostname and not p.username and
                    not p.password and p.path in {"", "/"} and not p.query and
                    not p.fragment and p.hostname not in {"localhost", "127.0.0.1", "::1"})
    except ValueError:
        return False


@dataclass(frozen=True)
class RuntimeSecurity:
    environment: str = "development"
    allowed_hosts: tuple[str, ...] = ()
    diagnostics_admins: tuple[str, ...] = ()
    paid_diagnostics: bool = False

    @classmethod
    def from_environ(cls, env: Mapping[str, str]) -> "RuntimeSecurity":
        return cls((env.get("APP_ENV") or "development").strip().lower(),
                   csv(env.get("ALLOWED_HOSTS")), csv(env.get("DIAGNOSTICS_ADMIN_USER_IDS")),
                   enabled(env.get("ENABLE_PAID_DIAGNOSTICS")))

    @property
    def release_mode(self) -> bool:
        return self.environment in {"beta", "production"}


def configuration_errors(env: Mapping[str, str]) -> list[str]:
    """Return stable codes only. Never echo an environment value or credential."""
    s = RuntimeSecurity.from_environ(env)
    errors = []
    if s.environment not in {"development", "test", "beta", "production"}:
        return ["APP_ENV_INVALID"]
    if not s.release_mode:
        return errors
    origin = (env.get("APP_BASE_URL") or env.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
    if not safe_https_origin(origin):
        errors.append("HTTPS_APP_BASE_URL_REQUIRED")
    if not s.allowed_hosts or any(h == "*" or not re.fullmatch(r"(?:\*\.)?[A-Za-z0-9.-]+", h) for h in s.allowed_hosts):
        errors.append("EXPLICIT_ALLOWED_HOSTS_REQUIRED")
    if len((env.get("JWT_SECRET") or "").strip()) < 32:
        errors.append("PERSISTENT_JWT_SECRET_MIN_32_REQUIRED_DO_NOT_ROTATE_EXISTING_KEY")
    if enabled(env.get("ALLOW_DEV_LOGIN")):
        errors.append("DEV_LOGIN_FORBIDDEN")
    if enabled(env.get("ALLOW_SOURCE_DOWNLOAD")):
        errors.append("SOURCE_DOWNLOAD_FORBIDDEN")
    origins = csv(env.get("CORS_ORIGINS"))
    if any(not safe_https_origin(o) for o in origins):
        errors.append("CORS_REQUIRES_EXPLICIT_HTTPS_ORIGINS")
    if s.paid_diagnostics and not s.diagnostics_admins:
        errors.append("PAID_DIAGNOSTICS_REQUIRE_EXPLICIT_ADMIN_IDS")
    if s.environment == "production":
        for key in ("ENABLE_PREVIEW_LOGIN", "ALLOW_PREVIEW_HOSTED_AI", "PREVIEW_UNLIMITED_CREDITS"):
            if enabled(env.get(key)):
                errors.append(f"{key}_FORBIDDEN_IN_PRODUCTION")
    if s.environment == "beta":
        if not enabled(env.get("STRIPE_TEST_ONLY", "true")):
            errors.append("BETA_REQUIRES_STRIPE_TEST_ONLY")
        if not env.get("BETA_ACCESS_PASSWORD_HASH") or not env.get("BETA_ACCESS_SIGNING_KEY"):
            errors.append("BETA_REQUIRES_ADDITIONAL_PASSWORD_GATE")
    stripe_key = env.get("STRIPE_API_KEY") or ""
    if enabled(env.get("STRIPE_TEST_ONLY", "true")) and stripe_key and not stripe_key.startswith(("sk_test_", "rk_test_")):
        errors.append("STRIPE_TEST_ONLY_REJECTS_NONTEST_KEY")
    mongo = env.get("MONGO_URL") or ""
    if not mongo:
        errors.append("MONGO_URL_REQUIRED_SUPABASE_IS_NOT_A_MONGO_URI")
    if not (env.get("DB_NAME") or "").strip():
        errors.append("DB_NAME_REQUIRED")
    if (env.get("STORAGE_BACKEND") or "emergent").strip().lower() == "local":
        if not (env.get("LOCAL_STORAGE_DIR") or "").strip():
            errors.append("EXPLICIT_DURABLE_MEDIA_PATH_REQUIRED")
        if not enabled(env.get("PERSISTENT_STORAGE_CONFIRMED")):
            errors.append("PERSISTENT_STORAGE_REQUIRES_OPERATOR_CONFIRMATION")
    if mongo:
        try:
            parsed = urlsplit(mongo)
            query = {k.lower(): [v.lower() for v in values] for k, values in parse_qs(parsed.query).items()}
            tls = parsed.scheme == "mongodb+srv" or query.get("tls") == ["true"] or query.get("ssl") == ["true"]
            host = (parsed.hostname or "").casefold().rstrip(".")
            local_host = not host or host == "localhost" or host.endswith(".localhost")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address is not None:
                mapped = getattr(address, "ipv4_mapped", None)
                local_host = local_host or address.is_loopback or address.is_unspecified or bool(mapped is not None and mapped.is_loopback)
            if (parsed.scheme not in {"mongodb", "mongodb+srv"} or not tls
                    or local_host
                    or any(query.get(k) == ["true"] for k in ("tlsallowinvalidcertificates", "tlsallowinvalidhostnames", "tlsinsecure"))
                    or query.get("tls") == ["false"] or query.get("ssl") == ["false"]):
                errors.append("RELEASE_REQUIRES_REMOTE_TLS_MONGODB")
        except ValueError:
            errors.append("RELEASE_REQUIRES_REMOTE_TLS_MONGODB")
    storage = (env.get("STORAGE_BACKEND") or "emergent").strip().lower()
    if storage == "vercel_blob" and not (env.get("BLOB_READ_WRITE_TOKEN") or "").startswith("vercel_blob_rw_"):
        errors.append("PRIVATE_BLOB_TOKEN_REQUIRED")
    if storage not in {"local", "emergent", "vercel_blob"}:
        errors.append("STORAGE_BACKEND_INVALID")
    if env.get("RENDER") == "true":
        if storage == "local":
            errors.append("RENDER_FREE_CANNOT_PRESERVE_LOCAL_MEDIA")
        if not enabled(env.get("DATA_IMPORT_CONFIRMED")):
            errors.append("DATA_IMPORT_AND_HISTORY_RECONCILIATION_REQUIRED")
    if (env.get("ROAST_WRITER_PROVIDER", "openrouter") != "openrouter"
            or env.get("ROAST_WRITER_PROFILE", "multimodal") != "multimodal"
            or enabled(env.get("ROAST_FREE_WRITER_ONLY"))):
        errors.append("RELEASE_REQUIRES_APPROVED_MULTIMODAL_WRITER")
    models = csv(env.get("ROAST_OPENROUTER_MODELS", "anthropic/claude-sonnet-4.5,openai/gpt-4.1,openai/gpt-4o"))
    if models != ("anthropic/claude-sonnet-4.5", "openai/gpt-4.1", "openai/gpt-4o"):
        errors.append("APPROVED_WRITER_ORDER_REQUIRED")
    if s.environment == "beta" and any(enabled(env.get(k)) for k in ("ENABLE_PREVIEW_LOGIN", "ALLOW_PREVIEW_HOSTED_AI")):
        if not all(enabled(env.get(k)) for k in ("ENABLE_PREVIEW_LOGIN", "ALLOW_PREVIEW_HOSTED_AI", "PREVIEW_UNLIMITED_CREDITS")):
            errors.append("BETA_EXPLORE_REQUIRES_EXPLICIT_UNLIMITED_PREVIEW_CONFIGURATION")
        if any(str(env.get(k, "-1")).strip() != "-1" for k in ("PREVIEW_HOSTED_DAILY_SHOW_LIMIT", "PREVIEW_HOSTED_DAILY_VOICE_LIMIT")):
            errors.append("BETA_PREVIEW_MUST_NOT_HAVE_APP_DAILY_GENERATION_LIMITS")
    return errors


def enforce_runtime(env: Mapping[str, str]) -> RuntimeSecurity:
    errors = configuration_errors(env)
    if errors:
        raise RuntimeError("Unsafe release configuration: " + ", ".join(errors))
    return RuntimeSecurity.from_environ(env)


class AuditJSONFormatter(logging.Formatter):
    """Serialize only fixed, non-user-content fields supplied by this module."""
    def format(self, record: logging.LogRecord) -> str:
        allowed = {"event", "request_id", "method", "route", "status", "duration_ms", "error_type"}
        fields = {k: v for k, v in getattr(record, "audit_fields", {}).items() if k in allowed}
        return json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                           "level": record.levelname, **fields}, separators=(",", ":"))


def configure_audit_logging(*, release_mode: bool = False) -> logging.Logger:
    audit = logging.getLogger("roastbox.audit")
    if not audit.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(AuditJSONFormatter())
        audit.addHandler(handler)
    audit.setLevel(logging.INFO)
    audit.propagate = False
    # Third-party INFO request logs can contain raw query strings/payment IDs.
    # Suppress them in development too; our route-template events replace them.
    for name in ("httpx", "httpcore", "httpx2", "httpcore2", "stripe"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True
    return audit


class RequestSecurityMiddleware:
    """Streaming ASGI wrapper: no request/response-body inspection or buffering.

    No IP, email, query string, credentials, subject photos, prompts, transcripts,
    arbitrary client request IDs, or literal resource IDs enter the audit event.
    The resolved route template is used instead of the raw request path.
    """
    def __init__(self, app, *, release_mode: bool = False):
        self.app = app
        self.release_mode = release_mode
        self.log = configure_audit_logging(release_mode=release_mode)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.perf_counter()
        status = 500
        started = False
        error_type = None

        async def secured_send(message):
            nonlocal status, started
            if message["type"] == "http.response.start":
                status, started = message["status"], True
                headers = list(message.get("headers", []))
                replace = {b"x-request-id": request_id.encode(),
                           b"x-content-type-options": b"nosniff",
                           b"referrer-policy": b"no-referrer",
                           b"permissions-policy": b"geolocation=()"}
                if scope.get("path", "").startswith("/api/") or any(k.lower() == b"set-cookie" for k, _ in headers):
                    replace[b"cache-control"] = b"private, no-store"
                if self.release_mode:
                    replace[b"content-security-policy"] = b"base-uri 'self'; object-src 'none'; frame-ancestors 'none'"
                    replace[b"x-frame-options"] = b"DENY"
                    if scope.get("scheme") == "https":
                        replace[b"strict-transport-security"] = b"max-age=31536000"
                headers = [(k, v) for k, v in headers if k.lower() not in replace]
                headers.extend(replace.items())
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, secured_send)
        except Exception as exc:
            error_type = type(exc).__name__
            if not self.release_mode or started:
                raise
            body = json.dumps({"detail": "An internal error occurred. Contact support with the request ID.",
                               "request_id": request_id}).encode()
            await secured_send({"type": "http.response.start", "status": 500,
                                "headers": [(b"content-type", b"application/json")]})
            await secured_send({"type": "http.response.body", "body": body})
        finally:
            route = getattr(scope.get("route"), "path", None)
            # Route templates come from developer code, not path/query parameters.
            fields = {"event": "http.request", "request_id": request_id,
                      "method": scope.get("method") if scope.get("method") in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"} else "OTHER", "route": route or "<unmatched>",
                      "status": status, "duration_ms": round((time.perf_counter() - start) * 1000, 2)}
            if error_type:
                fields["error_type"] = error_type
            self.log.log(logging.ERROR if status >= 500 else logging.INFO, "http.request", extra={"audit_fields": fields})
