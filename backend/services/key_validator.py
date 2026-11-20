"""Verify a provider credential before it is saved.

A saved key that is silently broken is worse than no key: the app keeps failing
in a way that looks like a bug rather than a configuration problem. So each
provider gets a real, read-only call.

Distinguishing three outcomes matters:

* ``valid``    - the provider accepted the credential.
* ``invalid``  - the provider rejected it; do not save.
* ``unchecked``- the provider could not be reached at all (sandbox with no
  outbound network). The key cannot be *confirmed*, but it is also not proven
  wrong, so the operator is told plainly and may keep it. Refusing to save here
  would make the app unusable in an offline workspace.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

log = logging.getLogger(__name__)

TIMEOUT_S = 12.0

VALID = "valid"
INVALID = "invalid"
UNCHECKED = "unchecked"


def _result(status: str, detail: str, **extra: Any) -> Dict[str, Any]:
    return {"status": status, "detail": detail, **extra}


async def _get(url: str, *, headers: Dict[str, str] | None = None) -> Dict[str, Any]:
    """Single-shot GET with a short timeout, mapping failures to a status."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=False) as client:
            response = await client.get(url, headers=headers or {})
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
            httpx.RemoteProtocolError, httpx.UnsupportedProtocol) as exc:
        return _result(UNCHECKED, f"Provider unreachable from this environment ({type(exc).__name__}).")
    except httpx.HTTPError as exc:
        return _result(UNCHECKED, f"Network error while checking ({type(exc).__name__}).")
    return {"status": "http", "detail": "", "status_code": response.status_code, "body": response}


async def _check_openai(key: str) -> Dict[str, Any]:
    if not key.startswith("sk-"):
        return _result(INVALID, "An OpenAI key starts with 'sk-'.")
    probe = await _get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"})
    if probe["status"] != "http":
        return probe
    code = probe["status_code"]
    if code == 200:
        return _result(VALID, "OpenAI accepted the key.")
    if code in (401, 403):
        return _result(INVALID, "OpenAI rejected this key (401/403).")
    return _result(UNCHECKED, f"OpenAI returned HTTP {code}; the key was not confirmed.")


async def _check_openrouter(key: str) -> Dict[str, Any]:
    if not key.startswith("sk-or-"):
        return _result(INVALID, "An OpenRouter key starts with 'sk-or-'.")
    probe = await _get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"})
    if probe["status"] != "http":
        return probe
    code = probe["status_code"]
    if code == 200:
        body = probe["body"]
        try:
            info = body.json().get("data") or {}
            limit = info.get("limit")
            usage = info.get("usage")
            note = ""
            if limit is not None and usage is not None:
                note = f" Credit limit {limit}; used {usage}."
            return _result(VALID, "OpenRouter accepted the key." + note)
        except Exception:
            return _result(VALID, "OpenRouter accepted the key.")
    if code in (401, 403):
        return _result(INVALID, "OpenRouter rejected this key (401/403).")
    return _result(UNCHECKED, f"OpenRouter returned HTTP {code}; the key was not confirmed.")


async def _check_elevenlabs(key: str) -> Dict[str, Any]:
    probe = await _get("https://api.elevenlabs.io/v1/user", headers={"xi-api-key": key})
    if probe["status"] != "http":
        return probe
    code = probe["status_code"]
    if code == 200:
        return _result(VALID, "ElevenLabs accepted the key.")
    if code in (401, 403):
        return _result(INVALID, "ElevenLabs rejected this key (401/403).")
    return _result(UNCHECKED, f"ElevenLabs returned HTTP {code}; the key was not confirmed.")


async def _check_stripe(key: str) -> Dict[str, Any]:
    if not key.startswith(("sk_", "rk_")):
        return _result(INVALID, "A Stripe secret key starts with 'sk_' or 'rk_'.")
    probe = await _get("https://api.stripe.com/v1/balance", headers={"Authorization": f"Bearer {key}"})
    if probe["status"] != "http":
        return probe
    code = probe["status_code"]
    if code == 200:
        mode = "live" if key.startswith(("sk_live_", "rk_live_")) else "test"
        return _result(VALID, f"Stripe accepted the key ({mode} mode).", mode=mode)
    if code in (401, 403):
        return _result(INVALID, "Stripe rejected this key (401/403).")
    return _result(UNCHECKED, f"Stripe returned HTTP {code}; the key was not confirmed.")


