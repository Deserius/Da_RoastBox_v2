"""Local, bounded voice leveling for playback and reel exports.

Original recordings stay untouched in durable storage. A content-addressed,
private read cache contains leveled MP3s for both old and new persona clips.
No provider calls are made. Decoding/encoding is bounded to two concurrent
FFmpeg jobs so a 24-line show cannot spawn 24 encoders at once.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional

import imageio_ffmpeg
import numpy as np

from config import VOICE_LEVELING_ENABLED, VOICE_TARGET_RMS_DBFS
from . import storage

log = logging.getLogger(__name__)
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
MASTER_VERSION = "voice-rms-v1"
MAX_SOURCE_BYTES = 15 * 1024 * 1024
SAMPLE_RATE = 16000
ANALYSIS_SECONDS = 45
MAX_GAIN_DB = 18.0
MIN_GAIN_DB = -18.0
_JOBS = threading.BoundedSemaphore(2)
_LOCKS = tuple(threading.Lock() for _ in range(32))


def _run(command: list[str], audio: bytes, *, timeout: int = 25) -> bytes:
    result = subprocess.run(command, input=audio, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError("Voice audio could not be decoded or leveled")
    return result.stdout


def _speech_rms(audio: bytes) -> Optional[float]:
    """Gated 100 ms RMS, so pauses don't make a quiet line artificially loud."""
    raw = _run([FFMPEG, "-v", "error", "-i", "pipe:0", "-t", str(ANALYSIS_SECONDS),
                "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1"], audio)
    samples = np.frombuffer(raw, dtype="<f4")
    if not samples.size or not np.isfinite(samples).all():
        return None
    frame_size = SAMPLE_RATE // 10
    count = len(samples) // frame_size
    if count:
        frames = samples[:count * frame_size].reshape(count, frame_size).astype(np.float64)
        levels = np.sqrt(np.mean(frames * frames, axis=1))
    else:
        levels = np.array([np.sqrt(np.mean(samples.astype(np.float64) ** 2))])
    active = levels[levels >= 10 ** (-50 / 20)]
    if not active.size:
        return None  # Do not amplify near-silence/noise into a loud blast.
    return float(np.percentile(active, 60))


def master_voice_bytes(audio: bytes) -> bytes:
    """Return a leveled MP3, or leave unsupported/silent inputs unchanged.

    The RMS target and limited gain make typical TTS lines consistent; a mild
    peak compressor and limiter preserve headroom. Very quiet recordings,
    damaged audio and differing playback devices cannot be made identical.
    """
    if not audio or len(audio) > MAX_SOURCE_BYTES:
        return audio
    with _JOBS:
        try:
            level = _speech_rms(audio)
            if not level or not math.isfinite(level):
                return audio
            gain_db = max(MIN_GAIN_DB, min(MAX_GAIN_DB, VOICE_TARGET_RMS_DBFS - 20 * math.log10(level)))
            filters = (f"volume={gain_db:.4f}dB,"
                       "acompressor=threshold=0.25:ratio=2:attack=10:release=100,"
                       "alimiter=limit=0.90:level=0:latency=1")
            return _run([FFMPEG, "-v", "error", "-i", "pipe:0", "-map_metadata", "-1", "-vn",
                         "-af", filters, "-ar", "44100", "-ac", "1", "-c:a", "libmp3lame",
                         "-b:a", "128k", "-f", "mp3", "pipe:1"], audio)
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
            # Never turn a playable show into a silent one just because local
            # mastering failed. Log no script text, keys or user media paths.
            log.warning("Voice leveling unavailable for a clip; using the original audio")
            return audio


def _cached_master(audio: bytes, cache_dir: Path) -> bytes:
    if not VOICE_LEVELING_ENABLED or not audio:
        return audio
    variant = f"{MASTER_VERSION}:{VOICE_TARGET_RMS_DBFS:.2f}".encode()
    digest = hashlib.sha256(variant + b"\0" + audio).hexdigest()
    cache_file = cache_dir / f"master_{MASTER_VERSION}_{digest}.mp3"
    with _LOCKS[int(digest[:2], 16) % len(_LOCKS)]:
        try:
            if cache_file.is_file():
                return cache_file.read_bytes()
        except OSError:
            pass
        leveled = master_voice_bytes(audio)
        if leveled == audio:
            return audio  # No permanent cache of a temporary FFmpeg failure.
        try:
            cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = None
            try:
                with tempfile.NamedTemporaryFile(dir=cache_dir, prefix=".master-", delete=False) as tmp:
                    path = tmp.name
                    tmp.write(leveled)
                os.replace(path, cache_file)
            finally:
                if path and os.path.exists(path):
                    os.unlink(path)
        except OSError:
            log.warning("Voice-level cache unavailable; returning the processed clip")
        return leveled


async def load_voice_audio(filename: str) -> Optional[bytes]:
    """Fetch an authorized original and level it for a voice consumer."""
    audio = await storage.load_audio(filename)
    if audio is None or not VOICE_LEVELING_ENABLED:
        return audio
    return await asyncio.to_thread(_cached_master, audio, storage.AUDIO_DIR)
