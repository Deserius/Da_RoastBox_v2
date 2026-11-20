"""HD Social Reel export: queue a vertical MP4 render for a roast/battle, poll status, download."""
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import Response
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from auth_deps import get_current_user
from config import PREVIEW_UNLIMITED_CREDITS
from db import roasts_collection, reels_collection, users_collection, credits_collection
from models import User, CreditTransaction
from routes.personas import get_personas_by_ids
from services import roast_engine as eng
from services.pricing import ROAST_COSTS
from services.highlight_reel import REEL_LENGTHS, REEL_STYLE_VERSION, render_reel
from services.storage import get_blob, put_blob
from services.audio_mastering import load_voice_audio

log = logging.getLogger(__name__)
router = APIRouter(tags=["reels"])
# A full-HD encoder is memory intensive; serialize renders within one API worker.
_render_slots = asyncio.Semaphore(1)
_tasks: set = set()  # strong refs so background renders aren't GC'd


def _now():
    return datetime.now(timezone.utc).isoformat()


def reel_cost(user: User, roast: dict) -> int:
    if (user.is_preview and PREVIEW_UNLIMITED_CREDITS) or roast.get("hd_export") or user.lifetime_founder or user.plan_tier == "vip":
        return 0
    return ROAST_COSTS["hd_export"]


def _public(doc: dict) -> dict:
    out = {k: doc.get(k) for k in ("id", "roast_id", "status", "error", "created_at", "updated_at", "size_bytes", "length", "progress", "phase")}
    # Charging is an internal pre-queue state, not a new client-facing status.
    if out["status"] == "charging":
        out["status"] = "queued"
    out["video_url"] = f"/api/reels/{doc['id']}/video.mp4" if doc.get("status") == "done" else None
    out["download_url"] = f"/api/reels/{doc['id']}/video.mp4?download=true" if doc.get("status") == "done" else None
    out["filename"] = f"da-roastbox-{doc.get('length') or 60}s-{doc['id'][:8]}.mp4"
    return out


async def _reel_ledger(user_id: str, reel_id: str, amount: int, kind: str):
    """Retryable audit entry; Mongo's _id enforces uniqueness even on retries."""
    entry_id = f"reel-{kind}:{reel_id}"
    entry = CreditTransaction(id=entry_id, user_id=user_id, amount=amount, type=kind,
                              description="HD Social Reel export" if kind == "spend" else "HD Social Reel refund").model_dump()
    entry["_id"] = entry_id
    try:
        await credits_collection.insert_one(entry)
    except DuplicateKeyError:
        pass


async def _charge_reel(user_id: str, reel_id: str, cost: int):
    """Atomically debit and mark the operation in the same user document."""
    result = await users_collection.update_one(
        {"id": user_id, "credits": {"$gte": cost}, "charged_reel_ids": {"$ne": reel_id}},
        {"$inc": {"credits": -cost}, "$addToSet": {"charged_reel_ids": reel_id}},
    )
    if not result.modified_count:
        user = await users_collection.find_one({"id": user_id}, {"charged_reel_ids": 1})
        if not user or reel_id not in user.get("charged_reel_ids", []):
            raise HTTPException(status_code=402, detail="Insufficient credits at time of charge")
    await _reel_ledger(user_id, reel_id, -cost, "spend")


