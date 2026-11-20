#!/usr/bin/env python3
"""Compare candidate OpenRouter writers on the same roast: latency, length, craft.

Usage: python scripts/benchmark_writers.py [model_id ...]
Prints each model's beats so quality can be judged, plus structural heuristics.
"""
from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from services import roast_writer as rw  # noqa: E402

FIXTURE = Path("/tmp/bench_subject.jpg")


def make_photo() -> bytes:
    if not FIXTURE.exists():
        img = Image.new("RGB", (760, 760), (96, 132, 176))
        d = ImageDraw.Draw(img)
        d.ellipse((220, 120, 540, 440), fill=(236, 200, 168))
        d.rectangle((210, 150, 550, 205), fill=(38, 38, 44))
        d.rectangle((150, 470, 610, 700), fill=(196, 74, 74))
        d.rectangle((300, 250, 460, 300), fill=(30, 30, 30))
        img.save(FIXTURE, "JPEG", quality=88)
    return FIXTURE.read_bytes()


PERSONAS = [
    {"id": "persona_1", "displayName": "Big T", "name": "Big T", "role": "Street-corner philosopher",
     "cadence": "slow, booming", "quirks_prompt": "Loud, affectionate bully who hugs you while he buries you.",
     "lingo": ["ayo", "my guy"], "topics": ["hustle", "family"], "image": "assets/personas/persona_1.webp",
     "punchlines": ["My guy brought a knife to a gun fight, and the knife was plastic."],
     "comic_inspiration": ""},
    {"id": "persona_2", "displayName": "Roxy Vega", "name": "Roxy Vega", "role": "Club-headliner savant",
     "cadence": "fast, slicing", "quirks_prompt": "Sweet smile, surgical insults, flirts while she eviscerates.",
     "lingo": ["babe", "honestly"], "topics": ["dating", "money"], "image": "assets/personas/persona_2.webp",
     "punchlines": ["You're not a red flag, you're the whole clearance aisle."],
     "comic_inspiration": ""},
]

BANNED = ("if i'm being honest", "let's be real", "no offense", "at least you have", "your mom",
          "in conclusion", "it's worth noting", "a testament to")


def heuristics(beats: list[dict]) -> dict:
    lines = [b["text"].strip() for b in beats]
    words = [len(l.split()) for l in lines]
    openers = [re.match(r"^(?:you|he|she|they) (?:look|looks) like\b", l, re.I) for l in lines]
    enders = sum(1 for l in lines if re.search(r"[.!?\"']$", l))
    profane = sum(1 for l in lines if rw._CLEAN_WORDS.search(l))
    # A punchline beat should end on a concrete noun/verb: proxy = last word length >= 4.
    last_words = [re.sub(r"[^\w']", "", l.split()[-1]).lower() if l.split() else "" for l in lines]
    concrete_end = sum(1 for w in last_words if len(w) >= 4)
    return {
        "beats": len(lines),
        "avg_words": round(sum(words) / max(1, len(words)), 1),
        "min_words": min(words) if words else 0,
        "max_words": max(words) if words else 0,
        "generic_openers": sum(1 for o in openers if o),
        "punctuated": enders,
        "adult_lines": profane,
        "concrete_ending": concrete_end,
        "banned_hits": sum(1 for l in lines if any(b in l.casefold() for b in BANNED)),
        "repeated_first_three": len(lines) - len({l.casefold()[:24] for l in lines}),
    }


_orig_problem = rw._script_problem


def _logged_problem(text, personas, **kw):
    reason = _orig_problem(text, personas, **kw)
    if reason:
        print(f"    [check rejected: {reason}] first 220 chars: {text[:220]!r}")
    return reason


async def run(model: str) -> None:
    rw.ROAST_WRITER_MODEL = model
    rw._script_problem = _logged_problem
    rw.ROAST_FREE_BACKUP_MODEL = ""
    rw.ROAST_FREE_PREMIUM_MODEL = model
    block = rw.build_roast_prompt(PERSONAS, subject_name="Marcus",
                                 user_context="Showed up to a black-tie wedding in a neon tracksuit with a pet lizard on his shoulder, and he DJ'd the ceremony himself.",
                                 duration_minutes=3, premium_roast=False, extra_brutality=False,
                                 heat="inferno", adult=True, n_images=1, off_limits=None, styles=["savage"])
    started = time.time()
    try:
        beats = await rw.write_script(block, PERSONAS, [make_photo()], ["image/jpeg"],
                                      expected_beats=rw._target_beats(3), adult=True)
    except Exception as exc:  # noqa: BLE001
        print(f"\n### {model}: FAILED {type(exc).__name__}: {str(exc)[:160]}  ({time.time() - started:.1f}s)")
        return
    elapsed = time.time() - started
    print(f"\n### {model}  ({elapsed:.1f}s)")
    print("   ", heuristics(beats))
    for b in beats:
        print(f"   [{b['persona_id']}/{b['type']}/{b['laugh_after']}] {b['text']}")


async def main(models: list[str]) -> None:
    for model in models:
        await run(model)


if __name__ == "__main__":
    models = sys.argv[1:] or ["nvidia/nemotron-3.5-super-vl:free", "nvidia/nemotron-3.5-lightning:free",
                              "nvidia/nemotron-3-ultra-550b-a55b:free", "google/gemma-4-31b-it:free",
                              "recursive/flint-v1.0:free", "xingchen-agi/xing4.0-29b-a4b:free"]
    asyncio.run(main(models))
