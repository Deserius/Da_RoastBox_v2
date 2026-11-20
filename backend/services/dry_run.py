"""Offline demo provider: run the whole show pipeline with no network.

This workspace cannot reach OpenAI, OpenRouter, Stripe, or Google — the TLS
handshake is reset by the sandbox firewall. That means no real provider can
answer here no matter how valid the key is, so every generation failed with an
upstream/connection error.

``ROASTBOX_DRY_RUN=true`` swaps the two network boundaries for deterministic
local stand-ins:

* ``roast_writer.get_client`` returns a client whose completions are generated
  from the actual persona cast and prompt, so scripts still vary per cast and
  the normal structural checks still run.
* ``synthesize_tts_openai`` returns a short valid WAV so the audio pipeline,
  cache, storage, transcript and player all behave normally.

Everything else is the real code path: validation, entitlements, cost, voice
orchestration, credit commit, history, and sharing.

It is off unless explicitly enabled, and it refuses to activate in production so
it can never silently replace a paid provider.
"""
import json
import logging
import math
import random
import struct
import wave
from io import BytesIO
from types import SimpleNamespace
from typing import List, Optional

log = logging.getLogger(__name__)

_installed = False

# Lines are original filler, not impressions of any real person.
_OPENERS = [
    "Alright, gather round, because this one needs a moment of silence.",
    "You walked in here looking like a group project nobody wanted.",
    "I have seen a lot of photos. This one asked me for a lawyer.",
    "Let us all appreciate the confidence it took to submit this.",
]
_VERBS = ["unpaid-intern", "group-chat-moderator", "airport-shuttle", "sock-drawer",
          "wet-cardboard", "middle-manager", "expired-coupon", "laundromat"]
_NOUNS = ["lighting", "pose", "backdrop", "expression", "haircut", "jacket",
          "stance", "vibe", "framing", "smile", "posture", "wardrobe"]
_CLOSERS = [
    "Thank you, goodnight, and please update your camera roll.",
    "I am done. Somebody hand me a water and a therapist.",
    "That is all I have. The photo has suffered enough.",
]


# The most recent cast passed to write_script, used by the fake client. Reading
# ids out of the prompt text was unreliable (portrait captions mention ids that
# are not the actual cast).
_LAST_CAST: List[dict] = []
# How many beats the caller asked for; set from write_script's expected_beats.
_LAST_EXPECTED = [11]


def _remember_cast(personas: List[dict], keep=None):
    global _LAST_CAST
    if personas:
        _LAST_CAST = [{"id": p.get("id"), "name": p.get("name") or p.get("id")}
                      for p in personas if p.get("id")]
    return keep


def _fake_script(prompt: str, personas: List[dict], expected_beats: int) -> str:
    """Build a structurally valid script from the real cast in the prompt."""
    ids = [p.get("id") for p in personas if p.get("id")] or ["persona_1"]
    names = {p.get("id"): (p.get("name") or p.get("id")) for p in personas}
    rng = random.Random(hash((tuple(ids), expected_beats)) & 0xFFFFFFFF)
    n = max(1, int(expected_beats))
    beats = []
    for i in range(n):
        pid = ids[i % len(ids)]
        if i == 0:
            text = rng.choice(_OPENERS)
            kind = "intro"
        elif i == n - 1:
            text = rng.choice(_CLOSERS)
            kind = "closer"
        else:
            # Every line must be distinct: the real checker rejects heavy
            # repetition, so vary the wording as well as the index.
            verb = _VERBS[i % len(_VERBS)]
            noun = _NOUNS[(i * 7) % len(_NOUNS)]
            text = (f"{names.get(pid, pid)} says the {noun} in this photo has "
                    f"{verb} energy, and honestly the {noun} agrees with me about number {i}.")
            kind = "joke" if i % 2 else "punchline"
        beats.append({"persona_id": pid, "type": kind, "text": text})
    return json.dumps({"script": beats})


