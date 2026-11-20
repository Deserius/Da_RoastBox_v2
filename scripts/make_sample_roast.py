#!/usr/bin/env python3
"""Create (or reuse) one sample roast for manual/API checks. Prints the roast id.

Usage: python scripts/make_sample_roast.py [minutes] [tier]
Reuses the newest roast in history unless --force is passed.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roastbox_session import client as session_client
from PIL import Image, ImageDraw

FIXTURE = Path("/tmp/roastbox_sample_subject.jpg")


def make_photo() -> bytes:
    if not FIXTURE.exists():
        img = Image.new("RGB", (760, 760), (96, 132, 176))
        d = ImageDraw.Draw(img)
        d.ellipse((220, 120, 540, 440), fill=(236, 200, 168))      # head
        d.rectangle((210, 150, 550, 200), fill=(38, 38, 44))        # hair / cap
        d.rectangle((150, 470, 610, 700), fill=(196, 74, 74))       # loud shirt
        d.rectangle((300, 250, 460, 300), fill=(30, 30, 30))        # sunglasses
        img.save(FIXTURE, "JPEG", quality=88)
    return FIXTURE.read_bytes()


def main() -> int:
    minutes = sys.argv[1] if len(sys.argv) > 1 else "3"
    tier = sys.argv[2] if len(sys.argv) > 2 else "standard"
    force = "--force" in sys.argv
    with session_client() as c:
        if not force:
            history = c.get("/roast/history").json().get("history", [])
            if history:
                print(history[0]["id"])
                return 0
        started = time.time()
        res = None
        for attempt in range(3):
            res = c.post("/roast/generate", files={"images": ("subject.jpg", make_photo(), "image/jpeg")},
                         data={"persona_ids": "persona_1,persona_2", "subject_name": "Reel Test Guest",
                               "user_context": "Showed up to a black-tie wedding in a neon tracksuit with a pet lizard on his shoulder.",
                               "duration_minutes": minutes, "roast_tier": tier, "adult_language": "true", "heat": "fire"})
            if res.status_code == 200:
                break
            print(f"  attempt {attempt + 1}: {res.status_code} {res.text[:160]}", flush=True)
            time.sleep(3)
        if res.status_code != 200:
            raise SystemExit(f"generation failed: {res.status_code} {res.text[:300]}")
        data = res.json()
        print(data["roast_id"])
        print(f"  beats={len(data['transcript'])} elapsed={time.time() - started:.1f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
