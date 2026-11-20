"""BYOK API key management for OpenAI and ElevenLabs."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from auth_deps import get_current_user
from models import User
from db import users_collection
from crypto_utils import encrypt

router = APIRouter(prefix="/voice-settings", tags=["voice-settings"])


class KeysBody(BaseModel):
    openai_key: Optional[str] = None
    elevenlabs_key: Optional[str] = None


@router.post("/keys")
async def update_keys(body: KeysBody, current_user: User = Depends(get_current_user)):
    update = {}
    if body.openai_key is not None:
        if body.openai_key.strip():
            update["openai_key_encrypted"] = encrypt(body.openai_key.strip())
            update["has_byok_openai"] = True
        else:
            update["openai_key_encrypted"] = None
            update["has_byok_openai"] = False
    if body.elevenlabs_key is not None:
        if body.elevenlabs_key.strip():
            update["elevenlabs_key_encrypted"] = encrypt(body.elevenlabs_key.strip())
            update["has_byok_elevenlabs"] = True
        else:
            update["elevenlabs_key_encrypted"] = None
            update["has_byok_elevenlabs"] = False
    if not update:
        raise HTTPException(status_code=400, detail="No keys provided")

    await users_collection.update_one({"id": current_user.id}, {"$set": update})
    return {"status": "ok",
            "has_byok_openai": update.get("has_byok_openai", current_user.has_byok_openai),
            "has_byok_elevenlabs": update.get("has_byok_elevenlabs", current_user.has_byok_elevenlabs)}


@router.delete("/keys")
async def clear_keys(current_user: User = Depends(get_current_user)):
    await users_collection.update_one(
        {"id": current_user.id},
        {"$set": {
            "openai_key_encrypted": None, "has_byok_openai": False,
            "elevenlabs_key_encrypted": None, "has_byok_elevenlabs": False,
        }},
    )
    return {"status": "ok"}
