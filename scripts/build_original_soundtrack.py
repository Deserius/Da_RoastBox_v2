#!/usr/bin/env python3
"""Synthesize Da RoastBox's original instrumental assets; no network or paid AI.

All notes and effects are built here from sine waves and seeded noise.  The
MP3s are committed so this optional generation script is not an install step.
Requires numpy and imageio-ffmpeg (in backend requirements) plus optional scipy.
The bundled finished tracks do not require scipy to play.
"""
from __future__ import annotations

import math
import subprocess
import tempfile
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public" / "assets" / "intro"
RNG = np.random.default_rng(20261104)


def time(n):
    return np.arange(n, dtype=np.float64) / SR


def put(dest, source, start, pan=0):
    start = int(start * SR)
    if start >= len(dest):
        return
    source = source[:len(dest) - start]
    # Constant-power panning, modest stereo width.
    left = math.sqrt((1 - pan) / 2)
    right = math.sqrt((1 + pan) / 2)
    dest[start:start + len(source), 0] += source * left
    dest[start:start + len(source), 1] += source * right


def band_noise(seconds, lo, hi):
    n = int(seconds * SR)
    noise = RNG.normal(0, 1, n)
    sos = butter(2, [lo, hi], btype="bandpass", fs=SR, output="sos")
    return sosfilt(sos, noise)


def note(midi, seconds, velocity=1):
    """Warm electric-piano tone; harmonics have their own natural decay."""
    t = time(int(seconds * SR))
    f = 440 * (2 ** ((midi - 69) / 12))
    attack = np.minimum(1, t / .012)
    release = np.minimum(1, np.maximum(0, (seconds - t) / .42))
    env = attack * release * (0.22 + 0.78 * np.exp(-2.2 * t))
    phase = 2 * np.pi * f * t
    return velocity * env * (np.sin(phase + .6 * np.exp(-2.8 * t) * np.sin(2 * phase)) +
                             .13 * np.exp(-1.1 * t) * np.sin(3 * phase) +
                             .045 * np.exp(-2 * t) * np.sin(5 * phase))


def bass(midi, seconds):
    t = time(int(seconds * SR))
    f = 440 * (2 ** ((midi - 69) / 12))
    env = np.minimum(1, t / .01) * np.exp(-2.4 * t) * np.minimum(1, (seconds - t) / .08)
    return env * (np.sin(2 * np.pi * f * t) + .15 * np.sin(4 * np.pi * f * t))


def kick():
    t = time(int(.32 * SR))
    phase = 2 * np.pi * (42 * t + 60 * .035 * (1 - np.exp(-t / .035)))
    return np.sin(phase) * np.exp(-18 * t) + .12 * band_noise(.32, 100, 2000) * np.exp(-70 * t)


def snare():
    t = time(int(.26 * SR))
    return .55 * band_noise(.26, 750, 6500) * np.exp(-18 * t) + .27 * np.sin(2 * np.pi * 180 * t) * np.exp(-30 * t)


def hat():
    t = time(int(.075 * SR))
    return band_noise(.075, 5500, 15000) * np.exp(-66 * t)


def save(data, name):
    peak = float(np.max(np.abs(data))) or 1
    data = np.tanh(data * (0.86 / peak)) / np.tanh(.86) * .80
    pcm = (np.clip(data, -1, 1) * 32767).astype('<i2')
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / 'mix.wav'
        with wave.open(str(wav), 'wb') as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-y',
                        '-i', str(wav), '-codec:a', 'libmp3lame', '-b:a', '160k',
                        str(OUT / name)], check=True)
    print(name, 'duration', round(len(data) / SR, 2), 'seconds')


