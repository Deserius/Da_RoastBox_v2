"""Generate missing persona portraits via Gemini Nano Banana. Usage: python scripts/generate_persona_portraits.py [--force id ...]"""
import asyncio
import base64
import io
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

from emergentintegrations.llm.chat import LlmChat, UserMessage  # noqa: E402
from PIL import Image  # noqa: E402

OUT_DIR = BACKEND_DIR.parent / "frontend" / "public" / "assets" / "personas"
PERSONAS = json.loads((BACKEND_DIR / "data" / "personas.json").read_text())

STYLE_PREFIX = (
    "Comic-book bust portrait of a stand-up roast battle comedian character, "
    "square 1:1 frame, expressive face, exaggerated cartoon features, vibrant color palette, "
    "graffiti brick-wall urban backdrop with a spotlight, bold ink outlines, halftone shading, cinematic lighting. "
    "Centered head & shoulders. No text, no letters, no logos, no watermarks. Single character."
)


def _prompt(p: dict) -> str:
    tier = "PREMIUM elite roaster, luxurious gold rim-light accents. " if p.get("tier") == "premium" else ""
    return (f"{STYLE_PREFIX}\n\n{tier}Character: {p['name']} — {p['role']}, age {p.get('age')}, {p.get('gender')}. "
            f"{p['description']} Signature colour {p.get('color')}. Vibe: {p.get('tagline')}.")


async def gen_one(api_key: str, p: dict, force: bool) -> bool:
    out = OUT_DIR / Path(p["image"]).name
    if out.exists() and out.stat().st_size > 10_000 and not force:
        return True
    for attempt in range(3):
        try:
            chat = LlmChat(api_key=api_key, session_id=f"roastbox-portrait-{p['id']}-{attempt}",
                           system_message="You generate single-character comic book bust portraits.")
            chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
            _text, images = await chat.send_message_multimodal_response(UserMessage(text=_prompt(p)))
            if images:
                img = Image.open(io.BytesIO(base64.b64decode(images[0]["data"]))).convert("RGB")
                img.thumbnail((384, 384))
                img.save(out, "WEBP", quality=82)
                print(f"OK {p['id']} -> {out.name}")
                return True
        except Exception as e:
            print(f"ERR {p['id']} attempt {attempt + 1}: {e}")
    return False


async def main():
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        sys.exit("Missing EMERGENT_LLM_KEY")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    force_ids = set(sys.argv[2:]) if len(sys.argv) > 1 and sys.argv[1] == "--force" else set()
    results = await asyncio.gather(*[gen_one(key, p, p["id"] in force_ids) for p in PERSONAS])
    print(f"DONE {sum(results)}/{len(results)} portraits present")


if __name__ == "__main__":
    asyncio.run(main())
