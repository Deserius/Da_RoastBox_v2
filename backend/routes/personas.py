"""Persona catalog + cached voice previews."""
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from auth_deps import get_current_user, get_optional_user
from config import DATA_DIR, EMERGENT_LLM_KEY, OPENAI_API_KEY, ELEVENLABS_API_KEY
from db import (users_collection, voice_previews_collection, voice_preview_samples_collection,
                voice_preview_leases_collection)
from models import User
from services.preview_budget import consume_preview_hosted

router = APIRouter(prefix="/personas", tags=["personas"])

_PERSONAS = json.loads((DATA_DIR / "personas.json").read_text())
_BY_ID = {p["id"]: p for p in _PERSONAS}
_PRIVATE_FIELDS = {"voice_direction", "elevenlabs", "tts_voice", "tts_voice_hd"}
PREVIEW_VERSION = "v2"
_preview_locks: dict = {}


async def _acquire_voice_lease(persona_id: str, sample: int):
    """Serialize the same uncached sample across API workers, not just this process."""
    key = f"{persona_id}:{sample}:{PREVIEW_VERSION}"
    owner = uuid4().hex
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        now = datetime.now(timezone.utc)
        try:
            lease = await voice_preview_leases_collection.find_one_and_update(
                {"_id": key, "$or": [{"expires_at": {"$lte": now}}, {"expires_at": {"$exists": False}}]},
                {"$set": {"owner": owner, "expires_at": now + timedelta(minutes=5)}},
                upsert=True, return_document=ReturnDocument.AFTER,
            )
            if lease and lease.get("owner") == owner:
                return key, owner
        except DuplicateKeyError:
            pass  # A different worker owns the lease until it finishes or expires.
        await asyncio.sleep(0.2)
    raise HTTPException(status_code=409, detail="This voice sample is being prepared. Please try again shortly.")


def _public(p: dict, unlocked: bool) -> dict:
    item = {k: v for k, v in p.items() if k not in _PRIVATE_FIELDS}
    item["is_premium"] = p.get("tier") == "premium"
    item["locked"] = item["is_premium"] and not unlocked
    return item


@router.get("")
async def list_personas(current_user: Optional[User] = Depends(get_optional_user)):
    unlocked = bool(current_user and (current_user.premium_personas_unlocked or
                                       current_user.lifetime_founder or current_user.plan_tier == "vip"))
    return {"personas": [_public(p, unlocked) for p in _PERSONAS], "premium_unlocked": unlocked}


@router.get("/favorites")
async def list_favorites(current_user: User = Depends(get_current_user)):
    return {"favorites": [pid for pid in current_user.favorite_persona_ids if pid in _BY_ID]}


@router.put("/favorites/{persona_id}")
async def add_favorite(persona_id: str, current_user: User = Depends(get_current_user)):
    if persona_id not in _BY_ID:
        raise HTTPException(status_code=404, detail="Unknown persona")
    await users_collection.update_one({"id": current_user.id}, {"$addToSet": {"favorite_persona_ids": persona_id}})
    return {"persona_id": persona_id, "favorite": True}


@router.delete("/favorites/{persona_id}")
async def remove_favorite(persona_id: str, current_user: User = Depends(get_current_user)):
    if persona_id not in _BY_ID:
        raise HTTPException(status_code=404, detail="Unknown persona")
    await users_collection.update_one({"id": current_user.id}, {"$pull": {"favorite_persona_ids": persona_id}})
    return {"persona_id": persona_id, "favorite": False}


@router.get("/{persona_id}/voice-preview")
async def voice_preview(persona_id: str, sample: int = Query(0, ge=0), current_user: Optional[User] = Depends(get_optional_user)):
    """Play a catalog punchline. Each sample is generated on demand and cached."""
    p = _BY_ID.get(persona_id)
    if not p:
        raise HTTPException(status_code=404, detail="Unknown persona")
    samples = p.get("punchlines") or [p.get("tagline", "")]
    if sample >= len(samples):
        raise HTTPException(status_code=404, detail="Unknown voice sample")
    line = samples[sample]
    # Sample zero keeps the existing v2 filenames/documents; additional samples
    # use a separate collection and never invalidate the original cache.
    collection = voice_previews_collection if sample == 0 else voice_preview_samples_collection
    key = {"persona_id": persona_id} if sample == 0 else {"persona_id": persona_id, "sample": sample}
    filename = f"preview_{persona_id}_{PREVIEW_VERSION}{'' if sample == 0 else f'_s{sample}'}.mp3"
    async def is_cached():
        doc = await collection.find_one({**key, "version": PREVIEW_VERSION})
        if not doc:
            return False
        from services.storage import load_audio
        return await load_audio(doc.get("filename") or filename) is not None

    lock = _preview_locks.setdefault((persona_id, sample), asyncio.Lock())
    async with lock:
        if not await is_cached():
            if not current_user:
                raise HTTPException(status_code=401, detail="Sign in to generate a voice preview.")
            lease_key, owner = await _acquire_voice_lease(persona_id, sample)
            try:
                # Another worker may have completed the sample while we waited.
                if not await is_cached():
                    from services.voice_orchestrator import synthesize_line
                    from services import roast_engine as eng
                    beat = {"type": "punchline", "emotion": "cocky", "delivery": "signature line, sell it to the back row"}
                    byok_openai, byok_eleven = eng.user_byok(current_user)
                    preview = bool(current_user.is_preview)
                    premium = bool(eng.has_premium_voices(current_user) and not preview)
                    hosted_available = not preview and (EMERGENT_LLM_KEY or OPENAI_API_KEY or (premium and ELEVENLABS_API_KEY))
                    preview_hosted = False
                    if preview and not (byok_openai or byok_eleven):
                        await consume_preview_hosted("voice")
                        preview_hosted = True
                    if not (byok_openai or byok_eleven or hosted_available or preview_hosted):
                        raise HTTPException(status_code=503, detail="Voice preview requires an OpenAI or ElevenLabs key in Settings, or configured hosted AI credentials.")
                    try:
                        await synthesize_line(line, persona_id, p, byok_eleven, byok_openai,
                                              premium_voices_unlocked=premium, beat=beat, filename=filename,
                                              allow_hosted_openai=not preview or preview_hosted)
                    except Exception as e:
                        raise HTTPException(status_code=503, detail="Voice preview unavailable. Check your voice provider configuration.") from e
                    await collection.update_one(
                        key,
                        {"$set": {**key, "version": PREVIEW_VERSION, "filename": filename, "text": line}},
                        upsert=True)
            finally:
                await voice_preview_leases_collection.delete_one({"_id": lease_key, "owner": owner})
    return {"audio_url": f"/api/audio/{filename}", "text": line, "sample": sample}


def get_personas_by_ids(ids):
    return [_BY_ID[i] for i in ids if i in _BY_ID]


def all_personas():
    return _PERSONAS
