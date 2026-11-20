"""Voice orchestrator: ElevenLabs v3 (BYOK or hosted key, emotion tags) → OpenAI expressive TTS fallback.

Per-persona voice config lives in data/personas.json (`tts_voice_hd`, `voice_direction`, `elevenlabs`).
"""
import asyncio
import hashlib
import logging
import time
import uuid
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from config import (AUDIO_DIR, ELEVENLABS_API_KEY, ROAST_TTS_CACHE, ROAST_TTS_CONCURRENCY,
                    ROAST_TTS_TIMEOUT_S)
from services.runtime_settings import secret_cached
from .openai_service import synthesize_tts_openai
from .elevenlabs_service import synthesize_tts_elevenlabs
from .storage import save_audio

log = logging.getLogger(__name__)

AUDIO_TTL_SECONDS = 7 * 24 * 3600
EMOTION_DIRECTION = {
    "cocky": "cocky and self-satisfied, grinning through the line",
    "sarcastic": "dripping sarcasm, exaggerated fake sincerity",
    "deadpan": "bone-dry deadpan, flat and slow, zero emotion — let the words do the work",
    "excited": "fired up, fast, voice rising with excitement",
    "outraged": "mock outrage, loud and incredulous, almost yelling the end",
    "whisper": "conspiratorial stage whisper close to the mic, then a little louder on the last words",
    "mock_sympathy": "fake pity, soft and patronising, like comforting a sad puppy",
    "disgusted": "audibly grossed out, recoiling",
    "hype": "big hype-man energy, loud, working the crowd",
    "smug": "smug and slow, savouring every word",
    "incredulous": "can't-believe-what-I'm-seeing disbelief, building to a shout",
}
ELEVEN_TAGS = {
    "cocky": "[confident]", "sarcastic": "[sarcastic]", "deadpan": "[deadpan]", "excited": "[excited]",
    "outraged": "[shouting]", "whisper": "[whispers]", "mock_sympathy": "[sympathetic]",
    "disgusted": "[disgusted]", "hype": "[excited]", "smug": "[mischievously]", "incredulous": "[surprised]",
}


_TTS_CACHE: "OrderedDict[str, str]" = OrderedDict()
TTS_CACHE_MAX = 400


def _cache_key(text: str, voice: str, instructions: str, provider: str) -> str:
    digest = hashlib.sha256("\x1f".join((provider, voice, instructions, text)).encode("utf-8")).hexdigest()
    return digest


def _cache_get(key: str) -> Optional[str]:
    """Reuse a recent identical line (for example the repeated host sign-off)."""
    if not ROAST_TTS_CACHE:
        return None
    url = _TTS_CACHE.get(key)
    if not url:
        return None
    name = url.rsplit("/", 1)[-1]
    if not (AUDIO_DIR / name).exists():
        _TTS_CACHE.pop(key, None)
        return None
    _TTS_CACHE.move_to_end(key)
    return url


def _cache_put(key: str, url: str) -> None:
    if not ROAST_TTS_CACHE:
        return
    _TTS_CACHE[key] = url
    _TTS_CACHE.move_to_end(key)
    while len(_TTS_CACHE) > TTS_CACHE_MAX:
        _TTS_CACHE.popitem(last=False)


