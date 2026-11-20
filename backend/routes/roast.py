"""Roast generation: vision-driven structured script + multi-voice expressive TTS + credit cost engine."""
import logging
import secrets
import time
import asyncio
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pymongo import ReturnDocument

from auth_deps import get_current_user
from config import ROAST_WRITER_PROVIDER, PREVIEW_UNLIMITED_CREDITS
from models import User, RoastRecord
from db import roasts_collection
from services.pricing import compute_roast_cost, ROAST_COSTS
from services.runtime_settings import setting_cached
from services.preview_budget import consume_preview_hosted
from services.roast_writer import parse_comedy_styles, _target_beats, build_roast_prompt, finish_roast_script, highest_unlocked_heat, normalize_heat, write_script
from services.voice_orchestrator import synthesize_beat, synthesize_show, voice_beats_progressive
from services import roast_engine as eng
from routes.personas import get_personas_by_ids

log = logging.getLogger(__name__)
router = APIRouter(prefix="/roast", tags=["roast"])

MAX_PERSONAS = 5


@router.get("/cost-quote")
async def cost_quote(roast_tier: str = "standard", premium_voice: bool = False, premium_persona: bool = False,
                     hd_export: bool = False, current_user: User = Depends(get_current_user)):
    cost = compute_roast_cost(roast_tier=roast_tier, uses_premium_voice=premium_voice,
                              uses_premium_persona=premium_persona, hd_export=hd_export)
    free_available = (roast_tier == "standard" and not premium_voice and not premium_persona and not hd_export
                      and current_user.last_free_roast_date != eng.today_utc())
    return {"credit_cost": cost, "free_available": free_available, "credits_balance": current_user.credits,
            "plan_tier": current_user.plan_tier, "roast_costs": ROAST_COSTS}


@router.post("/generate")
async def generate_roast(
    persona_ids: str = Form(..., max_length=200),
    subject_name: Optional[str] = Form(None, max_length=120),
    user_context: Optional[str] = Form(None, max_length=3000),
    off_limits: Optional[str] = Form(None, max_length=600),
    comedy_styles: Optional[str] = Form(None, max_length=400),
    duration_minutes: int = Form(3),
    roast_tier: str = Form("standard"),
    use_premium_voice: bool = Form(False),
    hd_export: bool = Form(False),
    heat: Optional[str] = Form(None),
    adult_language: bool = Form(True),
    images: List[UploadFile] = File(default=[]),
    current_user: User = Depends(eng.locked_generation_user),
):
    ids = [p.strip() for p in persona_ids.split(",") if p.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="Select at least one roaster")
    if len(ids) > MAX_PERSONAS or len(set(ids)) != len(ids):
        raise HTTPException(status_code=400, detail=f"Choose up to {MAX_PERSONAS} different roasters")
    personas = get_personas_by_ids(ids)
    if len(personas) != len(ids):
        raise HTTPException(status_code=400, detail="Unknown personas")
    uses_premium_persona = eng.check_persona_access(current_user, personas)
    heat = normalize_heat(heat) if heat is not None else highest_unlocked_heat(
        current_user.nsfw_edgier_unlocked or current_user.lifetime_founder)
    eng.check_heat_access(current_user, heat)
    if use_premium_voice and not eng.has_premium_voices(current_user):
        raise HTTPException(status_code=402, detail="Premium voices locked. Unlock Premium Voices Bundle or subscribe to RoastBox Plus/VIP.")
    if not images:
        raise HTTPException(status_code=400, detail="At least one subject image required")

    duration_minutes = max(3, min(10, int(duration_minutes or 3)))
    roast_tier = roast_tier if roast_tier in ("standard", "premium") else "standard"
    cost = compute_roast_cost(roast_tier=roast_tier, uses_premium_voice=use_premium_voice,
                              uses_premium_persona=uses_premium_persona, hd_export=hd_export)
    free = (roast_tier == "standard" and not use_premium_voice and not uses_premium_persona and not hd_export
            and current_user.last_free_roast_date != eng.today_utc())
    if current_user.is_preview and PREVIEW_UNLIMITED_CREDITS:
        # Preview accounts cannot purchase credits, so generation is not credit
        # limited. It is billed at zero rather than as the daily free roast, so
        # the once-per-day allowance is not consumed and nothing is capped.
        free, cost = False, 0
    if free:
        cost = 0
    elif current_user.credits < cost:
        raise HTTPException(status_code=402, detail=f"Not enough credits — this roast costs {cost}. You have {current_user.credits}.")

    try:
        styles = parse_comedy_styles(comedy_styles)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    img_bytes, img_types = await eng.read_images(images)
    byok_openai, byok_eleven = eng.user_byok(current_user)
    # A preview account spending its own OpenAI key consumes no shared budget,
    # so it is metered only when the hosted credentials will actually be used.
    writer_provider = setting_cached("ROAST_WRITER_PROVIDER", ROAST_WRITER_PROVIDER)
    if current_user.is_preview and (not byok_openai or writer_provider == "openrouter"):
        await consume_preview_hosted("show", using_own_key=bool(byok_openai))
    prompt = build_roast_prompt(personas, subject_name, user_context, duration_minutes, roast_tier == "premium",
                                current_user.nsfw_edgier_unlocked or current_user.lifetime_founder,
                                heat=heat, adult=adult_language, n_images=len(img_bytes), off_limits=off_limits, styles=styles)
    _pipeline_start = time.monotonic()
    meta_by_id = {p["id"]: p for p in personas}
    premium_voices = (use_premium_voice or eng.has_premium_voices(current_user)) and not current_user.is_preview
    # Start voice work on each beat as it streams instead of waiting for the full script.
    started: Dict[str, asyncio.Task] = {}

    def _start(beat):
        key = beat["text"]
        if key not in started:
            started[key] = asyncio.create_task(synthesize_beat(
                beat, meta_by_id, byok_eleven=byok_eleven, byok_openai=byok_openai,
                premium_voices=premium_voices))

    async def _on_beat(beat):
        _start(beat)

    try:
        written = await write_script(prompt, personas, img_bytes, img_types, byok_openai,
                                     expected_beats=_target_beats(duration_minutes),
                                     adult=adult_language, off_limits=off_limits,
                                     roast_tier=roast_tier, on_beat=_on_beat)
        beats = finish_roast_script(written, personas, subject_name, _target_beats(duration_minutes) + 1,
                                    adult=adult_language, off_limits=off_limits)
        if not beats:
            raise RuntimeError("Roast model returned an empty script")
    except Exception as e:
        for task in started.values():
            task.cancel()
        started.clear()
        log.exception("Roast generation failed")
        raise eng.friendly_ai_error(e)

    log.info("roast_timing script_ms=%d beats=%d", round((time.monotonic() - _pipeline_start) * 1000), len(beats))
    transcript, providers = await voice_beats_progressive(
        started, beats, meta_by_id, byok_eleven=byok_eleven, byok_openai=byok_openai,
        premium_voices=premium_voices)
    log.info("roast_timing total_ms=%d (script+voice)", round((time.monotonic() - _pipeline_start) * 1000))
    if not transcript or any(not beat.get("audio_url") for beat in transcript):
        # A paid result must not silently ship as a partial/silent show.
        raise HTTPException(status_code=503, detail="Voice generation failed. Check your OpenAI or ElevenLabs configuration; no credits were charged.")

    desc = (f"{roast_tier.capitalize()} Roast ({duration_minutes}min)" + (" +PremiumVoice" if use_premium_voice else "")
            + (" +PremiumPersona" if uses_premium_persona else "") + (" +HDExport" if hd_export else ""))
    record = RoastRecord(
        user_id=current_user.id, persona_ids=ids, subject_name=subject_name, user_context=user_context, off_limits=off_limits, comedy_styles=styles,
        heat=heat, adult_language=adult_language,
        image_count=len(img_bytes), duration_minutes=duration_minutes, roast_tier=roast_tier,
        used_premium_voice=use_premium_voice, used_premium_persona=uses_premium_persona, hd_export=hd_export,
        credits_spent=cost, was_free_roast=free, transcript=transcript, audio_provider=",".join(providers) or None,
    )
    remaining = await eng.commit_record(current_user, record, img_bytes,
                                        f"Daily free roast ({duration_minutes}min)" if free else desc)
    return {"roast_id": record.id, "persona_ids": ids, "transcript": transcript, "heat": heat, "adult_language": adult_language,
            "images": eng.subject_image_urls(record.id, len(img_bytes)), "audio_provider": record.audio_provider,
            "duration_minutes": duration_minutes, "roast_tier": roast_tier, "credits_spent": cost,
            "was_free_roast": free, "credits_remaining": remaining, "plan_tier": current_user.plan_tier}


