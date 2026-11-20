"""OpenAI-compatible client (Emergent gateway or BYOK) + expressive TTS."""
import asyncio
import logging
from typing import Optional
from openai import OpenAI

from config import EMERGENT_LLM_KEY, OPENAI_API_KEY, AI_DEFAULT_PROVIDER, TTS_MODEL

log = logging.getLogger(__name__)

_GATEWAY_URL = "https://integrations.emergentagent.com/llm"
EXPRESSIVE_VOICES = {"alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"}
CLASSIC_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}


def get_client(byok_key: Optional[str] = None, timeout: float = 90.0) -> OpenAI:
    if byok_key:
        return OpenAI(api_key=byok_key, timeout=timeout, max_retries=1)
    if AI_DEFAULT_PROVIDER == "openai" and OPENAI_API_KEY:
        return OpenAI(api_key=OPENAI_API_KEY, timeout=timeout, max_retries=1)
    if EMERGENT_LLM_KEY:
        return OpenAI(api_key=EMERGENT_LLM_KEY, base_url=_GATEWAY_URL, timeout=timeout, max_retries=1)
    if OPENAI_API_KEY:
        return OpenAI(api_key=OPENAI_API_KEY, timeout=timeout, max_retries=1)
    raise RuntimeError("No AI provider key configured. Add an OpenAI key in Settings or configure EMERGENT_LLM_KEY or OPENAI_API_KEY.")


def get_emergent_client(timeout: float = 90.0) -> OpenAI:
    """Explicit hosted fallback; never send a user's BYOK to this endpoint."""
    if not EMERGENT_LLM_KEY:
        raise RuntimeError("Emergent backup is not configured")
    return OpenAI(api_key=EMERGENT_LLM_KEY, base_url=_GATEWAY_URL, timeout=timeout, max_retries=0)


def _read(resp) -> bytes:
    if hasattr(resp, "read"):
        return resp.read()
    if hasattr(resp, "content"):
        return resp.content
    return bytes(resp)


async def synthesize_tts_openai(text: str, voice: str = "onyx", speed: float = 1.0,
                                byok_key: Optional[str] = None, instructions: Optional[str] = None) -> bytes:
    """Expressive TTS (gpt-4o-mini-tts + acting instructions); falls back to tts-1 on failure."""
    client = get_client(byok_key, timeout=20.0)
    if instructions and TTS_MODEL != "tts-1":
        try:
            resp = await asyncio.to_thread(
                client.audio.speech.create, model=TTS_MODEL,
                voice=voice if voice in EXPRESSIVE_VOICES else "ash",
                input=text, instructions=instructions[:1500], response_format="mp3",
            )
            return _read(resp)
        except Exception as e:
            log.warning("Expressive TTS failed (%s); falling back to tts-1.", e)
    resp = await asyncio.to_thread(
        client.audio.speech.create, model="tts-1",
        voice=voice if voice in CLASSIC_VOICES else "onyx",
        input=text, response_format="mp3", speed=max(0.5, min(2.0, float(speed))),
    )
    return _read(resp)
