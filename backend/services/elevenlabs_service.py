"""ElevenLabs TTS for distinct persona voices (BYOK or hosted key)."""
import asyncio
import re
from typing import Optional
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings

DEFAULT_VOICE = {"voice_id": "nPczCjzI2devNBz1zQrb", "stability": 0.55}
MODEL_CHAIN = ("eleven_v3", "eleven_multilingual_v2")  # v3 understands [emotion] tags


async def synthesize_tts_elevenlabs(api_key: str, text: str, voice_cfg: Optional[dict] = None) -> bytes:
    cfg = voice_cfg or DEFAULT_VOICE
    client = ElevenLabs(api_key=api_key)
    settings = VoiceSettings(
        stability=float(cfg.get("stability", 0.55)),
        similarity_boost=0.75,
        style=0.55,
        use_speaker_boost=True,
    )

    def _call(model_id: str, body: str):
        chunks = client.text_to_speech.convert(
            text=body, voice_id=cfg["voice_id"], model_id=model_id,
            output_format="mp3_44100_128", voice_settings=settings,
        )
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
