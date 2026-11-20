#!/usr/bin/env python3
"""Offline real-FFmpeg checks for the reel's voice-first crowd envelope.

Synthetic signals only; no provider calls or user media. The test measures the
rendered waveform, including two closely spaced voice windows, rather than
checking the expression string alone.
"""
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.highlight_reel import (  # noqa: E402
    FFMPEG, REEL_CROWD_GAIN, REEL_ROOM_GAIN, SPEECH_DUCK, _crowd_duck_expression,
)


def rms(data, rate, begin, end):
    values = data[int(rate * begin):int(rate * end)]
    return float(np.sqrt(np.mean(values * values)))


def main():
    assert 0.35 <= REEL_CROWD_GAIN <= 0.50 and 0.08 <= REEL_ROOM_GAIN <= 0.12
    assert 0 < SPEECH_DUCK <= 0.1
    rate = 48000
    windows = [(1.0, 2.0), (2.10, 3.0)]
    envelope = _crowd_duck_expression(windows)
    proc = subprocess.run(
        [FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=220:sample_rate={rate}:duration=4",
         "-af", f"volume='{envelope}':eval=frame", "-f", "f32le", "-ac", "1", "-ar", str(rate), "-"],
        check=True, capture_output=True,
    )
    sound = np.frombuffer(proc.stdout, dtype="<f4")
    baseline = rms(sound, rate, 0.4, 0.8)
    talking = rms(sound, rate, 1.15, 1.85)
    between = rms(sound, rate, 2.03, 2.07)
    second = rms(sound, rate, 2.3, 2.8)
    recovered = rms(sound, rate, 3.4, 3.8)
    assert 0.97 < recovered / baseline < 1.03, (baseline, recovered)
    assert abs(talking / baseline - SPEECH_DUCK) < 0.01, talking / baseline
    assert abs(second / baseline - SPEECH_DUCK) < 0.01, second / baseline
    assert between / baseline < 0.5, "Close lines must not restore the crowd to full level between voices"
    # No voices means the room remains at its natural, slightly reduced level.
    assert _crowd_duck_expression([]) == "1"
    # Invalid/empty intervals cannot produce a permanent duck or invalid math.
    assert _crowd_duck_expression([(2, 2), (3, 1)]) == "1"
    print(f"PASS: real FFmpeg envelope: speech crowd={talking / baseline:.2f}×, "
          f"close-line gap={between / baseline:.2f}×, recovery={recovered / baseline:.2f}×")


if __name__ == "__main__":
    main()
