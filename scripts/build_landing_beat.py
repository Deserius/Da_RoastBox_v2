#!/usr/bin/env python3
"""Synthesize the original landing-page hip-hop loop for Da RoastBox.

Everything is generated from oscillators and seeded noise: no samples, no
network, no third-party music. The loop is exactly 30.0 s (96 BPM, 12 bars of
4/4) so it aligns with the welcome announcement that plays once per loop.
Requires numpy, scipy and imageio-ffmpeg (already in backend requirements).
"""
from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100
BPM = 96
BEATS_PER_BAR = 4
BARS = 12
BEAT = 60.0 / BPM
LOOP_SECONDS = BEAT * BEATS_PER_BAR * BARS  # 30.0 s
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public" / "assets" / "intro" / "roastbox-landing-beat.mp3"
RNG = np.random.default_rng(20261105)


def t(n):
    return np.arange(n, dtype=np.float64) / SR


def env_ar(n, attack, release, curve=3.0):
    tt = t(n)
    a = np.minimum(1.0, tt / max(attack, 1e-6))
    r = np.minimum(1.0, np.maximum(0.0, (n / SR - tt) / max(release, 1e-6)))
    return a * (r ** curve)


def kick():
    n = int(0.42 * SR)
    tt = t(n)
    f = 118 * np.exp(-26 * tt) + 44
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-7.5 * tt)
    click = RNG.normal(0, 1, n) * np.exp(-180 * tt) * 0.35
    return (body + click) * 0.95


def snare():
    n = int(0.30 * SR)
    tt = t(n)
    tone = (np.sin(2 * np.pi * 196 * tt) * 0.45 + np.sin(2 * np.pi * 331 * tt) * 0.28) * np.exp(-24 * tt)
    noise = RNG.normal(0, 1, n)
    noise = sosfilt(butter(2, [1400, 7200], btype="bandpass", fs=SR, output="sos"), noise)
    return (tone + noise * np.exp(-19 * tt) * 0.9) * 0.7


def hat(open_hat=False):
    n = int((0.26 if open_hat else 0.09) * SR)
    tt = t(n)
    noise = RNG.normal(0, 1, n)
    noise = sosfilt(butter(2, [7200, 15000], btype="bandpass", fs=SR, output="sos"), noise)
    return noise * np.exp((-13 if open_hat else -46) * tt) * (0.30 if open_hat else 0.26)


def bass(midi, seconds):
    n = int(seconds * SR)
    tt = t(n)
    f = 440 * (2 ** ((midi - 69) / 12))
    phase = 2 * np.pi * f * tt
    tone = np.sin(phase) + 0.30 * np.sin(2 * phase + 0.5) + 0.10 * np.sin(3 * phase)
    return tone * env_ar(n, 0.012, 0.08, curve=2.0) * np.exp(-0.55 * tt) * 0.55


def stab(midis, seconds):
    """Short filtered chord stab; the warm pad under the drums."""
    n = int(seconds * SR)
    tt = t(n)
    out = np.zeros(n)
    for m in midis:
        f = 440 * (2 ** ((m - 69) / 12))
        out += np.sin(2 * np.pi * f * tt + 0.3) * 0.5
        out += np.sin(2 * np.pi * f * 2 * tt) * 0.12
    out = sosfilt(butter(2, 260, btype="highpass", fs=SR, output="sos"), out)
    return out * env_ar(n, 0.02, 0.30, curve=1.6) * 0.16


def vinyl(seconds):
    """Barely-there texture so the loop does not sound synthetic and sterile."""
    n = int(seconds * SR)
    noise = RNG.normal(0, 1, n)
    hiss = sosfilt(butter(2, [900, 6000], btype="bandpass", fs=SR, output="sos"), noise)
    return hiss * 0.012


def place(dest, source, beat, pan=0.0, gain=1.0):
    start = int(beat * BEAT * SR) % len(dest)
    src = source * gain
    left = np.sqrt((1 - pan) / 2)
    right = np.sqrt((1 + pan) / 2)
    end = min(len(dest), start + len(src))
    src = src[: end - start]
    dest[start:end, 0] += src * left
    dest[start:end, 1] += src * right
    if end == len(dest) and len(src) < len(source):  # wrap the tail for a seamless loop
        rem = len(source) - len(src)
        dest[0:rem, 0] += source[len(src):] * left
        dest[0:rem, 1] += source[len(src):] * right


def build():
    n = int(LOOP_SECONDS * SR)
    mix = np.zeros((n, 2))
    # Kit: boom-bap style, kick on 1 and the "and" of 2, snare on 2 and 4.
    for bar in range(BARS):
        base = bar * BEATS_PER_BAR
        place(mix, kick(), base + 0.0, gain=1.0)
        place(mix, kick(), base + 2.5, gain=0.82)
        place(mix, snare(), base + 1.0, pan=-0.08)
        place(mix, snare(), base + 3.0, pan=0.08)
        for eighth in range(8):
            place(mix, hat(open_hat=(eighth == 7)), base + eighth * 0.5,
                  pan=(-0.22 if eighth % 2 else 0.22), gain=0.9)
        if bar % 4 == 3:  # small fill into the next four-bar phrase
            place(mix, snare(), base + 3.5, pan=0.16, gain=0.55)
            place(mix, snare(), base + 3.75, pan=-0.16, gain=0.35)
    # Bass line (A minor, one bar per root) and a two-bar chord vamp.
    roots = [33, 33, 36, 31]
    for bar in range(BARS):
        root = roots[bar % 4]
        base = bar * BEATS_PER_BAR
        place(mix, bass(root, 0.62), base + 0.0)
        place(mix, bass(root, 0.42), base + 1.5)
        place(mix, bass(root + 12, 0.30), base + 2.5)
        place(mix, bass(root, 0.52), base + 3.5)
    chords = [[57, 60, 64], [55, 58, 62]]
    for bar in range(BARS):
        base = bar * BEATS_PER_BAR
        place(mix, stab(chords[bar % 2], 0.9), base + 0.5)
        place(mix, stab(chords[bar % 2], 0.7), base + 3.0, pan=0.12)
    mix += vinyl(LOOP_SECONDS)[:, None]
    # Glue, shape and fade-proof limiting so the loop point is inaudible.
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = np.tanh(mix / peak * 1.35) * 0.82
    mix -= mix.mean(axis=0, keepdims=True) * 0.02
    return mix


def write_mp3(mix):
    pcm = np.clip(mix, -1.0, 1.0)
    interleaved = (pcm * 32767.0).astype("<i2")
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "loop.wav"
        with wave.open(str(wav), "wb") as fh:
            fh.setnchannels(2)
            fh.setsampwidth(2)
            fh.setframerate(SR)
            fh.writeframes(interleaved.tobytes())
        OUT.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(wav),
                        "-codec:a", "libmp3lame", "-b:a", "160k", str(OUT)], check=True)
    return OUT


if __name__ == "__main__":
    path = write_mp3(build())
    print(f"Wrote {path} ({path.stat().st_size} bytes, {LOOP_SECONDS:.1f}s loop at {BPM} BPM)")
