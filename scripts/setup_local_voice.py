#!/usr/bin/env python3
"""Install and pre-fetch the optional local (Kokoro) voice fallback.

This is entirely optional: the app runs fully without it, always falling back
to "configure an OpenAI or ElevenLabs key" the same way it always has. Running
this once unlocks a free, natural-sounding, key-free voice tier so a roast
never ships silent for lack of a provider key.

Usage
-----
    python scripts/setup_local_voice.py          # install + download, from the project root
    ..\\.venv\\Scripts\\python scripts\\setup_local_voice.py     (Windows, project venv)
    ../.venv/bin/python scripts/setup_local_voice.py             (macOS/Linux, project venv)

What it does
------------
1. Checks the interpreter is one kokoro-onnx supports (3.10-3.13 today).
2. `pip install -r backend/requirements-local-voice.txt`.
3. Downloads the ~150MB Kokoro model weights into backend/models/kokoro/
   (skipped automatically on next run, and also happens lazily on first use
   if you skip this script - this just avoids a multi-minute wait during a
   show's first voice line).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def main() -> int:
    major, minor = sys.version_info[:2]
    if not (3, 10) <= (major, minor) <= (3, 13):
        print(f"Note: kokoro-onnx currently declares support for Python 3.10-3.13; "
              f"this interpreter is {major}.{minor}. The install below may fail - "
              "that's fine, the app works without this optional fallback.")
    print("==> Installing kokoro-onnx (optional local voice fallback)")
    req = BACKEND / "requirements-local-voice.txt"
    result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req)])
    if result.returncode != 0:
        print("\nCould not install the local voice package with this Python version.")
        print("The app still works normally; it will keep requiring an OpenAI or")
        print("ElevenLabs key for voice. To try again, use Python 3.10-3.13.")
        return 1

    print("\n==> Downloading the Kokoro model weights (one-time, ~150MB)")
    sys.path.insert(0, str(BACKEND))
    try:
        from services.kokoro_service import ensure_models, KOKORO_IMPORT_ERROR
    except Exception as e:  # pragma: no cover - import-time failure
        print(f"Could not import the local voice module: {e}")
        return 1
    if KOKORO_IMPORT_ERROR:
        print(f"kokoro-onnx did not import after installing: {KOKORO_IMPORT_ERROR}")
        return 1
    try:
        ensure_models()
    except Exception as e:
        print(f"\nModel download failed: {e}")
        print("Check your internet connection and try again; the app works without")
        print("this fallback in the meantime (requires an OpenAI or ElevenLabs key).")
        return 1

    print("\nLocal voice fallback is ready. No API key is needed for it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
