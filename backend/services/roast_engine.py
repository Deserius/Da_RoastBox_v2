"""Shared roast pipeline helpers: image prep, entitlement checks, credit ledger, persistence."""
import asyncio
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import uuid4

from fastapi import Depends, HTTPException, UploadFile
from PIL import Image, ImageOps
from pymongo.errors import DuplicateKeyError

from crypto_utils import decrypt
from auth_deps import get_current_user, active_plan_tier
from db import users_collection, roasts_collection, credits_collection
from models import User, RoastRecord, CreditTransaction
from services.storage import put_blob

log = logging.getLogger(__name__)
MAX_IMAGE_PIXELS = 1280
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_PIXELS = 25_000_000
IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _resize(raw: bytes) -> bytes:
    """Decode and normalize a bounded image, stripping metadata before storage."""
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in IMAGE_FORMATS:
                raise HTTPException(status_code=400, detail="Use JPEG, PNG, or WebP images.")
            if source.width * source.height > MAX_SOURCE_PIXELS:
                raise HTTPException(status_code=413, detail="Image dimensions are too large (maximum 25 megapixels).")
            img = ImageOps.exif_transpose(source).convert("RGB")
            img.thumbnail((MAX_IMAGE_PIXELS, MAX_IMAGE_PIXELS))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=85)
            return out.getvalue()
    except HTTPException:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as e:
        raise HTTPException(status_code=400, detail="Invalid or unreadable image. Use JPEG, PNG, or WebP.") from e


async def read_images(images: List[UploadFile]) -> Tuple[List[bytes], List[str]]:
    if len(images) > MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"Upload at most {MAX_IMAGES} images.")
    data = []
    for upload in images:
        raw = await upload.read(MAX_IMAGE_BYTES + 1)
        if len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Each image must be 8 MB or smaller.")
        data.append(raw)
    # Decoding and resizing is CPU bound; run the uploads' work concurrently.
    resized = await asyncio.gather(*[asyncio.to_thread(_resize, raw) for raw in data])
    return list(resized), ["image/jpeg"] * len(resized)


async def locked_generation_user(current_user: User = Depends(get_current_user)):
    """Serialize expensive jobs for an account across API processes.

    The lease expires after ten minutes if a process dies. Release only our own
    lease so a very slow, expired job cannot remove a later job's lease.
    """
    lease_id = uuid4().hex
    now = datetime.now(timezone.utc)
    result = await users_collection.update_one(
        {"id": current_user.id, "$or": [
            {"generation_lease": {"$exists": False}}, {"generation_lease": None},
            {"generation_lease.expires_at": {"$lte": now.isoformat()}},
        ]},
        {"$set": {"generation_lease": {"id": lease_id, "expires_at": (now + timedelta(minutes=10)).isoformat()}}},
    )
    if not result.modified_count:
        raise HTTPException(status_code=409, detail="Another job is already running for this account. Please wait for it to finish.")
    try:
        # Refresh after acquiring the lease so credit and daily-free checks cannot
        # use a snapshot taken before another job finished.
        doc = await users_collection.find_one({"id": current_user.id})
        if not doc:
            raise HTTPException(status_code=401, detail="User not found")
        fresh = User(**doc)
        fresh.plan_tier = active_plan_tier(fresh.plan_tier, fresh.plan_until)
        yield fresh
    finally:
        await users_collection.update_one(
            {"id": current_user.id, "generation_lease.id": lease_id}, {"$unset": {"generation_lease": ""}},
        )


def user_byok(user: User) -> Tuple[Optional[str], Optional[str]]:
    openai_key = decrypt(user.openai_key_encrypted) if user.has_byok_openai else None
    eleven_key = decrypt(user.elevenlabs_key_encrypted) if user.has_byok_elevenlabs else None
    return openai_key, eleven_key


def has_premium_voices(user: User) -> bool:
    return user.premium_voices_unlocked or user.plan_tier in ("plus", "vip")


