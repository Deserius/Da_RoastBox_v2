"""Public share pages for roasts and battles (no auth, no owner data)."""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from db import roasts_collection
from routes.personas import get_personas_by_ids
from services.storage import get_blob
from services.audio_mastering import load_voice_audio
from services.roast_engine import VISIBLE_BILLING

router = APIRouter(prefix="/share", tags=["share"])

PUBLIC_PERSONA_FIELDS = ("id", "name", "displayName", "tagline", "role", "color", "image", "tier", "comic_inspiration")
PUBLIC_BEAT_FIELDS = ("persona_id", "type", "text", "emotion", "laugh_after", "reaction",
                      "pause_before_ms", "pause_after_ms", "audio_url", "image_index", "rapid_fire")


async def _shared_doc(share_id: str):
    doc = await roasts_collection.find_one({"share_id": share_id, "billing_state": VISIBLE_BILLING}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="This roast was deleted or never existed")
    return doc


@router.get("/{share_id}")
async def get_shared(share_id: str):
    doc = await _shared_doc(share_id)
    personas = get_personas_by_ids(doc.get("persona_ids", []))
    transcript = []
    for index, beat in enumerate(doc.get("transcript", [])):
        public = {k: beat.get(k) for k in PUBLIC_BEAT_FIELDS}
        public["audio_url"] = f"/api/share/{share_id}/audio/{index}" if beat.get("audio_url") else None
        transcript.append(public)
    return {
        "share_id": share_id,
        "mode": doc.get("mode", "roast"),
        "battle_style": doc.get("battle_style", "classic"),
        "subject_name": doc.get("subject_name"),
        "created_at": doc.get("created_at"),
        "battle": doc.get("battle"),
        "heat": doc.get("heat", "hot"),
        "images": [f"/api/share/{share_id}/images/{i}.jpg" for i in range(doc.get("image_count", 0))],
        "personas": [{k: p.get(k) for k in PUBLIC_PERSONA_FIELDS} for p in personas],
        "transcript": transcript,
    }


@router.get("/{share_id}/audio/{index}")
async def shared_audio(share_id: str, index: int):
    doc = await _shared_doc(share_id)
    beats = doc.get("transcript", [])
    if index < 0 or index >= len(beats):
        raise HTTPException(status_code=404, detail="Not found")
    url = beats[index].get("audio_url") or ""
    if not url.startswith("/api/audio/"):
        raise HTTPException(status_code=404, detail="Not found")
    filename = url.removeprefix("/api/audio/")
    if not filename or Path(filename).name != filename:
        raise HTTPException(status_code=404, detail="Not found")
    data = await load_voice_audio(filename)
    if data is None:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=data, media_type="audio/mpeg", headers={"Cache-Control": "private, no-store"})


@router.get("/{share_id}/images/{index}.jpg")
async def shared_image(share_id: str, index: int):
    doc = await _shared_doc(share_id)
    if index < 0 or index >= doc.get("image_count", 0):
        raise HTTPException(status_code=404, detail="Not found")
    data = await get_blob(f"subjects/{doc['id']}_{index}.jpg")
    if data is None and index == 0:
        data = await get_blob(f"subjects/{doc['id']}.jpg")
    if data is None:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})
