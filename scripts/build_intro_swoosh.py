#!/usr/bin/env python3
"""Mix a locally synthesized rising swoosh into the existing HAE impact track."""
import math, subprocess, tempfile, wave
from pathlib import Path
import numpy as np
import imageio_ffmpeg
from scipy.signal import butter, sosfilt
root = Path(__file__).resolve().parents[1]
folder = root / 'frontend/public/assets/intro'
sr = 44100
rng = np.random.default_rng(20261105)
t = np.arange(int(sr * 6.9)) / sr
# Rising filtered air before the 1.7s logo impact, then a brief water wash.
noise = sosfilt(butter(3, [350, 6800], btype='bandpass', fs=sr, output='sos'), rng.normal(size=t.size))
rise = np.clip((t - .18) / 1.48, 0, 1)
env = np.where((t >= .18) & (t < 1.7), np.sin(np.pi * rise / 2) ** 2, 0)
wash_t = np.maximum(0, t - 1.7)
wash = np.where((t >= 1.7) & (t < 2.7), np.exp(-4.8 * wash_t), 0)
osc = np.sin(2 * np.pi * (260 * t + 190 * t * t))
audio = np.clip(.20 * noise * env + .025 * osc * env + .13 * noise * wash, -1, 1)
with tempfile.TemporaryDirectory() as tmp:
    sound = Path(tmp) / 'swoosh.wav'
    with wave.open(str(sound), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((audio * 32767).astype('<i2').tobytes())
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error', '-i', str(folder/'hae-cinematic-impact.mp3'), '-i', str(sound), '-filter_complex', '[0:a]volume=0.85[a];[a][1:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.92[out]', '-map', '[out]', '-codec:a', 'libmp3lame', '-b:a', '160k', str(folder/'hae-cinematic-swoosh.mp3')], check=True)
print('Generated original swoosh mix.')
