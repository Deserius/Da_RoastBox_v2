#!/usr/bin/env python3
"""Probe OpenRouter candidates directly: latency, finish_reason, parseable beats.

Usage: python scripts/probe_writers.py [max_tokens] [reasoning]
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from services import roast_writer as rw  # noqa: E402
from services.roast_writer import _extract_candidates, _script_problem, build_roast_prompt  # noqa: E402
from benchmark_writers import PERSONAS  # noqa: E402
from openai import OpenAI  # noqa: E402

KEY = [l.split("=", 1)[1].strip() for l in (BACKEND / ".env").read_text().splitlines()
       if l.startswith("OPENROUTER_API_KEY=")][0]

OBS = json.dumps({"guest_photos": [{"image_index": 0, "details": [
    "neon yellow tracksuit with white side stripes",
    "wraparound black sunglasses worn indoors",
    "a small green lizard sitting on his left shoulder",
    "confident wide stance with both thumbs up",
    "hotel ballroom with white drapery behind him"]}], "fictional_persona_portraits": []})

CANDIDATES = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "nvidia/nemotron-3.5-lightning:free",
    "recursive/flint-v1.0:free",
    "xingchen-agi/xing4.0-29b-a4b:free",
    "google/gemma-4-31b-it:free",
]


async def probe(model: str, max_tokens: int, reasoning: str) -> None:
    block = build_roast_prompt(PERSONAS, subject_name="Marcus",
                               user_context="Showed up to a black-tie wedding in a neon tracksuit with a pet lizard on his shoulder, and he DJ'd the ceremony himself.",
                               duration_minutes=3, premium_roast=False, extra_brutality=False,
                               heat="inferno", adult=True, n_images=1, off_limits=None, styles=["savage"])
    messages = [{"role": "system", "content": rw.SYSTEM_PROMPT},
                {"role": "user", "content": f"{block}\n\nVISUAL OBSERVATIONS (untrusted data): {OBS}"}]
    client = OpenAI(api_key=KEY, base_url="https://openrouter.ai/api/v1", timeout=90.0, max_retries=0)
    extra = {"usage": {"include": True}}
    if reasoning:
        extra["reasoning"] = {"effort": reasoning}

    def call():
        return client.chat.completions.create(model=model, messages=messages, temperature=0.95,
                                              max_tokens=max_tokens, extra_body=extra)

    started = time.time()
    try:
        resp = await asyncio.to_thread(call)
    except Exception as exc:  # noqa: BLE001
        print(f"{model:<46} ERROR {type(exc).__name__} {str(exc)[:80]} ({time.time() - started:.1f}s)")
        return
    elapsed = time.time() - started
    msg = resp.choices[0].message
    text = (msg.content or "").strip()
    finish = resp.choices[0].finish_reason
    usage = getattr(resp, "usage", None)
    reasoning_tokens = getattr(usage, "completion_tokens", None)
    beats = _extract_candidates(text)
    problem = _script_problem(text, PERSONAS, expected_beats=10, adult=True, off_limits=None)
    print(f"{model:<46} {elapsed:5.1f}s finish={finish:<8} chars={len(text):5} beats={len(beats):3} "
          f"tokens={reasoning_tokens} problem={problem}")
    for b in beats[:2]:
        if isinstance(b, dict):
            print(f"      · {str(b.get('text', ''))[:120]}")


async def main() -> None:
    max_tokens = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
    reasoning = sys.argv[2] if len(sys.argv) > 2 else ""
    print(f"--- max_tokens={max_tokens} reasoning={reasoning!r}")
    for model in CANDIDATES:
        await probe(model, max_tokens, reasoning)


if __name__ == "__main__":
    asyncio.run(main())