async def _refund_pending(reel_id: str):
    """Apply a failed job's refund once, and resume after an interrupted write."""
    doc = await reels_collection.find_one({"id": reel_id, "status": "failed", "refund_pending": True})
    if not doc:
        return
    cost = int(doc.get("credits_spent") or 0)
    refund_confirmed = not cost
    if cost:
        condition = {"id": doc["user_id"], "refunded_reel_ids": {"$ne": reel_id}}
        # v2 creates the job before charging; an interrupted pre-charge job
        # must never receive credits it did not spend. Older queued jobs were
        # always charged before insertion, so retain their legacy recovery.
        if doc.get("billing_version") == 2:
            condition["charged_reel_ids"] = reel_id
        await users_collection.update_one(condition,
            {"$inc": {"credits": cost}, "$addToSet": {"refunded_reel_ids": reel_id}})
        user = await users_collection.find_one({"id": doc["user_id"]}, {"charged_reel_ids": 1, "refunded_reel_ids": 1})
        if not user:
            log.error("Cannot refund reel %s: account is missing; manual reconciliation required", reel_id)
            return  # Leave refund_pending set without blocking application startup.
        if reel_id in user.get("refunded_reel_ids", []):
            # A crash after either balance update leaves the pending flag set;
            # deterministic entries are safe to recreate on the next startup.
            if doc.get("billing_version") == 2 and reel_id in user.get("charged_reel_ids", []):
                await _reel_ledger(doc["user_id"], reel_id, -cost, "spend")
            await _reel_ledger(doc["user_id"], reel_id, cost, "refund")
            refund_confirmed = True
    await reels_collection.update_one({"id": reel_id, "status": "failed", "refund_pending": True},
                                      {"$set": {"refund_pending": False, "refund_confirmed": refund_confirmed,
                                                "updated_at": _now()}})


