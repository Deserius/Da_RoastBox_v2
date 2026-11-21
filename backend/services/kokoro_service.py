"""Hardcoded, key-free local voice fallback: Kokoro (Apache-2.0 neural TTS).

This is the last tier in the voice chain (see voice_orchestrator.py), tried
only after ElevenLabs and OpenAI TTS are unconfigured or fail. It needs no API
key and no network access once its model weights are present, so a show never
ships silent just because no voice provider is configured.

Kokoro is a small (~82M parameter) open-weight model that is widely reported
as noticeably more natural than classic formant/concatenative engines (eSpeak,
the browser's SpeechSynthesis voices) while still running in real time on a
CPU. See https://github.com/thewh1teagle/kokoro-onnx and
https://huggingface.co/hexgrad/Kokoro-82M.

Two things are optional and best-effort, never required to run the app:
  - the `kokoro-onnx` package (backend/requirements-local-voice.txt). It
    currently caps its supported Python at <3.14; on a newer interpreter this
    fallback tier is simply unavailable and the app runs exactly as before.
  - its ~150MB of model weights, fetched from this project's GitHub release on
    first use (see ensure_models()) unless KOKORO_AUTO_DOWNLOAD=false, in which
    case run `python scripts/setup_local_voice.py` once to fetch them ahead of
    time (useful on a slow or offline-at-request-time connection).

PERSONA_VOICE maps every catalog persona (data/personas.json) to a specific
Kokoro voice so each comic archetype sounds distinct instead of all sharing one
default voice; persona["speech"]["rate"] (already used by the OpenAI tier)
supplies the per-persona speed so the pacing stays consistent across providers.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import threading
import urllib.request
from pathlib import Path
from typing import Optional

from config import KOKORO_AUTO_DOWNLOAD, KOKORO_MODEL_DIR, KOKORO_VARIANT

log = logging.getLogger(__name__)

try:
    import numpy as np
    from kokoro_onnx import Kokoro
    KOKORO_IMPORT_ERROR: Optional[str] = None
except Exception as _e:  # pragma: no cover - exercised only when the optional package is missing
    np = None  # type: ignore[assignment]
    Kokoro = None  # type: ignore[assignment]
    KOKORO_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:  # pragma: no cover - imageio_ffmpeg is a core dependency; defensive only
    FFMPEG = None

RELEASE_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
# Exact sizes from the GitHub Releases API, used to verify a download finished
# intact (a corrupt/partial model file fails to load, so this check matters).
_MODEL_ASSETS = {
    "fp32": ("kokoro-v1.0.onnx", 325_505_369),
    "fp16": ("kokoro-v1.0.fp16.onnx", 163_527_961),
    "int8": ("kokoro-v1.0.int8.onnx", 114_119_327),
}
_VOICES_ASSET = ("voices-v1.0.bin", 28_214_398)

# Every standard (persona_1..25) and premium (persona_p1..p15) persona gets its
# own assignment, chosen for gender/age/cadence fit from Kokoro's graded
# American/British English voices (see huggingface.co/hexgrad/Kokoro-82M).
# Reusing a voice across personas (as the ElevenLabs/OpenAI tiers already do)
# is fine: the script's writing and the persona's acting direction, not the
# base timbre alone, carry most of a character's distinctiveness here.
PERSONA_VOICE = {
    "persona_1": "am_puck", "persona_2": "af_sky", "persona_3": "am_onyx",
    "persona_4": "am_michael", "persona_5": "bm_fable", "persona_6": "am_liam",
    "persona_7": "am_fenrir", "persona_8": "af_heart", "persona_9": "af_sarah",
    "persona_10": "bm_george", "persona_11": "am_eric", "persona_12": "am_fenrir",
    "persona_13": "af_nicole", "persona_14": "bf_emma", "persona_15": "af_kore",
    "persona_16": "am_puck", "persona_17": "bm_daniel", "persona_18": "am_michael",
    "persona_19": "af_aoede", "persona_20": "af_alloy", "persona_21": "af_nova",
    "persona_22": "am_liam", "persona_23": "af_sky", "persona_24": "am_onyx",
    "persona_25": "bm_lewis",
    "persona_p1": "am_fenrir", "persona_p2": "am_onyx", "persona_p3": "af_bella",
    "persona_p4": "bm_lewis", "persona_p5": "am_puck", "persona_p6": "bf_isabella",
    "persona_p7": "am_echo", "persona_p8": "am_liam", "persona_p9": "af_aoede",
    "persona_p10": "am_michael", "persona_p11": "bm_george", "persona_p12": "af_kore",
    "persona_p13": "am_santa", "persona_p14": "am_echo", "persona_p15": "af_nicole",
}
# Used for any persona id this build does not recognise (a custom/renamed
# catalog), keyed by the "gender" field already present on every persona.
_GENDER_FALLBACK = {"male": "am_michael", "female": "af_heart"}
_DEFAULT_VOICE = "af_heart"


def _model_paths() -> tuple[Path, Path]:
    filename, _ = _MODEL_ASSETS[KOKORO_VARIANT]
    return KOKORO_MODEL_DIR / filename, KOKORO_MODEL_DIR / _VOICES_ASSET[0]


def models_present() -> bool:
    model_path, voices_path = _model_paths()
    return model_path.is_file() and voices_path.is_file()


def _download_one(url: str, dest: Path, expected_size: int) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    log.info("Downloading local voice model %s (%.0f MB)...", dest.name, expected_size / 1_000_000)
    try:
        with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as out:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
        size = tmp.stat().st_size
        if size != expected_size:
            raise RuntimeError(f"{dest.name} downloaded as {size} bytes, expected {expected_size}")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)


_download_lock = threading.Lock()


def ensure_models(*, force: bool = False) -> None:
    """Fetch the Kokoro weights into KOKORO_MODEL_DIR if they are not already there.

    Safe to call repeatedly/concurrently; a module-level lock serializes actual
    downloads so parallel requests do not race on the same partial file.
    """
    model_path, voices_path = _model_paths()
    if not force and models_present():
        return
    with _download_lock:
        if not force and models_present():
            return
        KOKORO_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        filename, size = _MODEL_ASSETS[KOKORO_VARIANT]
        if force or not model_path.is_file():
            _download_one(f"{RELEASE_BASE}/{filename}", model_path, size)
        vfilename, vsize = _VOICES_ASSET
        if force or not voices_path.is_file():
            _download_one(f"{RELEASE_BASE}/{vfilename}", voices_path, vsize)


_kokoro_instance = None
_kokoro_lock = threading.Lock()


def _load_kokoro():
    global _kokoro_instance
    if _kokoro_instance is not None:
        return _kokoro_instance
    with _kokoro_lock:
        if _kokoro_instance is not None:
            return _kokoro_instance
        if Kokoro is None:
            raise RuntimeError(
                "Local voice fallback is not installed. Run: pip install -r "
                f"backend/requirements-local-voice.txt ({KOKORO_IMPORT_ERROR})"
            )
        if KOKORO_AUTO_DOWNLOAD:
            ensure_models()
        if not models_present():
            raise RuntimeError(
                "Local voice fallback model files are missing. Run "
                "scripts/setup_local_voice.py once to download them, or set "
                "KOKORO_AUTO_DOWNLOAD=true to fetch them automatically."
            )
        model_path, voices_path = _model_paths()
        _kokoro_instance = Kokoro(str(model_path), str(voices_path))
        return _kokoro_instance


def voice_for_persona(persona_id: Optional[str], persona_meta: Optional[dict]) -> str:
    if persona_id and persona_id in PERSONA_VOICE:
        return PERSONA_VOICE[persona_id]
    gender = (persona_meta or {}).get("gender")
    return _GENDER_FALLBACK.get(gender, _DEFAULT_VOICE)


def available() -> bool:
    """True once this tier can plausibly be used (package importable; models
    present or fetchable). Does not guarantee a given synth call will succeed."""
    return Kokoro is not None and (models_present() or KOKORO_AUTO_DOWNLOAD)


def _pcm_to_mp3(samples, sample_rate: int) -> bytes:
    """Encode float32 PCM to MP3 with the bundled ffmpeg (no extra OS install)."""
    if FFMPEG is None:
        raise RuntimeError("ffmpeg is unavailable; cannot encode local voice audio")
    raw = np.asarray(samples, dtype="<f4").tobytes()
    cmd = [FFMPEG, "-v", "error", "-f", "f32le", "-ar", str(sample_rate), "-ac", "1", "-i", "pipe:0",
           "-ar", "44100", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "128k", "-f", "mp3", "pipe:1"]
    result = subprocess.run(cmd, input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError("Local voice audio could not be encoded to MP3")
    return result.stdout


def _synth_sync(text: str, voice: str, speed: float) -> bytes:
    kokoro = _load_kokoro()
    samples, sample_rate = kokoro.create(text, voice=voice, speed=max(0.5, min(2.0, float(speed))), lang="en-us")
    return _pcm_to_mp3(samples, sample_rate)


async def synthesize_tts_kokoro(text: str, persona_id: Optional[str] = None,
                                persona_meta: Optional[dict] = None, speed: float = 1.0) -> bytes:
    """Synthesize `text` locally with Kokoro. Raises if the tier is unavailable."""
    if not text or not text.strip():
        raise ValueError("Nothing to synthesize")
    voice = voice_for_persona(persona_id, persona_meta)
    return await asyncio.to_thread(_synth_sync, text.strip(), voice, speed)
