"""Health + diagnostics endpoints. Deep checks make live calls to each provider."""
import asyncio
import logging
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from auth_deps import get_optional_user
from models import User

from services.runtime_settings import secret_cached
from config import (APP_VERSION, ALLOW_DEV_LOGIN, ALLOW_SOURCE_DOWNLOAD, ENABLE_PREVIEW_LOGIN,
                    ALLOW_PREVIEW_HOSTED_AI, PREVIEW_HOSTED_DAILY_SHOW_LIMIT, PREVIEW_HOSTED_DAILY_VOICE_LIMIT,
                    PREVIEW_UNLIMITED_CREDITS, ALLOW_RUNTIME_SETTINGS,
                    STORAGE_BACKEND, AUDIO_DIR, DATA_DIR)
from db import db
from routes.personas import all_personas

log = logging.getLogger(__name__)
router = APIRouter(tags=["diagnostics"])

DEEP_CACHE_SECONDS = 600
_deep_cache: dict = {"at": 0.0, "checks": None}


async def _timed(coro):
    start = time.perf_counter()
    try:
        detail = await coro
        return {"ok": True, "ms": round((time.perf_counter() - start) * 1000), "detail": detail}
    except Exception as e:
        return {"ok": False, "ms": round((time.perf_counter() - start) * 1000), "error": str(e)[:300]}


async def _check_mongo():
    await db.command("ping")
    return "ping ok"


async def _check_llm():
    from services.openai_service import get_client
    client = get_client(timeout=30)
    resp = await asyncio.to_thread(
        client.chat.completions.create, model="gpt-4o", max_tokens=5,
        messages=[{"role": "user", "content": "Reply with: ok"}],
    )
    return (resp.choices[0].message.content or "").strip()


async def _check_tts():
    from services.openai_service import synthesize_tts_openai
    audio = await synthesize_tts_openai("Test.", voice="ash", instructions="Cocky comedian.")
    return f"{len(audio)} bytes mp3"


async def _check_stripe():
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    stripe_key, stripe_hook = secret_cached("STRIPE_API_KEY"), secret_cached("STRIPE_WEBHOOK_SECRET")
    if not stripe_key or not stripe_hook:
        raise RuntimeError("Both STRIPE_API_KEY and STRIPE_WEBHOOK_SECRET are required for checkout")
    StripeCheckout(api_key=stripe_key, webhook_secret=stripe_hook, webhook_url=None)
    # Initialising a client does not validate credentials; query the account instead.
    import stripe
    await asyncio.to_thread(stripe.Account.retrieve)
    return "Stripe account reachable"


async def _check_storage():
    from services.storage import init_storage
    if not await init_storage():
        raise RuntimeError("Configured storage is not available")
    return f"{STORAGE_BACKEND} storage ready"


async def _check_elevenlabs():
    from services.elevenlabs_service import check_elevenlabs_key
    await check_elevenlabs_key(secret_cached("ELEVENLABS_API_KEY"))
    return "key valid"


def _persona_integrity():
    personas = all_personas()
    public_dir = DATA_DIR.parent.parent / "frontend" / "public"
    missing_img = [p["id"] for p in personas if not (public_dir / p["image"]).exists()] if public_dir.exists() else []
    missing_voice = [p["id"] for p in personas if not p.get("tts_voice") or not p.get("elevenlabs")]
    return {
        "total": len(personas),
        "free": sum(p.get("tier") != "premium" for p in personas),
        "premium": sum(p.get("tier") == "premium" for p in personas),
        "missing_images": missing_img,
        "missing_voice_config": missing_voice,
    }