async def _fail_reel(reel_id: str, error: str):
    """Durably mark failure before refund, without overwriting a completed job."""
    doc = await reels_collection.find_one_and_update(
        {"id": reel_id, "status": {"$in": ["charging", "queued", "rendering"]}},
        {"$set": {"status": "failed", "error": error[:300], "refund_pending": True, "updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        doc = await reels_collection.find_one({"id": reel_id, "status": "failed"})
        if not doc:
            return
        # If a second worker interrupted a charging operation, the debit may
        # have happened just after its first refund check; retry safely.
        await reels_collection.update_one({"id": reel_id, "status": "failed"}, {"$set": {"refund_pending": True}})
    await _refund_pending(reel_id)


async def load_subject_photos(roast_id: str, count: int) -> list:
    photos = [p for p in await asyncio.gather(*[get_blob(f"subjects/{roast_id}_{i}.jpg") for i in range(count)]) if p]
    if not photos:  # v7 records stored a single photo
        legacy = await get_blob(f"subjects/{roast_id}.jpg")
        photos = [legacy] if legacy else []
    return photos


async def _render_job(reel_id: str, roast: dict, refund: int = 0, user_id: str = "", length: int = 60):
    async with _render_slots:
        claimed = await reels_collection.update_one({"id": reel_id, "status": "queued"},
                                                     {"$set": {"status": "rendering", "phase": "Loading voices and photos", "progress": 12, "updated_at": _now()}})
        if not claimed.modified_count:
            return
        try:
            beats = roast.get("transcript", [])
            voices = await asyncio.gather(*[load_voice_audio(b["audio_url"].rsplit("/", 1)[-1]) if b.get("audio_url") else asyncio.sleep(0)
                                            for b in beats])
            # A missing stored voice must not silently create an unvoiced video.
            # Missing entrance clips are harmless: the reel has its own entrance.
            available = [(beat, voice) for beat, voice in zip(beats, voices) if voice]
            if not available:
                raise ValueError("The original voice files could not be loaded. Restore this show's audio files and retry.")
            beats, voices = map(list, zip(*available))
            photos = await load_subject_photos(roast["id"], roast.get("image_count", 0))
            personas = {p["id"]: p for p in get_personas_by_ids(roast.get("persona_ids", []))}
            await reels_collection.update_one({"id": reel_id, "status": "rendering"}, {"$set": {
                "phase": "Rendering captions, voices and crowd", "progress": 35, "updated_at": _now()}})
            video = await asyncio.to_thread(render_reel, beats=beats, voice_files=list(voices), personas=personas,
                                            photos=photos, subject_name=roast.get("subject_name"),
                                            battle=roast.get("battle"), max_seconds=length, battle_style=roast.get("battle_style", "classic"))
            if len(video) < 1024 or video[4:8] != b"ftyp":
                raise RuntimeError("Encoder did not return a valid MP4")
            await reels_collection.update_one({"id": reel_id, "status": "rendering"}, {"$set": {
                "phase": "Saving your MP4", "progress": 95, "updated_at": _now()}})
            await put_blob(f"reels/{reel_id}.mp4", video, "video/mp4")
            await reels_collection.update_one({"id": reel_id, "status": "rendering"}, {"$set": {
                "status": "done", "phase": "Ready to watch and download", "progress": 100,
                "error": None, "size_bytes": len(video), "updated_at": _now()}})
        except Exception as e:
            log.exception("Reel render failed")
            message = str(e) if isinstance(e, ValueError) else "Video rendering failed. Please retry; any export charge is refunded."
            await _fail_reel(reel_id, message)


@router.post("/roast/{roast_id}/reel")
async def create_reel(roast_id: str, length: int = Body(60, embed=True), regenerate: bool = Body(False, embed=True),
                      current_user: User = Depends(eng.locked_generation_user)):
    if length not in REEL_LENGTHS:
        raise HTTPException(status_code=400, detail="Reel length must be 30 or 60 seconds")
    roast = await roasts_collection.find_one({"id": roast_id, "user_id": current_user.id,
                                               "billing_state": eng.VISIBLE_BILLING}, {"_id": 0})
    if not roast:
        raise HTTPException(status_code=404, detail="Roast not found")
    existing = await reels_collection.find_one({"roast_id": roast_id, "length": length, "user_id": current_user.id,
                                                "style_version": REEL_STYLE_VERSION,
                                                "status": {"$in": ["charging", "queued", "rendering", "done"]}},
                                               {"_id": 0}, sort=[("created_at", -1)])
    if existing and existing.get("status") != "done":
        return _public(existing)  # Double-clicks/reconnections reuse the same queued job.
    if existing and not regenerate:
        data = await get_blob(f"reels/{existing['id']}.mp4")
        if data and len(data) > 1024 and data[4:8] == b"ftyp":
            return _public(existing)
        # A DB record alone is not a playable reel (e.g. after moving machines).
        # Keep the ownership marker so rebuilding never charges the export again.
        await reels_collection.update_one({"id": existing["id"], "status": "done"}, {"$set": {
            "status": "unavailable", "error": "Saved MP4 is missing. Rebuild this reel without another export charge.",
            "updated_at": _now()}})
    # A previously completed export of this length already belongs to the user.
    # Upgrade its styling without charging a second time; old downloads still work.
    previous = await reels_collection.find_one({"roast_id": roast_id, "length": length, "user_id": current_user.id,
                                                "status": {"$in": ["done", "unavailable"]}}, {"_id": 0, "id": 1})
    cost = 0 if previous else reel_cost(current_user, roast)
    if cost and current_user.credits < cost:
        raise HTTPException(status_code=402, detail=f"HD Reel export costs {cost} credits. You have {current_user.credits}.")
    # Persist first, then atomically mark the debit in the user document. A
    # restart can now distinguish an uncharged job from a charged one.
    doc = {"id": str(uuid4()), "roast_id": roast_id, "user_id": current_user.id, "status": "charging", "length": length,
           "style_version": REEL_STYLE_VERSION, "credits_spent": cost, "billing_version": 2,
           "phase": "Waiting for the video renderer", "progress": 0,
           "created_at": _now(), "updated_at": _now()}
    await reels_collection.insert_one(dict(doc))
    try:
        if cost:
            await _charge_reel(current_user.id, doc["id"], cost)
        queued = await reels_collection.update_one({"id": doc["id"], "status": "charging"},
                                                    {"$set": {"status": "queued", "updated_at": _now()}})
        if not queued.modified_count:
            raise HTTPException(status_code=503, detail="Reel was interrupted. Please try again.")
    except Exception:
        try:
            await _fail_reel(doc["id"], "Could not queue this reel — please retry")
        except Exception:
            # Keep the charging/failed record for startup recovery; never hide
            # the original exception or silently drop the debit marker.
            log.exception("Could not finish reel refund; startup will retry")
        raise
    doc["status"] = "queued"
    task = asyncio.create_task(_render_job(doc["id"], roast, cost, current_user.id, length))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return _public(doc)


@router.get("/roast/{roast_id}/reels")
async def roast_reels(roast_id: str, current_user: User = Depends(get_current_user)):
    roast = await roasts_collection.find_one({"id": roast_id, "user_id": current_user.id,
                                               "billing_state": eng.VISIBLE_BILLING}, {"id": 1})
    if not roast:
        raise HTTPException(status_code=404, detail="Roast not found")
    docs = await reels_collection.find({"roast_id": roast_id, "user_id": current_user.id}, {"_id": 0}).sort("created_at", -1).limit(30).to_list(30)
    return {"reels": [_public(doc) for doc in docs]}


@router.get("/reels/{reel_id}")
async def reel_status(reel_id: str, current_user: User = Depends(get_current_user)):
    doc = await reels_collection.find_one({"id": reel_id, "user_id": current_user.id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Reel not found")
    return _public(doc)


def _video_response(data: bytes, filename: str, *, download: bool = False, byte_range: Optional[str] = None,
                    head: bool = False) -> Response:
    """Standards-compliant inline playback, byte seeking and attachment downloads."""
    size = len(data)
    headers = {"Cache-Control": "private, no-store", "Accept-Ranges": "bytes", "X-Content-Type-Options": "nosniff",
               "Content-Disposition": f'{"attachment" if download else "inline"}; filename="{filename}"'}
    start, end, status = 0, size - 1, 200
    if byte_range and not download:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", byte_range.strip())
        if not match or not any(match.groups()):
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
        left, right = match.groups()
        if left:
            start = int(left)
            end = min(size - 1, int(right)) if right else size - 1
        elif int(right) > 0:
            start = max(0, size - int(right))
        else:
            start = size
        if start >= size or start > end:
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(end - start + 1)
    return Response(content=b"" if head else data[start:end + 1], status_code=status, media_type="video/mp4", headers=headers)


@router.api_route("/reels/{reel_id}/video.mp4", methods=["GET", "HEAD"])
async def reel_video(reel_id: str, request: Request, download: bool = False,
                     current_user: User = Depends(get_current_user)):
    doc = await reels_collection.find_one({"id": reel_id, "user_id": current_user.id, "status": "done"}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Reel not found or not ready")
    data = await get_blob(f"reels/{reel_id}.mp4")
    if not data:
        raise HTTPException(status_code=404, detail="Saved MP4 is missing. Rebuild this reel without another export charge.")
    return _video_response(data, _public(doc)["filename"], download=download,
                           byte_range=request.headers.get("range"), head=request.method == "HEAD")


async def recover_interrupted_reels():
    """On a single-worker restart, fail interrupted jobs and safely retry refunds.

    This is not a distributed queue: overlapping API workers can still
    interrupt one another, so production remains limited to one worker.
    """
    query = {"$or": [{"status": {"$in": ["charging", "queued", "rendering"]}},
                      {"status": "failed", "refund_pending": True},
                      {"status": "failed", "billing_version": 2, "credits_spent": {"$gt": 0},
                       "refund_confirmed": {"$ne": True}}]}
    async for doc in reels_collection.find(query, {"_id": 0}):
        if doc.get("status") == "failed" and doc.get("refund_pending"):
            await _refund_pending(doc["id"])
        else:
            await _fail_reel(doc["id"], "Interrupted by server restart — please retry")


@router.get("/media/subject/{roast_id}/{index}.jpg")
async def subject_photo(roast_id: str, index: int, current_user: User = Depends(get_current_user)):
    """Private owner photo; shared photos use the revocable share endpoint."""
    doc = await roasts_collection.find_one({"id": roast_id, "user_id": current_user.id,
                                            "billing_state": eng.VISIBLE_BILLING}, {"image_count": 1})
    if not doc or index < 0 or index >= doc.get("image_count", 0):
        raise HTTPException(status_code=404, detail="Not found")
    data = await get_blob(f"subjects/{roast_id}_{index}.jpg")
    if data is None and index == 0:
        data = await get_blob(f"subjects/{roast_id}.jpg")
    if data is None:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})