def prune_audio_cache(max_age: int = AUDIO_TTL_SECONDS) -> int:
    """Delete local mp3 cache older than max_age seconds (durable copies stay in object storage)."""
    cutoff = time.time() - max_age
    removed = 0
    for f in AUDIO_DIR.glob("*.mp3"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            removed += 1
    return removed


def acting_instructions(meta: dict, beat: Optional[dict]) -> str:
    base = meta.get("voice_direction") or "Live stand-up comedian at a roast, punchy comedic timing."
    if not beat:
        return base
    if beat.get("rap_delivery"):
        return (f"{base}\nSpoken-word battle rap, not singing: deliver one short bar with a confident "
                "rhythmic cadence, crisp consonants, natural breath and emphasis on the final rhyme. "
                "Stay true to this fictional persona. Do not imitate any real performer or read these directions.")
    emo = EMOTION_DIRECTION.get(beat.get("emotion") or "", "")
    note = beat.get("delivery") or ""
    kind = beat.get("type") or "joke"
    return (f"{base}\nThis line is a {kind}. Emotion: {emo}. Acting note: {note}\n"
            "Perform conversationally as this fictional character: shape the setup and land the final surprise clearly. "
            "Use only natural, brief dramatic timing; do not speak the acting directions or imitate a real person.").strip()


async def synthesize_line(text: str, persona_id: str, persona_meta: Optional[dict],
                          user_elevenlabs_key: Optional[str], user_openai_key: Optional[str],
                          premium_voices_unlocked: bool = False, beat: Optional[dict] = None,
                          filename: Optional[str] = None, allow_hosted_openai: bool = True) -> Tuple[str, str]:
    """Returns (relative_audio_url, provider_used)."""
    meta = persona_meta or {}
    audio: Optional[bytes] = None
    provider = "none"
    shared_eleven = ELEVENLABS_API_KEY or secret_cached("ELEVENLABS_API_KEY")
    eleven_key = user_elevenlabs_key or (shared_eleven if premium_voices_unlocked else None)
    if eleven_key:
        try:
            tag = ELEVEN_TAGS.get((beat or {}).get("emotion") or "", "")
            audio = await synthesize_tts_elevenlabs(
                eleven_key, f"{tag} {text}".strip(), meta.get("elevenlabs"),
                persona_id=persona_id or meta.get("id"))
            provider = "elevenlabs"
        except Exception as e:
            log.warning("ElevenLabs synth failed (%s); falling back to OpenAI TTS.", e)
    if audio is None:
        if not allow_hosted_openai and not user_openai_key:
            raise RuntimeError("Preview voice requires a personal OpenAI key when ElevenLabs is unavailable")
        audio = await synthesize_tts_openai(
            text=text, voice=meta.get("tts_voice_hd") or meta.get("tts_voice") or "ash",
            speed=float((meta.get("speech") or {}).get("rate") or 1.0),
            byok_key=user_openai_key, instructions=acting_instructions(meta, beat),
        )
        provider = "openai"
    key = _cache_key(text, f"{persona_id or meta.get('id')}:{meta.get('tts_voice_hd') or meta.get('tts_voice') or 'ash'}",
                     acting_instructions(meta, beat), provider)
    cached = _cache_get(key)
    if cached:
        log.info("TTS cache hit provider=%s", provider)
        return cached, provider
    name = filename or f"{persona_id}_{uuid.uuid4().hex}.mp3"
    await save_audio(name, audio)
    url = f"/api/audio/{name}"
    _cache_put(key, url)
    return url, provider


_TTS_SEMAPHORE = asyncio.Semaphore(max(1, ROAST_TTS_CONCURRENCY))


async def synthesize_beat(beat: Dict, persona_meta_by_id: Dict[str, dict], *, byok_eleven: Optional[str],
                          byok_openai: Optional[str], premium_voices: bool) -> Dict:
    """Voice one beat, bounded by the configured concurrency and timeout."""
    async with _TTS_SEMAPHORE:
        try:
            url, provider = await asyncio.wait_for(synthesize_line(
                text=beat["text"], persona_id=beat["persona_id"],
                persona_meta=persona_meta_by_id.get(beat["persona_id"]),
                user_elevenlabs_key=byok_eleven, user_openai_key=byok_openai,
                premium_voices_unlocked=premium_voices, beat=beat,
            ), timeout=ROAST_TTS_TIMEOUT_S)
            return {**beat, "audio_url": url, "provider": provider}
        except asyncio.TimeoutError:
            return {**beat, "audio_url": None, "provider": "timeout"}
        except Exception as e:
            log.warning("TTS failed: %s", e)
            return {**beat, "audio_url": None, "provider": "none"}


async def synthesize_show(beats: List[Dict], persona_meta_by_id: Dict[str, dict], *, byok_eleven: Optional[str],
                          byok_openai: Optional[str], premium_voices: bool) -> Tuple[List[Dict], List[str]]:
    """Voice every beat in parallel. Returns (transcript, providers_used)."""
    transcript = await asyncio.gather(*[synthesize_beat(b, persona_meta_by_id, byok_eleven=byok_eleven,
                                                        byok_openai=byok_openai, premium_voices=premium_voices)
                                        for b in beats])
    providers = sorted({t["provider"] for t in transcript if t["provider"] not in ("none", "timeout")})
    return list(transcript), providers


async def voice_beats_progressive(beats_task_factory, beats: List[Dict], persona_meta_by_id: Dict[str, dict], *,
                                 byok_eleven: Optional[str], byok_openai: Optional[str],
                                 premium_voices: bool) -> Tuple[List[Dict], List[str]]:
    """Voice final beats, reusing any task already started while the script streamed."""
    tasks = {}
    for beat in beats:
        key = beat["text"]
        task = beats_task_factory.pop(key, None)
        if task is None:
            task = asyncio.create_task(synthesize_beat(beat, persona_meta_by_id, byok_eleven=byok_eleven,
                                                       byok_openai=byok_openai, premium_voices=premium_voices))
        tasks[key] = task
    try:
        transcript = []
        for beat in beats:
            voiced = await tasks[beat["text"]]
            # Early TTS may have seen a provisional type/turn before the show
            # runner added the opening, rapid-fire flags or cleaned private keys.
            # Only reuse the AUDIO, never overwrite the final staged script.
            transcript.append({**beat, "audio_url": voiced.get("audio_url"), "provider": voiced.get("provider")})
    finally:
        for task in beats_task_factory.values():
            task.cancel()
        beats_task_factory.clear()
    providers = sorted({t["provider"] for t in transcript if t.get("provider") not in (None, "none", "timeout")})
    return transcript, providers
