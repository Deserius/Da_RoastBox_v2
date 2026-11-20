#!/usr/bin/env python3
"""Render real 30/60-second-style reels offline; no user media or providers.

Default: both requested limits, sequentially. --smoke: shorter 30s test.
--seconds 30|60 selects one full test; --battle exercises the winner outro.
The exported reel is at most the chosen length and can be shorter if fewer
complete lines fit. Temp files are deleted after validation.
"""
from __future__ import annotations

import argparse
import io
import re
import resource
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from services.highlight_reel import (  # noqa: E402
    FFMPEG, GAP_S, _font, _wrap, build_timeline, hotseat_frame, intro_length, outro_frame, render_reel, select_highlights,
)


def frame(path: str, at: float) -> Image.Image:
    decoded = subprocess.run([FFMPEG, "-v", "error", "-ss", str(at), "-i", path, "-frames:v", "1",
                              "-vf", "scale=270:480", "-f", "image2pipe", "-vcodec", "png", "-"],
                             check=True, capture_output=True)
    return Image.open(io.BytesIO(decoded.stdout)).convert("RGB")


def exercise(length: int, *, smoke: bool, battle_mode: bool):
    personas = {
        f"persona_{i}": {"id": f"persona_{i}", "image": f"assets/personas/persona_{i}.webp",
                         "displayName": f"Test Roaster {i}", "color": "#ff7136" if i == 1 else "#ffc529"}
        # The 60s test has five selected comics but only two speak in the
        # fixture, ensuring the reel entrance still includes the full cast.
        for i in (range(1, 6) if length == 60 else (1, 2))
    }
    reactions = ("none", "small", "big", "explosive")
    beats = [{"persona_id": f"persona_{1 + i % 2}", "image_index": i % 2, "type": "punchline",
              "text": f"Test beat number {i + 1} adds several words so the captions reveal over the voice.",
              "laugh_after": reactions[i % len(reactions)], "reaction": "laugh", "rapid_fire": True}
             for i in range(2 if smoke else 8)]
    voice = (BACKEND / "assets/sfx/laugh_big_1.mp3").read_bytes()
    photos = [(BACKEND / f"assets/personas/persona_{i}.webp").read_bytes() for i in (1, 2)]
    battle = {"winner": "persona_1", "scores": {"persona_1": 8, "persona_2": 4}} if battle_mode else None
    video = render_reel(beats=beats, voice_files=[voice] * len(beats), personas=personas,
                        photos=photos, subject_name="Offline test", battle=battle, max_seconds=length)
    assert len(video) > 100_000 and b"ftyp" in video[:40]
    with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
        f.write(video)
        f.flush()
        probe = subprocess.run([FFMPEG, "-hide_banner", "-i", f.name], capture_output=True, text=True).stderr
        assert "1080x1920" in probe and "h264" in probe.lower() and "30 fps" in probe, probe
        assert "Audio: aac" in probe, probe
        match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe)
        assert match, probe
        duration = int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])
        assert 8 < duration <= length + 0.1, duration
        if not smoke and length == 60:
            assert duration > 40, duration
        if not smoke and length == 30:
            assert duration > 20, duration
        decoded = subprocess.run([FFMPEG, "-v", "error", "-i", f.name, "-f", "null", "-"], capture_output=True)
        assert decoded.returncode == 0, decoded.stderr.decode(errors="replace")
        # Both timestamps are in the same splash keyframe. Visible differences
        # prove the ffmpeg camera move is continuous, not just a slideshow.
        a, b = frame(f.name, 0.27), frame(f.name, 0.32)
        change = sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3
        assert change > 0.08, f"Expected smooth in-between-frame motion, got {change}"
        # A deliberate gap belongs to the hot-seat reveal, not the first
        # caption, and the final branded scene must not be truncated.
        guest = Image.open(io.BytesIO(photos[0])).convert("RGB")
        reveal = hotseat_frame(guest, "Offline test", battle_mode).resize((270, 480))
        actual_reveal = frame(f.name, intro_length(len(personas)) + GAP_S / 2)
        reveal_delta = sum(ImageStat.Stat(ImageChops.difference(actual_reveal, reveal)).mean) / 3
        assert reveal_delta < 24, f"First caption appeared before its voice: {reveal_delta}"
        expected_outro = outro_frame(guest, battle, personas, "Offline test").resize((270, 480))
        actual_outro = frame(f.name, duration - 0.4)
        outro_delta = sum(ImageStat.Stat(ImageChops.difference(actual_outro, expected_outro)).mean) / 3
        assert outro_delta < 24, f"Branded outro missing/truncated: {outro_delta}"
    print(f"PASS: offline {'battle' if battle_mode else 'roast'} {length}s-limit reel: "
          f"{duration:.1f}s, 1080×1920 H.264/AAC, {len(video)} bytes, "
          f"motion delta {change:.2f}, peak Python RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024} MiB")


def unit_checks():
    beats = [{"persona_id": "a", "type": "punchline", "laugh_after": "big"}]
    assert not select_highlights(beats, [100.0], 30, 1), "Do not cut a too-long voice in mid-sentence"
    for length in (30, 60):
        many = beats * 12
        picked = select_highlights(many, [5.0] * len(many), length, 2)
        _, _, total = build_timeline([many[i] for i in picked], [5.0] * len(picked), 2)
        assert picked and picked == sorted(picked) and total <= length
    image = Image.new("RGB", (1080, 100))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    font = _font(51, False)
    lines = _wrap(draw, "VERYLONGUNBROKENNAME" * 12, font, 820)
    assert len(lines) > 1 and all(draw.textlength(line, font=font) <= 820 for line in lines)
    print("PASS: highlight budgets, whole-line selection and long-word caption wrapping")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--seconds", type=int, choices=(30, 60))
    parser.add_argument("--battle", action="store_true")
    args = parser.parse_args()
    unit_checks()
    lengths = [args.seconds] if args.seconds else ([30] if args.smoke else [30, 60])
    for length in lengths:
        exercise(length, smoke=args.smoke, battle_mode=args.battle)


if __name__ == "__main__":
    main()