def create_intro():
    duration = 6.9
    impact = 1.70  # Must match the water contact in cinematic-intro.css.
    out = np.zeros((int(duration * SR), 2), dtype=np.float64)
    t = time(int(impact * SR))
    swell = np.minimum(1, t / .4) * (t / impact) ** 1.6
    whoosh = band_noise(impact, 120, 3200) * swell * .22
    put(out, whoosh, 0, -.18)
    put(out, whoosh * .65, .03, .25)
    # A low sub hit, short metallic bloom, and a textured water collision.
    t = time(int(2.6 * SR))
    phase = 2 * np.pi * (37 * t + 57 * .055 * (1 - np.exp(-t / .055)))
    boom = np.sin(phase) * np.exp(-3.5 * t)
    put(out, boom * 1.05, impact)
    for idx, freq in enumerate([227, 311, 463, 719, 1093]):
        metal = np.sin(2 * np.pi * freq * t + .2 * idx) * np.exp(-(2.4 + idx * .5) * t)
        put(out, metal * (.12 / (idx + 1) ** .45), impact, (-.26 + .13 * idx))
    s = time(int(1.25 * SR))
    splash = band_noise(1.25, 240, 9000) * (np.exp(-5 * s) + .15 * np.exp(-2 * s))
    put(out, splash * .62, impact, -.2)
    put(out, splash * .43, impact + .035, .25)
    # Falling water droplets, all synthesized individually from oscillators.
    for k in range(28):
        when = impact + .15 + float(RNG.random()) * 1.9
        length = .09 + float(RNG.random()) * .10
        tt = time(int(length * SR))
        f = float(RNG.uniform(620, 2100))
        plip = np.sin(2 * np.pi * (f * tt - f * .12 * tt * tt)) * np.exp(-38 * tt)
        put(out, plip * float(RNG.uniform(.012, .038)), when, float(RNG.uniform(-.85, .85)))
    # Very soft, fully original harmonic light reveal.
    for i, midi in enumerate([48, 55, 60, 64, 67]):
        tt = time(int(4.4 * SR)); f = 440 * 2 ** ((midi - 69) / 12)
        env = np.minimum(1, tt / .7) * np.exp(-.72 * tt)
        put(out, .035 * env * np.sin(2 * np.pi * f * tt), impact + .15 + i * .03, (i - 2) * .12)
    # Short stereo reflections; fades prevent clicks.
    dry = out.copy()
    for delay, gain in [(0.07, .10), (.16, .07), (.28, .04)]:
        n = int(delay * SR); out[n:, :] += dry[:-n, ::-1] * gain
    end = int(.5 * SR); out[-end:] *= np.linspace(1, 0, end)[:, None]
    save(out, 'hae-cinematic-original.mp3')


def create_lounge():
    beat = 60 / 80
    bars = 8
    duration = beat * 4 * bars
    # Work with a little tail, fold it back into the loop.
    out = np.zeros((int((duration + 1.2) * SR), 2), dtype=np.float64)
    # Original 8-bar progression: Dm9, G13, Cmaj9, Am9 with a soft hip-hop pulse.
    chords = [[50, 53, 57, 60, 64], [43, 53, 59, 64, 69],
              [48, 52, 55, 59, 62], [45, 52, 55, 59, 60]]
    roots = [38, 43, 36, 45]
    for bar in range(bars):
        start = bar * 4 * beat
        chord = chords[bar % 4]
        for chord_hit, loud in [(0, .29), (2.5, .16)]:
            for j, midi in enumerate(chord):
                offset = j * .014 + float(RNG.uniform(-.007, .007))
                put(out, note(midi, 2.05, loud), start + chord_hit * beat + offset,
                    (j - 2) * .14)
        for pos, pitch, vol in [(0, roots[bar % 4], .26), (1.5, roots[bar % 4], .16),
                                 (2.5, roots[bar % 4] + 7, .18), (3.5, roots[bar % 4], .14)]:
            put(out, bass(pitch, .58) * vol, start + pos * beat)
        for pos in (0, 1.75, 2.75):
            put(out, kick() * .25, start + pos * beat)
        for pos in (1, 3):
            put(out, snare() * .14, start + pos * beat, .08)
        for eighth in range(8):
            p = eighth * .5 + (.045 if eighth % 2 else 0)
            put(out, hat() * (.043 if eighth % 2 else .065), start + p * beat, -.13 if eighth % 2 else .13)
        # A restrained 3-note high-register answering phrase every second bar.
        if bar % 2:
            for pos, midi in [(2.05, chord[-1] + 12), (2.5, chord[-2] + 12), (3, chord[-1] + 12)]:
                put(out, note(midi, .62, .10), start + pos * beat, .28)
    dry = out.copy()
    for delay, gain in [(.079, .10), (.17, .06), (.29, .035)]:
        n = int(delay * SR); out[n:] += dry[:-n, ::-1] * gain
    n = int(duration * SR)
    # Fold the final decay into the beginning so reverb is continuous on loop.
    tail = out[n:]; out = out[:n]; out[:len(tail)] += tail
    save(out, 'roastbox-lounge-original.mp3')


if __name__ == '__main__':
    create_intro()
    create_lounge()