def check_persona_access(user: User, personas: List[dict]) -> bool:
    """Raises 402 if a locked premium persona is selected. Returns whether any premium persona is used."""
    uses_premium = any(p.get("tier") == "premium" for p in personas)
    if uses_premium and not (user.premium_personas_unlocked or user.lifetime_founder or user.plan_tier == "vip"):
        raise HTTPException(status_code=402, detail="Premium personas locked. Unlock the Premium Personas Bundle or purchase a RoastBox VIP pass.")
    return uses_premium


def check_heat_access(user: User, heat: str) -> None:
    if heat == "inferno" and not (user.nsfw_edgier_unlocked or user.lifetime_founder):
        raise HTTPException(status_code=402, detail="Inferno heat is part of Brutality+ Mode. Unlock it on the Credits page.")


def subject_image_urls(roast_id: str, count: int) -> List[str]:
    return [f"/api/media/subject/{roast_id}/{i}.jpg" for i in range(count)]


def friendly_ai_error(e: Exception) -> HTTPException:
    low = str(e).lower()
    if "script did not pass local checks" in low:
        return HTTPException(status_code=502, detail=(
            "The writer returned an incomplete or out-of-bounds script. No RoastBox credits were charged. "
            "Your AI provider may bill its request; try refining the details or boundaries."))
    if "free-only mode to be disabled" in low or "free-only writer requires" in low:
        return HTTPException(status_code=503, detail=(
            "OpenRouter writer is misconfigured: the creative profile uses paid models while free-only mode is on. "
            "Set ROAST_FREE_WRITER_ONLY=false to allow paid models, or ROAST_WRITER_PROFILE=free to stay on :free models."))
    if "no writer is configured" in low or "openrouter writer is selected but not configured" in low:
        return HTTPException(status_code=503, detail=(
            "No roast writer is configured. Add OPENROUTER_API_KEY for the OpenRouter writer, or set "
            "ROAST_WRITER_PROVIDER=existing to use the configured OpenAI/Emergent provider."))
    if "no ai provider key configured" in low:
        return HTTPException(status_code=503, detail="No AI provider key configured. Add an OpenAI key in Settings or configure EMERGENT_LLM_KEY / OPENAI_API_KEY on the server.")
    if "cloudflare" in low or "403" in low or "blocked" in low:
        return HTTPException(status_code=502, detail="Upstream filter blocked this roast. Try a different photo or context.")
    if "refused" in low or "policy" in low:
        return HTTPException(status_code=502, detail="AI refused this combination. Try a different subject or rephrase.")
    return HTTPException(status_code=502, detail="Roast generation failed at the AI provider. Please try again or check your configured key.")


# Pending/aborted records are never shown or shared until their debit marker
# has been reconciled. Old records have no billing_state and remain visible.
VISIBLE_BILLING = {"$nin": ["pending", "aborted"]}


async def _generation_ledger(record: dict):
    """Write the deterministic spend/free entry at most once, even after a crash."""
    entry_id = f"generation:{record['id']}"
    free = bool(record.get("was_free_roast"))
    entry = CreditTransaction(id=entry_id, user_id=record["user_id"],
                              amount=0 if free else -int(record.get("credits_spent") or 0),
                              type="free_roast" if free else "spend",
                              description=record.get("billing_description") or "Roast generation").model_dump()
    entry["_id"] = entry_id
    try:
        await credits_collection.insert_one(entry)
    except DuplicateKeyError:
        pass