async def _deep_checks() -> dict:
    """Live provider calls, cached so repeated requests can't burn LLM budget."""
    if _deep_cache["checks"] and time.time() - _deep_cache["at"] < DEEP_CACHE_SECONDS:
        return {**_deep_cache["checks"], "cached": {"ok": True, "age_s": round(time.time() - _deep_cache["at"])}}
    tasks = {"llm": _check_llm(), "tts": _check_tts(), "stripe": _check_stripe(), "storage": _check_storage()}
    if secret_cached("ELEVENLABS_API_KEY"):
        tasks["elevenlabs"] = _check_elevenlabs()
    results = dict(zip(tasks.keys(), await asyncio.gather(*[_timed(c) for c in tasks.values()])))
    _deep_cache.update(at=time.time(), checks=results)
    return results


@router.get("/health")
async def health():
    return {"status": "ok", "version": APP_VERSION}


@router.get("/diagnostics")
async def diagnostics(deep: bool = False, user: Optional[User] = Depends(get_optional_user)):
    """Config summary; `?deep=true` (signed-in only) performs live provider calls."""
    if deep and not user:
        raise HTTPException(status_code=401, detail="Sign in to run deep diagnostics")
    if deep and user and user.is_preview:
        raise HTTPException(status_code=403, detail="Live provider diagnostics are disabled for preview accounts.")
    # Report what is actually in effect, including keys entered in the settings
    # console, so the UI never claims a provider is missing when it is usable.
    emergent_key = secret_cached("EMERGENT_LLM_KEY")
    openai_key = secret_cached("OPENAI_API_KEY")
    stripe_key = secret_cached("STRIPE_API_KEY")
    stripe_hook = secret_cached("STRIPE_WEBHOOK_SECRET")
    eleven_key = secret_cached("ELEVENLABS_API_KEY")
    openrouter_key = secret_cached("OPENROUTER_API_KEY")
    report = {
        "version": APP_VERSION,
        "config": {
            "emergent_llm_key": bool(emergent_key),
            "openai_hosted_key": bool(openai_key),
            "openrouter_key": bool(openrouter_key),
            "stripe_api_key": bool(stripe_key),
            "elevenlabs_hosted_key": bool(eleven_key),
            "dev_login_enabled": ALLOW_DEV_LOGIN,
            "source_download_enabled": ALLOW_SOURCE_DOWNLOAD,
            "preview_login_enabled": ENABLE_PREVIEW_LOGIN,
            "preview_hosted_ai_enabled": ENABLE_PREVIEW_LOGIN and ALLOW_PREVIEW_HOSTED_AI and bool(emergent_key or openai_key or openrouter_key),
            "preview_hosted_daily_show_limit": "unlimited" if PREVIEW_HOSTED_DAILY_SHOW_LIMIT < 0 else PREVIEW_HOSTED_DAILY_SHOW_LIMIT,
            "preview_hosted_daily_voice_limit": "unlimited" if PREVIEW_HOSTED_DAILY_VOICE_LIMIT < 0 else PREVIEW_HOSTED_DAILY_VOICE_LIMIT,
            "preview_unlimited_credits": PREVIEW_UNLIMITED_CREDITS,
            "storage_backend": STORAGE_BACKEND,
            "stripe_webhook_secret": bool(stripe_hook),
            "runtime_settings_enabled": bool(ALLOW_RUNTIME_SETTINGS),
            "audio_cache_writable": AUDIO_DIR.exists(),
        },
        "personas": _persona_integrity(),
        "checks": {"mongo": await _timed(_check_mongo())},
    }
    if deep:
        report["checks"].update(await _deep_checks())
    report["warnings"] = []
    if not (emergent_key or openai_key or openrouter_key):
        report["warnings"].append("Hosted AI key missing; configure OpenAI/Emergent or use a personal key in Settings.")
    if not stripe_key:
        report["warnings"].append("Stripe API key missing; checkout is disabled.")
    if not stripe_hook:
        report["warnings"].append("Stripe webhook signing secret missing; checkout and webhooks are disabled.")
    report["status"] = "ok" if not report["warnings"] and all(c["ok"] for c in report["checks"].values()) else "degraded"
    return report