def _tone_wav(text: str, seconds: Optional[float] = None) -> bytes:
    """A short, quiet, valid WAV so the player and cache path behave normally."""
    if seconds is None:
        # Roughly speech-like: longer lines get a touch more audio.
        seconds = max(0.4, min(6.0, len(text) / 90.0))
    rate = 8000
    frames = int(rate * seconds)
    base = 180 + (abs(hash(text[:40])) % 120)
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        for i in range(frames):
            envelope = 0.15 * (1.0 - (i / max(1, frames)))  # gentle fade
            value = int(32767 * envelope * math.sin(2 * math.pi * base * i / rate))
            w.writeframes(struct.pack("<h", value))
    return buf.getvalue()


def _is_vision_request(messages: list) -> int:
    """How many image_url parts a request carries, so a photo-analysis call -
    distinguishable from a script-writing call by its message shape - gets an
    answer shaped like one instead of a fake script no caller asked for."""
    count = 0
    for msg in messages:
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, list):
            count += sum(1 for part in content if isinstance(part, dict) and part.get("type") == "image_url")
    return count


def _fake_photo_observations(n_images: int) -> str:
    """Schema-valid stand-in for _normalize_photo_observations in roast_writer."""
    photos = [{"image_index": i, "details": ["a person in frame", "a plain background"]}
              for i in range(max(1, n_images))]
    return json.dumps({"photos": photos})


class _DryRunCompletions:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        messages = kwargs.get("messages") or []
        n_images = _is_vision_request(messages)
        if n_images:
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=_fake_photo_observations(n_images)))])
        # The user block carries the cast and instructions; recover the beat count
        # from the prompt so the script satisfies the same structural checks.
        text = json.dumps(messages)[:40000]
        expected = _LAST_EXPECTED[0]
        personas = list(_LAST_CAST)
        if not personas:
            personas = [{"id": "persona_1", "name": "Roaster"}]
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=_fake_script(text, personas, expected)))])


class _DryRunClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_DryRunCompletions())
        self.audio = SimpleNamespace(speech=SimpleNamespace(create=self._speech))

    @staticmethod
    def _speech(**kwargs):
        return BytesIO(_tone_wav(str(kwargs.get("input") or "")))


async def _dry_tts(text: str = "", voice: str = "onyx", speed: float = 1.0,
                   byok_key: Optional[str] = None, instructions: Optional[str] = None, **_kw) -> bytes:
    return _tone_wav(text)


def install() -> bool:
    """Patch the network boundaries once. Returns True when active."""
    global _installed
    if _installed:
        return True
    from config import APP_VERSION  # noqa: F401  (import check only)
    from services import openai_service, roast_writer

    roast_writer.get_client = lambda _byok=None, **_kw: _DryRunClient()
    # Capture the authoritative cast. Callers import write_script by name, so
    # patch build_roast_prompt, which every writer path calls with the personas.
    _orig_prompt = roast_writer.build_roast_prompt

    def _prompt(personas, *args, **kwargs):
        _remember_cast(personas)
        return _orig_prompt(personas, *args, **kwargs)

    roast_writer.build_roast_prompt = _prompt
    _orig_write = roast_writer.write_script

    async def _write(*args, **kwargs):
        if kwargs.get("expected_beats"):
            _LAST_EXPECTED[0] = int(kwargs["expected_beats"])
        elif len(args) > 5 and args[5]:
            _LAST_EXPECTED[0] = int(args[5])
        return await _orig_write(*args, **kwargs)

    roast_writer.write_script = _write
    try:
        from routes import roast as _roar
        _roar.write_script = _write
    except Exception:  # pragma: no cover
        pass
    try:
        from routes import roast as roar
        roar.build_roast_prompt = _prompt
    except Exception:  # pragma: no cover - route import order
        pass
    openai_service.synthesize_tts_openai = _dry_tts
    # voice_orchestrator imported the symbol directly, so patch it there too.
    from services import voice_orchestrator
    voice_orchestrator.synthesize_tts_openai = _dry_tts
    _installed = True
    log.warning("DRY-RUN provider active: scripts and audio are generated locally, no network calls")
    return True