async def _apply_generation_debit(record: dict):
    """Debit credits/free allowance and record the operation in one user write."""
    record_id, user_id = record["id"], record["user_id"]
    free = bool(record.get("was_free_roast"))
    condition = {"id": user_id, "generation_charge_ids": {"$ne": record_id}}
    update = {"$addToSet": {"generation_charge_ids": record_id}}
    if free:
        day = record["billing_free_date"]
        condition["last_free_roast_date"] = {"$ne": day}
        update["$set"] = {"last_free_roast_date": day}
    else:
        cost = int(record.get("credits_spent") or 0)
        condition["credits"] = {"$gte": cost}
        update["$inc"] = {"credits": -cost}
    result = await users_collection.update_one(condition, update)
    if not result.modified_count:
        user = await users_collection.find_one({"id": user_id}, {"generation_charge_ids": 1})
        if not user or record_id not in user.get("generation_charge_ids", []):
            if free:
                raise HTTPException(status_code=409, detail="Today's free roast was already used. Refresh and try again.")
            raise HTTPException(status_code=402, detail="Insufficient credits at time of charge")


async def _reconcile_generation(record: dict) -> bool:
    """Publish a staged result if charged, otherwise hide it without a debit."""
    user = await users_collection.find_one({"id": record["user_id"]}, {"generation_charge_ids": 1})
    if not user:
        log.error("Cannot reconcile generation %s: account is missing", record["id"])
        return False
    if record["id"] in user.get("generation_charge_ids", []):
        await _generation_ledger(record)
        result = await roasts_collection.update_one({"id": record["id"], "user_id": record["user_id"],
                                                     "billing_state": {"$in": ["pending", "aborted"]}},
                                                    {"$set": {"billing_state": "committed"}})
        if not result.matched_count and not await roasts_collection.find_one(
                {"id": record["id"], "user_id": record["user_id"], "billing_state": "committed"}, {"_id": 1}):
            raise RuntimeError("Charged generation record is missing; manual reconciliation required")
        return True
    await roasts_collection.update_one({"id": record["id"], "user_id": record["user_id"], "billing_state": "pending"},
                                       {"$set": {"billing_state": "aborted"}})
    return False


async def recover_interrupted_generations(older_than: Optional[str] = None):
    """Recover staged results after a single-worker restart or a stale task.

    Marked charges publish their already-generated show and restore the ledger;
    uncharged records stay hidden. This does not deduplicate a new request that
    the user deliberately submits after a lost HTTP response.
    """
    query = {"billing_version": 2, "billing_state": {"$in": ["pending", "aborted"]}}
    if older_than:
        query["billing_staged_at"] = {"$lte": older_than}
    async for record in roasts_collection.find(query, {"_id": 0}):
        await _reconcile_generation(record)


async def commit_record(user: User, record: RoastRecord, subject_images: Optional[List[bytes]], description: str) -> int:
    """Persist a complete result, then commit an idempotent debit and ledger.

    The debit and its marker are atomic in the user document. A crash after that
    write is reconciled by publishing the saved show, not by charging twice.
    """
    for i, img in enumerate(subject_images or []):
        try:
            await put_blob(f"subjects/{record.id}_{i}.jpg", img, "image/jpeg")
        except Exception as exc:
            log.warning("Subject image storage failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not save the subject photo. No credits were charged; please retry.") from exc
    staged = record.model_dump()
    staged.update({"billing_version": 2, "billing_state": "pending", "billing_staged_at": datetime.now(timezone.utc).isoformat(),
                   "billing_description": description, "billing_free_date": today_utc() if record.was_free_roast else None})
    await roasts_collection.insert_one(dict(staged))
    try:
        await _apply_generation_debit(staged)
        if not await _reconcile_generation(staged):
            raise RuntimeError("Could not reconcile the generation charge")
    except Exception as original:
        # If the balance write succeeded and the following ledger write failed,
        # a retry can safely publish the saved record instead of charging twice.
        try:
            recovered = await _reconcile_generation(staged)
        except Exception:
            log.exception("Generation settlement is pending; recovery will retry")
            raise original
        if not recovered:
            raise
    current = await users_collection.find_one({"id": user.id}, {"credits": 1})
    return (current or {}).get("credits", 0)
