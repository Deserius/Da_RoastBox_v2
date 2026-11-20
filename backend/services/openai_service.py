"""OpenAI-compatible client (direct OpenAI or BYOK) + expressive TTS.

Direct OpenAI is the default. The legacy Emergent LLM gateway is only used when
AI_DEFAULT_PROVIDER is explicitly "emergent" *and* a gateway key is present, so a
stock install never needs the Emergent platform.
"""
import asyncio
import logging
from typing import Optional
from openai import OpenAI

from config import EMERGENT_LLM_KEY, OPENAI_API_KEY, AI_DEFAULT_PROVIDER, TTS_MODEL
from services.runtime_settings import secret_cached

log = logging.getLogger(__name__)

_GATEWAY_URL = "https://integrations.emergentagent.com/llm"
EXPRESSIVE_VOICES = {"alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"}
CLASSIC_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}


def get_client(byok_key: Optional[str] = None, timeout: float = 90.0) -> OpenAI:
    # Resolved per call, not at import, so a key entered in the settings console
    # takes effect immediately without a restart.
    # Module constants stay authoritative; the console only fills a gap.
    openai_key = OPENAI_API_KEY or secret_cached("OPENAI_API_KEY")
    emergent_key = EMERGENT_LLM_KEY or secret_cached("EMERGENT_LLM_KEY")
    if byok_key:
        return OpenAI(api_key=byok_key, timeout=timeout, max_retries=1)
    # Direct OpenAI first: it is the supported path and needs no vendor gateway.
    if openai_key and AI_DEFAULT_PROVIDER != "emergent":
        return OpenAI(api_key=openai_key, timeout=timeout, max_retries=1)
    # Legacy gateway, only when the operator opted in and a key exists.
    if emergent_key and AI_DEFAULT_PROVIDER == "emergent":
        return OpenAI(api_key=emergent_key, base_url=_GATEWAY_URL, timeout=timeout, max_retries=1)
    if openai_key:
        return OpenAI(api_key=openai_key, timeout=timeout, max_retries=1)
    raise RuntimeError(
        "No AI provider key configured. Add an OpenAI key in Settings "
        "(passphrase console) or set OPENAI_API_KEY in backend/.env."
    )


def get_emergent_client(timeout: float = 90.0) -> OpenAI:
    """Explicit hosted fallback; never send a user's BYOK to this endpoint.

    Optional. Only reachable when AI_DEFAULT_PROVIDER is "emergent" and an
    EMERGENT_LLM_KEY is configured; otherwise this raises and callers fall
    through to the next provider.
    """
    emergent_key = EMERGENT_LLM_KEY or secret_cached("EMERGENT_LLM_KEY")
    if not emergent_key:
        raise RuntimeError("Emergent backup is not configured")
    return OpenAI(api_key=emergent_key, base_url=_GATEWAY_URL, timeout=timeout, max_retries=0)


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
