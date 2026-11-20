"""Da RoastBox FastAPI backend — app factory. See /app/docs/ARCHITECTURE.md."""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, APIRouter, Depends, HTTPException
from fastapi.responses import Response
from typing import Optional
from starlette.middleware.cors import CORSMiddleware

from config import APP_VERSION, CORS_ORIGINS
from runtime_security import enforce_runtime, RequestSecurityMiddleware

RUNTIME_SECURITY = enforce_runtime(os.environ)
from db import ensure_indexes, roasts_collection, voice_previews_collection, voice_preview_samples_collection
from auth_deps import get_optional_user
from models import User
from services.voice_orchestrator import prune_audio_cache
from services.roast_engine import VISIBLE_BILLING, recover_interrupted_generations
from services.storage import init_storage
from services.audio_mastering import load_voice_audio
from routes.reels import recover_interrupted_reels
from routes import auth, email_auth, personas, roast, battle, share, reels, payments, voice_settings, download, diagnostics, session_tunnel

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

app = FastAPI(title="Da RoastBox API", version=APP_VERSION,
              docs_url=None if RUNTIME_SECURITY.release_mode else "/docs",
              redoc_url=None if RUNTIME_SECURITY.release_mode else "/redoc",
              openapi_url=None if RUNTIME_SECURITY.release_mode else "/openapi.json")
api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"message": "Da RoastBox API live", "version": APP_VERSION}


@api_router.get("/audio/{filename}")
async def serve_audio(filename: str, current_user: Optional[User] = Depends(get_optional_user)):
    if Path(filename).name != filename:
        raise HTTPException(status_code=404, detail="Not found")
    # Fixed, catalog-wide voice previews contain no customer content. All other
    # audio must belong to the signed-in account; public shares use their own
    # revocable share-scoped audio endpoint instead.
    preview = (await voice_previews_collection.find_one({"filename": filename}, {"_id": 1}) or
               await voice_preview_samples_collection.find_one({"filename": filename}, {"_id": 1}))
    if not preview:
        owned = current_user and await roasts_collection.find_one(
            {"user_id": current_user.id, "transcript.audio_url": f"/api/audio/{filename}",
             "billing_state": VISIBLE_BILLING}, {"_id": 1},
        )
        if not owned:
            raise HTTPException(status_code=404, detail="Not found")
    data = await load_voice_audio(filename)
    if data is None:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=data, media_type="audio/mpeg", headers={"Cache-Control": "private, no-store"})


for module in (diagnostics, auth, email_auth, personas, roast, battle, share, reels, payments, voice_settings, download, session_tunnel):
    api_router.include_router(module.router)

app.include_router(api_router)

# Development keeps using the separate CRA proxy. A production container can
# opt in to a same-origin, built frontend without changing any API routes.
frontend_build = os.environ.get("FRONTEND_BUILD_DIR", "").strip()
if frontend_build:
    from frontend_static import SPAStaticFiles
    build_dir = Path(frontend_build).expanduser().resolve()
    if not (build_dir / "index.html").is_file():
        raise RuntimeError("FRONTEND_BUILD_DIR does not contain a built index.html")
    app.mount("/", SPAStaticFiles(directory=build_dir, html=True), name="frontend")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

if RUNTIME_SECURITY.environment == "beta":
    from beta_access import BetaAccessMiddleware
    from config import APP_BASE_URL
    app.add_middleware(BetaAccessMiddleware,
                       password_hash=os.environ["BETA_ACCESS_PASSWORD_HASH"],
                       signing_key=os.environ["BETA_ACCESS_SIGNING_KEY"],
                       origin=APP_BASE_URL)
if RUNTIME_SECURITY.allowed_hosts:
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(RUNTIME_SECURITY.allowed_hosts))
app.add_middleware(RequestSecurityMiddleware, release_mode=RUNTIME_SECURITY.release_mode)


_generation_recovery_task = None
_payment_recovery_task = None


async def _generation_recovery_loop():
    while True:
        await asyncio.sleep(60)
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        try:
            await recover_interrupted_generations(older_than=cutoff)
            await recover_interrupted_reels()
        except Exception:
            logging.getLogger(__name__).exception("Generation recovery failed; it will be retried")


async def _payment_recovery_loop():
    while True:
        await asyncio.sleep(30)
        try:
            await payments.reconcile_pending_test_payments()
        except Exception as exc:
            logging.getLogger(__name__).warning("TEST payment reconciliation will retry (%s)", type(exc).__name__)


@app.on_event("startup")
async def _startup():
    global _generation_recovery_task, _payment_recovery_task
    await ensure_indexes()
    storage_ready = await init_storage()
    if RUNTIME_SECURITY.release_mode and not storage_ready:
        raise RuntimeError("Durable media storage is unavailable; release startup refused")
    await recover_interrupted_reels()
    await recover_interrupted_generations()
    _generation_recovery_task = asyncio.create_task(_generation_recovery_loop())
    _payment_recovery_task = asyncio.create_task(_payment_recovery_loop())
    logging.getLogger(__name__).info("Pruned %d stale audio files", prune_audio_cache())


@app.on_event("shutdown")
async def _shutdown():
    if _payment_recovery_task:
        _payment_recovery_task.cancel()
        try:
            await _payment_recovery_task
        except asyncio.CancelledError:
            pass
    if _generation_recovery_task:
        _generation_recovery_task.cancel()
        try:
            await _generation_recovery_task
        except asyncio.CancelledError:
            pass
