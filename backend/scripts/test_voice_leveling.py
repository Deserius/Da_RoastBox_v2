#!/usr/bin/env python3
"""Deterministic, offline FFmpeg tests for persona voice leveling.

Synthetic WAV/MP3 signals only. Tests quiet/loud lines, silence, clipping,
cache reuse, concurrency and original-file preservation; no provider calls.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import io
import subprocess
import sys
import tempfile
import threading
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import services.audio_mastering as mastering  # noqa: E402


def fixture(scale: float, *, transient: bool = False) -> bytes:
    rate = 16000
    t = np.arange(rate * 3) / rate
    envelope = np.where((t > .2) & (t < 1.2) | (t > 1.4) & (t < 2.7), 1.0, 0.0)
    samples = scale * envelope * (0.5 * np.sin(2 * np.pi * 220 * t) + 0.2 * np.sin(2 * np.pi * 870 * t))
    if transient:
        samples[rate:rate + 12] = .98
    pcm = np.int16(np.clip(samples, -1, 1) * 32767)
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())
    return out.getvalue()


def decode(data: bytes):
    result = subprocess.run([mastering.FFMPEG, "-v", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1",
                             "-ar", "16000", "pipe:1"], input=data, capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype="<f4")


def main():
    # Difference in input level exceeds 17 dB; output speech levels converge.
    sources = [fixture(s) for s in (.04, .10, .30)]
    before = [mastering._speech_rms(s) for s in sources]
    outputs = [mastering.master_voice_bytes(s) for s in sources]
    after = [mastering._speech_rms(s) for s in outputs]
    spread_before = 20 * np.log10(max(before) / min(before))
    spread_after = 20 * np.log10(max(after) / min(after))
    assert spread_before > 17 and spread_after < 1.5, (before, after, spread_before, spread_after)
    assert all(0.08 < rms < 0.14 for rms in after), after
    peak = float(np.max(np.abs(decode(mastering.master_voice_bytes(fixture(.2, transient=True))))))
    assert peak < .99, peak
    silence = fixture(0)
    assert mastering.master_voice_bytes(silence) == silence, "Silence must not be amplified"
    assert mastering.master_voice_bytes(b"not audio") == b"not audio", "Invalid media must fail open"

    with tempfile.TemporaryDirectory(prefix="roastbox-leveling-") as temp:
        raw = sources[1]
        src = Path(temp) / "original.wav"
        src.write_bytes(raw)
        counter = [0]
        lock = threading.Lock()
        old = mastering.master_voice_bytes
        def counted(data):
            with lock:
                counter[0] += 1
            return old(data)
        mastering.master_voice_bytes = counted
        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: mastering._cached_master(raw, Path(temp)), range(8)))
            assert counter[0] == 1 and all(r == results[0] for r in results), counter
            assert src.read_bytes() == raw, "Mastering must not overwrite stored originals"
            assert len(list(Path(temp).glob("master_*.mp3"))) == 1
        finally:
            mastering.master_voice_bytes = old
    print(f"PASS: synthetic voice spread {spread_before:.1f} dB → {spread_after:.1f} dB; peak {peak:.3f}")
    print("PASS: silence/invalid input safely handled; concurrent cache reuse and original preservation")


if __name__ == "__main__":
    main()