async def _check_stripe_webhook(secret: str) -> Dict[str, Any]:
    """A webhook secret is not a credential a provider will validate for us.

    It is a shared HMAC secret created alongside a specific endpoint, so the only
    thing worth checking is that it has the documented shape.
    """
    if not secret.startswith("whsec_"):
        return _result(INVALID, "A Stripe webhook secret starts with 'whsec_'.")
    if len(secret) < 20:
        return _result(INVALID, "That webhook secret looks truncated.")
    return _result("shape-ok", "Webhook secret has the expected shape. It is verified when Stripe sends its first event.")


async def _check_google_client_id(value: str) -> Dict[str, Any]:
    if not value.endswith(".apps.googleusercontent.com") or not value[:-len(".apps.googleusercontent.com")].strip():
        return _result(INVALID, "A Google client ID ends with '.apps.googleusercontent.com'.")
    return _result("shape-ok", "Client ID has the expected format.")


async def _check_google_client_secret(value: str) -> Dict[str, Any]:
    if not value.startswith("GOCSPX-"):
        return _result(INVALID, "A Google client secret starts with 'GOCSPX-'.")
    return _result("shape-ok", "Client secret has the expected format.")


async def _check_emergent(key: str) -> Dict[str, Any]:
    probe = await _get("https://integrations.emergentagent.com/llm/v1/models",
                       headers={"Authorization": f"Bearer {key}"})
    if probe["status"] != "http":
        return probe
    code = probe["status_code"]
    if code == 200:
        return _result(VALID, "Emergent gateway accepted the key.")
    if code in (401, 403):
        return _result(INVALID, "Emergent gateway rejected this key.")
    return _result(UNCHECKED, f"Emergent gateway returned HTTP {code}; the key was not confirmed.")


async def _check_blob(token: str) -> Dict[str, Any]:
    if not token.startswith("vercel_blob_rw_"):
        return _result(INVALID, "A Vercel Blob token starts with 'vercel_blob_rw_'.")
    probe = await _get("https://blob.vercel-storage.com/")
    if probe["status"] != "http":
        return probe
    return _result(UNCHECKED, "Vercel Blob has no read-only probe; confirmed on the first upload.")


async def _check_model_id(value: str) -> Dict[str, Any]:
    """Model IDs are validated by shape here and by the writer at first use."""
    if not value or len(value) > 160 or " " in value:
        return _result(INVALID, "A model ID looks like 'vendor/model' with no spaces.")
    if "/" not in value:
        return _result(INVALID, "An OpenRouter model ID is 'vendor/model'.")
    return _result("shape-ok", "Model ID format looks right.")


_CHECKS = {
    "OPENAI_API_KEY": _check_openai,
    "OPENROUTER_API_KEY": _check_openrouter,
    "ELEVENLABS_API_KEY": _check_elevenlabs,
    "EMERGENT_LLM_KEY": _check_emergent,
    "STRIPE_API_KEY": _check_stripe,
    "STRIPE_WEBHOOK_SECRET": _check_stripe_webhook,
    "BLOB_READ_WRITE_TOKEN": _check_blob,
    "GOOGLE_CLIENT_ID": _check_google_client_id,
    "GOOGLE_CLIENT_SECRET": _check_google_client_secret,
    "ROAST_WRITER_MODEL": _check_model_id,
    "ROAST_FREE_PREMIUM_MODEL": _check_model_id,
    "ROAST_FREE_BACKUP_MODEL": _check_model_id,
    "ROAST_PAID_PRIMARY_MODEL": _check_model_id,
    "ROAST_PAID_STANDARD_MODEL": _check_model_id,
    "ROAST_PAID_BACKUP_MODEL": _check_model_id,
}


def blocking_status(status: str) -> bool:
    """Only a provider rejection should stop a save."""
    return status == INVALID


async def validate(key: str, value: str) -> Dict[str, Any]:
    """Check one field. Unknown fields are accepted by shape only."""
    value = (value or "").strip()
    if not value:
        return _result(INVALID, "Value is empty.")
    checker = _CHECKS.get(key)
    if checker is None:
        return _result("shape-ok", "No automatic check is available for this field.")
    try:
        return await checker(value)
    except Exception as exc:  # a validator must never break a save by crashing
        log.warning("Validation for %s raised %s", key, type(exc).__name__)
        return _result(UNCHECKED, f"Could not validate ({type(exc).__name__}); the key was not confirmed.")


async def validate_many(values: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """Validate several fields concurrently, preserving key order."""
    keys = list(values)
    results = await asyncio.gather(*(validate(k, values[k]) for k in keys))
    return dict(zip(keys, results))
