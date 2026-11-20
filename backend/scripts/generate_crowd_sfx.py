"""Generate the comedy-club crowd SFX library via fal.ai ElevenLabs Sound Effects v2 (Emergent Universal Key).

Usage: python scripts/generate_crowd_sfx.py [--force] [name ...]
Writes frontend/public/assets/sfx/crowd/<name>.mp3. Existing files are skipped unless --force.
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
# Fal Universal Key supports queue inference through the Emergent proxy only, not Fal Platform APIs.
PROXY_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
CONTROL_BASE = f"{PROXY_BASE.rstrip('/')}/api/v1/fal"
ENDPOINT = "fal-ai/elevenlabs/sound-effects/v2"
OUT_DIR = BACKEND_DIR.parent / "frontend" / "public" / "assets" / "sfx" / "crowd"

ROOM = "recorded live inside a packed 200-seat underground comedy club, natural room reverb, real human audience, no music"
SFX = {
    "room_tone": ("Quiet bar room ambience: soft indistinct murmur of seated people, a glass clinks, a chair creaks. No laughter, no applause, no voices standing out, no music. Steady, calm, loopable background", 14, True),
    "intro_cheer": (f"Audience whoops, cheers and applauds loudly as the roast host walks on stage, whistles, {ROOM}", 6, False),
    "chuckle_1": (f"A few scattered audience members chuckle and snicker at a subtle joke, short and natural, {ROOM}", 2.2, False),
    "chuckle_2": (f"Light ripple of amused laughter through part of the crowd, a couple of 'heh's, quickly fading, {ROOM}", 2.2, False),
    "laugh_med_1": (f"Whole audience laughs genuinely at a good punchline, warm hearty laughter that swells then settles, {ROOM}", 3.5, False),
    "laugh_med_2": (f"Crowd bursts into solid laughter with a few people clapping once, natural decay into murmurs, {ROOM}", 3.5, False),
    "laugh_big_1": (f"Packed audience erupts into huge roaring belly laughter, people howling and slapping tables, a whistle, long tail, {ROOM}", 5, False),
    "laugh_big_2": (f"Room explodes with uncontrollable laughter, some people screaming with laughter, scattered clapping, {ROOM}", 5, False),
    "explosive_1": (f"Massive roaring laughter that turns into thunderous applause and cheering, whistles, stomping, crowd going wild after a brutal roast closer, {ROOM}", 8, False),
    "explosive_2": (f"Audience loses it completely: screaming laughter, standing ovation applause, people yelling 'OHHH' and cheering, {ROOM}", 8, False),
    "ooh_1": (f"Large crowd of people all shouting a long loud drawn-out 'OOOOOOOHHHHH' in unison together, like reacting to a savage burn at a roast battle, followed by laughter, {ROOM}", 4, False),
    "ooh_2": (f"Big audience gasping then yelling 'OHHHHHH!' together in shock, men and women, then cheering and laughing, {ROOM}", 4, False),
    "groan_1": (f"Audience groans 'awwww' and 'ughhh' at a terrible dark joke, mixed with guilty laughter, {ROOM}", 3, False),
    "applause_outro": (f"Long enthusiastic applause and cheering as the roast show ends, whistles and 'woo's, {ROOM}", 7, False),
}


def _headers(extra=None):
    h = {"Authorization": f"Bearer {EMERGENT_LLM_KEY}", "Content-Type": "application/json"}
    if os.environ.get("job_id"):
        h["X-App-ID"] = h["X-Job-ID"] = os.environ["job_id"]
    if extra:
        h.update(extra)
    return h


def _trusted(url: str) -> str:
    c, base = urlparse(url), urlparse(f"{CONTROL_BASE}/queue/")
    if c.scheme != base.scheme or c.netloc != base.netloc or not c.path.startswith(base.path):
        raise RuntimeError("untrusted queue URL")
    return url


def _get(url, deadline):
    delay = 1
    for attempt in range(5):
        try:
            return requests.get(url, headers=_headers(), timeout=30)
        except (requests.ConnectTimeout, requests.ReadTimeout, requests.ConnectionError):
            if attempt == 4 or time.monotonic() + delay > deadline:
                raise
            time.sleep(delay)
            delay *= 2


def generate(name: str, prompt: str, seconds: float, loop: bool, force: bool) -> str:
    out = OUT_DIR / f"{name}.mp3"
    if out.exists() and out.stat().st_size > 5000 and not force:
        return f"SKIP {name}"
    payload = {"text": prompt[:450], "duration_seconds": seconds, "prompt_influence": 0.55,
               "loop": loop, "output_format": "mp3_44100_128"}
    r = requests.post(f"{CONTROL_BASE}/proxy", headers=_headers({"X-Fal-Target-Url": f"https://queue.fal.run/{ENDPOINT}"}),
                      json=payload, timeout=60)
    if r.status_code == 402:
        return f"FAIL {name}: insufficient Universal Key balance"
    r.raise_for_status()
    sub = r.json()
    status_url, response_url = _trusted(sub["status_url"]), _trusted(sub["response_url"])
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        st = _get(status_url, deadline).json()
        s = (st.get("status") or "").upper()
        if s in {"COMPLETED", "OK"}:
            res = _get(response_url, deadline).json()
            audio = requests.get(res["audio"]["url"], timeout=60)
            audio.raise_for_status()
            out.write_bytes(audio.content)
            return f"OK {name} ({len(audio.content)} bytes)"
        if s in {"FAILED", "CANCELLED", "CANCELED", "ERROR"}:
            return f"FAIL {name}: {s}"
        time.sleep(2)
    return f"FAIL {name}: timeout"


def main():
    force = "--force" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=5) as pool:
        for line in pool.map(lambda kv: generate(kv[0], *kv[1], force), [kv for kv in SFX.items() if not only or kv[0] in only]):
            print(line, flush=True)


if __name__ == "__main__":
    main()