@router.get("/history")
async def history(current_user: User = Depends(get_current_user)):
    cursor = roasts_collection.find({"user_id": current_user.id, "billing_state": eng.VISIBLE_BILLING},
                                     {"_id": 0, "billing_state": 0, "billing_version": 0,
                                      "billing_staged_at": 0, "billing_description": 0, "billing_free_date": 0}) \
                              .sort("created_at", -1).limit(50)
    return {"history": [d async for d in cursor]}


@router.post("/{roast_id}/share")
async def share_roast(roast_id: str, current_user: User = Depends(get_current_user)):
    doc = await roasts_collection.find_one({"id": roast_id, "user_id": current_user.id,
                                            "billing_state": eng.VISIBLE_BILLING}, {"share_id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Roast not found")
    share_id = doc.get("share_id")
    if not share_id:
        # Concurrent share clicks converge on one link rather than returning a
        # link overwritten by another request. Existing links are preserved.
        updated = await roasts_collection.find_one_and_update(
            {"id": roast_id, "user_id": current_user.id, "billing_state": eng.VISIBLE_BILLING,
             "$or": [{"share_id": {"$exists": False}}, {"share_id": None}, {"share_id": ""}]},
            {"$set": {"share_id": secrets.token_urlsafe(16)}}, return_document=ReturnDocument.AFTER,
        )
        doc = updated or await roasts_collection.find_one({"id": roast_id, "user_id": current_user.id,
                                                            "billing_state": eng.VISIBLE_BILLING})
        share_id = doc and doc.get("share_id")
        if not share_id:
            raise HTTPException(status_code=409, detail="Share link changed. Please try again.")
    return {"share_id": share_id, "share_path": f"/r/{share_id}"}


@router.delete("/{roast_id}/share")
async def unshare_roast(roast_id: str, current_user: User = Depends(get_current_user)):
    res = await roasts_collection.update_one({"id": roast_id, "user_id": current_user.id,
                                                "billing_state": eng.VISIBLE_BILLING}, {"$unset": {"share_id": ""}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Roast not found")
    return {"status": "ok"}
