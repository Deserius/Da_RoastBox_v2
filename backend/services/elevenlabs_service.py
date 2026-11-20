"""ElevenLabs TTS for distinct persona voices (BYOK or hosted key)."""
import asyncio
import re
from typing import Optional
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings

DEFAULT_VOICE = {"voice_id": "nPczCjzI2devNBz1zQrb", "stability": 0.55}
MODEL_CHAIN = ("eleven_v3", "eleven_multilingual_v2")  # v3 understands [emotion] tags
# Reference-project delivery mapping. `rate` is the pace hint the upstream spec
# paired with each persona's voice (Brian is 1.00, Matilda 1.05, Sam 1.15 ...).
# It is applied as the per-request speed multiplier so distinct personas also
# differ in tempo, not only timbre.
PERSONA_RATE = {
    "persona_1": 1.00, "persona_2": 1.05, "persona_3": 1.15, "persona_4": 0.95,
    "persona_5": 1.05, "persona_6": 1.15, "persona_7": 0.90, "persona_8": 1.20,
    "persona_9": 1.05, "persona_10": 0.95, "persona_11": 1.10, "persona_12": 1.00,
    "persona_13": 1.15, "persona_14": 1.20, "persona_15": 1.10, "persona_16": 1.05,
    "persona_17": 0.95, "persona_18": 0.95, "persona_19": 1.10, "persona_20": 1.00,
    # Premium personas
    "persona_p1": 0.92, "persona_p2": 1.10, "persona_p3": 1.12,
    "persona_p4": 0.85, "persona_p5": 1.05,
}


async def synthesize_tts_elevenlabs(api_key: str, text: str, voice_cfg: Optional[dict] = None,
                                    persona_id: Optional[str] = None) -> bytes:
    cfg = voice_cfg or DEFAULT_VOICE
    client = ElevenLabs(api_key=api_key)
    settings = VoiceSettings(
        stability=float(cfg.get("stability", 0.55)),
        similarity_boost=0.75,
        style=0.55,
        use_speaker_boost=True,
    )
    # Pace is a delivery hint, not a required field: fall back to the persona's
    # mapped rate, then to natural speed.
    rate = cfg.get("rate", PERSONA_RATE.get(persona_id or cfg.get("persona_id"), 1.0))
    try:
        rate = max(0.7, min(1.2, float(rate)))
    except (TypeError, ValueError):
        rate = 1.0

    def _call(model_id: str, body: str):
        kwargs = {
            "text": body, "voice_id": cfg["voice_id"], "model_id": model_id,
            "output_format": "mp3_44100_128", "voice_settings": settings,
        }
        # Send a speed only when it actually changes the read, so the default
        # path stays identical to before and compatible with older SDKs.
        if abs(rate - 1.0) > 0.01:
            kwargs["speed"] = rate
        chunks = client.text_to_speech.convert(**kwargs)
        return b"".join(chunks)

    try:
        return await asyncio.to_thread(_call, MODEL_CHAIN[0], text)
    except Exception:
        plain = re.sub(r"\[[a-z ]+\]\s*", "", text)
        return await asyncio.to_thread(_call, MODEL_CHAIN[1], plain)


async def check_elevenlabs_key(api_key: str) -> bool:
    def _call():
        ElevenLabs(api_key=api_key).user.get()
        return True
    return await asyncio.to_thread(_call)
