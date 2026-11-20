#!/usr/bin/env python3
"""Offline checks for preview usage limits: 0 disabled, N capped, -1 unlimited."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

import services.preview_budget as pb


class FakeCollection:
    def __init__(self):
        self.docs = {}

    async def update_one(self, flt, update, upsert=False):
        key = flt["_id"]
        inserted = key not in self.docs
        doc = self.docs.setdefault(key, {"used": 0})
        # Mongo only applies $setOnInsert when the upsert actually inserts.
        if "$setOnInsert" in update and inserted:
            doc.update(update["$setOnInsert"])
        if "$inc" in update:
            if "used" in flt and not doc["used"] < flt["used"]["$lt"]:
                return type("R", (), {"modified_count": 0})()
            doc["used"] += update["$inc"]["used"]
        return type("R", (), {"modified_count": 1})()


async def attempt(patch_limit, times):
    fake = FakeCollection()
    with __import__("unittest.mock", fromlist=["patch"]).patch.object(pb, "preview_usage_collection", fake), \
         __import__("unittest.mock", fromlist=["patch"]).patch.object(pb, "PREVIEW_HOSTED_DAILY_SHOW_LIMIT", patch_limit), \
         __import__("unittest.mock", fromlist=["patch"]).patch.object(pb, "ENABLE_PREVIEW_LOGIN", True), \
         __import__("unittest.mock", fromlist=["patch"]).patch.object(pb, "ALLOW_PREVIEW_HOSTED_AI", True), \
         __import__("unittest.mock", fromlist=["patch"]).patch.object(pb, "EMERGENT_LLM_KEY", "fake"), \
         __import__("unittest.mock", fromlist=["patch"]).patch.object(pb, "OPENAI_API_KEY", ""), \
         __import__("unittest.mock", fromlist=["patch"]).patch.object(pb, "OPENROUTER_API_KEY", ""), \
         __import__("unittest.mock", fromlist=["patch"]).patch.object(pb, "ROAST_WRITER_PROVIDER", "existing"):
        allowed = 0
        for _ in range(times):
            try:
                await pb.consume_preview_hosted("show")
                allowed += 1
            except HTTPException as exc:
                return allowed, exc.status_code
        return allowed, None


async def main():
    allowed, status = await attempt(0, 3)
    assert allowed == 0 and status == 429, (allowed, status)
    allowed, status = await attempt(3, 10)
    assert allowed == 3 and status == 429, (allowed, status)
    allowed, status = await attempt(-1, 500)
    assert allowed == 500 and status is None, (allowed, status)

asyncio.run(main())
print("PASS: preview limits — 0 blocks, 3 caps at three, -1 never blocks (500 attempts)")
