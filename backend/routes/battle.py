"""Roast Battle Mode: 1v1 persona duel, crowd reactions decide the winner."""
import logging
import random
from pathlib import Path
import asyncio
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from auth_deps import get_current_user
from config import ROAST_WRITER_PROVIDER, PREVIEW_UNLIMITED_CREDITS
from models import User, RoastRecord
from services.pricing import ROAST_COSTS
from services.preview_budget import consume_preview_hosted
from services.roast_writer import parse_comedy_styles, battle_beats, build_battle_prompt, highest_unlocked_heat, normalize_heat, write_script
from services.voice_orchestrator import synthesize_beat, voice_beats_progressive
from services import roast_engine as eng
from routes.personas import get_personas_by_ids

log = logging.getLogger(__name__)
router = APIRouter(prefix="/battle", tags=["battle"])

LAUGH_POINTS = {"none": 0, "small": 1, "medium": 2, "big": 4, "explosive": 6}
REACTION_BONUS = {"ooh": 1, "cheer": 1, "groan": -1, "laugh": 0}


def battle_cost(uses_premium_persona: bool) -> int:
    return ROAST_COSTS["standard_roast"] + (ROAST_COSTS["premium_persona"] if uses_premium_persona else 0)


def score_battle(beats: List[dict], a_id: str, b_id: str, rng: random.Random) -> dict:
    scores = {a_id: 0, b_id: 0}
    for b in beats:
        if b["persona_id"] in scores:
            scores[b["persona_id"]] += LAUGH_POINTS.get(b["laugh_after"], 0) + REACTION_BONUS.get(b.get("reaction"), 0)
    # Crowd applause vote: small jitter so close fights feel live.
    for k in scores:
        scores[k] += rng.randint(0, 3)
    if scores[a_id] == scores[b_id]:
        scores[rng.choice([a_id, b_id])] += 1
    winner = max(scores, key=scores.get)
    return {"scores": scores, "winner": winner}


def has_battle_access(user: User) -> bool:
    return user.roast_battle_unlocked or user.lifetime_founder


@router.get("/access")
async def battle_access(current_user: User = Depends(get_current_user)):
    return {"unlocked": has_battle_access(current_user), "base_cost": ROAST_COSTS["standard_roast"],
            "premium_persona_cost": ROAST_COSTS["premium_persona"]}


@router.post("/generate")
async def generate_battle(
    persona_a: str = Form(..., max_length=64),
    persona_b: str = Form(..., max_length=64),
    rounds: int = Form(3),
    battle_style: str = Form("classic", max_length=20),
    subject_name: Optional[str] = Form(None, max_length=120),
    user_context: Optional[str] = Form(None, max_length=3000),
    off_limits: Optional[str] = Form(None, max_length=600),
    comedy_styles: Optional[str] = Form(None, max_length=400),
    heat: Optional[str] = Form(None),
    adult_language: bool = Form(True),
    images: List[UploadFile] = File(default=[]),
    current_user: User = Depends(eng.locked_generation_user),
):
    if battle_style not in ("classic", "rap"):
        raise HTTPException(status_code=422, detail="Unknown battle style")
    if not has_battle_access(current_user):
        raise HTTPException(status_code=402, detail="Roast Battle Mode is locked. Unlock it on the Credits page.")
    if persona_a == persona_b:
        raise HTTPException(status_code=400, detail="Pick two different fighters")
    fighters = get_personas_by_ids([persona_a, persona_b])
    if len(fighters) != 2:
        raise HTTPException(status_code=400, detail="Unknown fighters")
    uses_premium = eng.check_persona_access(current_user, fighters)
    heat = normalize_heat(heat) if heat is not None else highest_unlocked_heat(
        current_user.nsfw_edgier_unlocked or current_user.lifetime_founder)
    eng.check_heat_access(current_user, heat)
    cost = battle_cost(uses_premium)
    if current_user.is_preview and PREVIEW_UNLIMITED_CREDITS:
        cost = 0
    if cost and current_user.credits < cost:
        raise HTTPException(status_code=402, detail=f"Not enough credits — this battle costs {cost}. You have {current_user.credits}.")

    rounds = max(2, min(4, int(rounds or 3)))
    try:
        styles = parse_comedy_styles(comedy_styles)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    img_bytes, img_types = await eng.read_images(images)
    byok_openai, byok_eleven = eng.user_byok(current_user)
    if current_user.is_preview and (not byok_openai or ROAST_WRITER_PROVIDER == "openrouter"):
        await consume_preview_hosted("show")
    a, b = fighters
    portraits = []
    if battle_style == "rap":
        base = Path(__file__).resolve().parent.parent / "assets" / "personas"
        for fighter in fighters:
            path = base / Path(fighter.get("image") or "").name
            if path.is_file() and path.suffix.lower() == ".webp":
                portraits.append({"id": fighter["id"], "data": path.read_bytes(), "type": "image/webp"})
        if len(portraits) != 2:
            raise HTTPException(status_code=503, detail="Fighter portraits are unavailable; no credits were charged.")
    prompt = build_battle_prompt(a, b, rounds, subject_name, user_context, bool(img_bytes), False,
                                 current_user.nsfw_edgier_unlocked or current_user.lifetime_founder,
                                 heat=heat, adult=adult_language, n_images=len(img_bytes), off_limits=off_limits, styles=styles, rap=battle_style == "rap")
    meta_by_id = {p["id"]: p for p in fighters}
    premium_voices = eng.has_premium_voices(current_user) and not current_user.is_preview
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
        written = await write_script(prompt, fighters, img_bytes, img_types, byok_openai,
                                    expected_beats=battle_beats(rounds),
                                    adult=adult_language, off_limits=off_limits,
                                    persona_portraits=portraits, on_beat=_on_beat)
        beats = written[:battle_beats(rounds) + 2]
        for beat in beats:
            beat.pop("_standalone", None)
            if battle_style == "rap":
                beat["rap_delivery"] = True
                beat["rapid_fire"] = True
    except Exception as e:
        for task in started.values():
            task.cancel()
        started.clear()
        log.exception("Battle generation failed")
        raise eng.friendly_ai_error(e)

    transcript, providers = await voice_beats_progressive(
        started, beats, meta_by_id, byok_eleven=byok_eleven, byok_openai=byok_openai,
        premium_voices=premium_voices)
    if not transcript or any(not beat.get("audio_url") for beat in transcript):
        # A paid result must not silently ship as a partial/silent show.
        raise HTTPException(status_code=503, detail=(
            "Voice generation failed. Check your OpenAI or ElevenLabs configuration, or run "
            "scripts/setup_local_voice.py once to enable the free local voice fallback. "
            "No credits were charged."))
    result = score_battle(transcript, a["id"], b["id"], random.Random())

    record = RoastRecord(
        user_id=current_user.id, mode="battle", battle_style=battle_style, heat=heat, adult_language=adult_language, persona_ids=[a["id"], b["id"]], subject_name=subject_name,
        user_context=user_context, off_limits=off_limits, comedy_styles=styles, image_count=len(img_bytes), duration_minutes=rounds,
        used_premium_persona=uses_premium, credits_spent=cost, transcript=transcript,
        audio_provider=",".join(providers) or None, battle=result,
    )
    remaining = await eng.commit_record(current_user, record, img_bytes,
                                        f"Roast Battle: {a['displayName']} vs {b['displayName']}")
    return {"roast_id": record.id, "battle_style": battle_style, "transcript": transcript, "images": eng.subject_image_urls(record.id, len(img_bytes)), "battle": result, "credits_spent": cost,
            "credits_remaining": remaining, "audio_provider": record.audio_provider}
