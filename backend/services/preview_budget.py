"""Shared, count-based limits for optional hosted AI in a disposable preview.

Each attempt is reserved atomically before any paid provider request. Limits are
per UTC day across all preview accounts and API workers. Counts are not a dollar
spending cap; provider pricing and model output length can vary.
"""
from datetime import datetime, timezone
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from config import (ALLOW_PREVIEW_HOSTED_AI, ENABLE_PREVIEW_LOGIN,
                    EMERGENT_LLM_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY, ROAST_WRITER_PROVIDER,
                    PREVIEW_HOSTED_DAILY_SHOW_LIMIT, PREVIEW_HOSTED_DAILY_VOICE_LIMIT)
from db import preview_usage_collection


async def consume_preview_hosted(kind: str) -> None:
    if not ENABLE_PREVIEW_LOGIN or not ALLOW_PREVIEW_HOSTED_AI:
        raise HTTPException(status_code=503, detail="Preview accounts need their own OpenAI API key in Settings; hosted AI is disabled for this preview.")
    if not (EMERGENT_LLM_KEY or OPENAI_API_KEY or (kind == "show" and ROAST_WRITER_PROVIDER == "openrouter" and OPENROUTER_API_KEY)):
        raise HTTPException(status_code=503, detail="No hosted AI key is configured. Add your own OpenAI key in Settings.")
    if kind == "show":
        limit = PREVIEW_HOSTED_DAILY_SHOW_LIMIT
        label = "show attempts"
    elif kind == "voice":
        limit = PREVIEW_HOSTED_DAILY_VOICE_LIMIT
        label = "voice previews"
    else:
        raise ValueError("Unknown preview budget category")
    if limit == 0:
        raise HTTPException(status_code=429, detail=f"Hosted preview {label} are disabled. Use your own OpenAI key in Settings.")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{today}:{kind}"
    try:
        await preview_usage_collection.update_one({"_id": key}, {"$setOnInsert": {"used": 0, "day": today, "kind": kind}}, upsert=True)
    except DuplicateKeyError:
        pass  # Another worker created the daily counter at the same instant.
    if limit < 0:
        # Unlimited: still counted so the workspace can see how much it is using.
        await preview_usage_collection.update_one({"_id": key}, {"$inc": {"used": 1}}, upsert=True)
        return
    result = await preview_usage_collection.update_one({"_id": key, "used": {"$lt": limit}}, {"$inc": {"used": 1}})
    if not result.modified_count:
        raise HTTPException(status_code=429, detail=f"The shared preview limit of {limit} hosted {label} per UTC day is reached. Try tomorrow or add your own OpenAI key in Settings.")
