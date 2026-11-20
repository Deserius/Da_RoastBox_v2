"""Command-line health report. Usage: python scripts/diagnose.py [--deep]

Checks config, persona data integrity and (with --deep) live calls to Mongo, LLM, TTS, Stripe, ElevenLabs.
Exit code 0 = healthy, 1 = degraded.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routes import diagnostics  # noqa: E402


async def main() -> int:
    deep = "--deep" in sys.argv
    report = await diagnostics.diagnostics(deep=deep, user=object() if deep else None)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" and not report["personas"]["missing_images"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
