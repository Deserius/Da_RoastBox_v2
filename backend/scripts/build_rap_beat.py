#!/usr/bin/env python3
"""Synthesize an original 90 BPM four-bar instrumental loop locally; no external samples."""
import math
import wave
import tempfile
import subprocess
from pathlib import Path
import numpy as np
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[2]
RATE, BPM, BARS = 44100, 90, 4
N = int(RATE * 60 / BPM * 4 * BARS)
a = np.zeros(N, dtype=np.float64)
rng = np.random.default_rng(77123)

def put(pos, wave):
    i = int(pos * RATE); end = min(N, i + len(wave))
    if i < N: a[i:end] += wave[:end-i]

def kick(pos):
    t = np.arange(int(RATE*.31))/RATE
    f = 47*t + (95/35)*(1-np.exp(-35*t))
    put(pos, .62*np.sin(2*np.pi*f)*np.exp(-t*11))

def snare(pos):
    t = np.arange(int(RATE*.19))/RATE
    noise = rng.standard_normal(len(t))
    put(pos, .17*noise*np.exp(-t*24) + .11*np.sin(2*np.pi*180*t)*np.exp(-t*20))

def hat(pos, vol):
    t = np.arange(int(RATE*.055))/RATE
    noise = rng.standard_normal(len(t)); noise = noise - np.convolve(noise,np.ones(7)/7,'same')
    put(pos, vol*noise*np.exp(-t*65))

def bass(pos, hz, duration):
    t = np.arange(int(RATE*duration))/RATE
    env = np.minimum(1,t*50)*np.maximum(0,1-t/duration)**1.3
    put(pos, .20*(np.sin(2*np.pi*hz*t)+.22*np.sin(4*np.pi*hz*t))*env)

beat = 60/BPM
for bar in range(BARS):
    start=bar*4*beat
    for x in (0, 1.5, 2.75): kick(start+x*beat)
    for x in (1,3): snare(start+x*beat)
    for i in range(8): hat(start+i*beat/2, .045 if i%2 else .065)
    for x,hz in ((0,55),(1.5,65.41),(2.75,49)): bass(start+x*beat,hz,beat*.55)
# Gentle ends avoid an audible loop seam. Peak control is independent of playback gain.
fade=int(RATE*.012);a[:fade]*=np.linspace(0,1,fade);a[-fade:]*=np.linspace(1,0,fade)
a=np.tanh(a*1.1)*.85
with tempfile.TemporaryDirectory() as d:
    wav=Path(d)/'beat.wav'; mp3=Path(d)/'beat.mp3'
    with wave.open(str(wav),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(RATE);f.writeframes((np.clip(a,-1,1)*32767).astype('<i2').tobytes())
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-v','error','-i',str(wav),'-codec:a','libmp3lame','-b:a','160k',str(mp3)],check=True)
    for dest in [ROOT/'frontend/public/assets/sfx/crowd/rap_beat.mp3',ROOT/'backend/assets/sfx/rap_beat.mp3']:
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(mp3.read_bytes())
print('Generated original 90 BPM loop for theater and reels.')
