"""Isolated, offline integration checks for this workspace export.

Requires a local MongoDB at MONGO_URL (defaults to localhost:27017). This uses a
random temporary database and temporary media directory, mocks only paid AI and
video rendering, and drops its database afterward. It never makes paid calls.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

test_db = f"roastbox_offline_test_{uuid.uuid4().hex[:12]}"
os.environ.update({
    "MONGO_URL": os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017"),
    "DB_NAME": test_db,
    "JWT_SECRET": "offline-test-secret-not-for-production",
    "EMERGENT_LLM_KEY": "offline-hosted-key-must-not-be-used",
    "OPENAI_API_KEY": "",
    "ELEVENLABS_API_KEY": "",
    "STRIPE_API_KEY": "sk_test_not_a_real_key",
    "STRIPE_WEBHOOK_SECRET": "whsec_offline_test_secret",
    "STRIPE_TEST_ONLY": "true",
    "STORAGE_BACKEND": "local",
    "ENABLE_PREVIEW_LOGIN": "true",
    "ALLOW_PREVIEW_HOSTED_AI": "false",
    "ALLOW_DEV_LOGIN": "false",
    "ROAST_WRITER_PROVIDER": "existing",
    "OPENROUTER_API_KEY": "",
    "PREVIEW_UNLIMITED_CREDITS": "false",  # Exercise normal billing in this isolated test DB.
    "APP_BASE_URL": "",
})

from fastapi.testclient import TestClient
from PIL import Image
from pymongo import MongoClient
import services.storage as storage
import services.voice_orchestrator as voice_orchestrator
import services.openai_service as openai_service
import services.roast_writer as roast_writer
import services.preview_budget as preview_budget
import routes.personas as personas_routes
import routes.auth as auth_routes
import routes.roast as roast_routes
import routes.battle as battle_routes
import routes.reels as reel_routes
import routes.payments as payment_routes
from services.roast_writer import write_script as real_writer
from services.voice_orchestrator import synthesize_show as real_synth, voice_beats_progressive as real_progressive
from server import app


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}", flush=True)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def post_login(client):
    r = client.post("/api/auth/preview-login")
    assert r.status_code == 200, r.text
    return r.json()


async def fake_writer(_prompt, personas, *_args, **_kwargs):
    return [{"persona_id": p["id"], "type": "punchline", "text": "Offline integration test line.",
             "emotion": "cocky", "reaction": "laugh", "laugh_after": "big", "image_index": 0,
             "pause_before_ms": 0, "pause_after_ms": 0} for p in personas]


async def fake_synth(beats, *_args, **_kwargs):
    sample = (ROOT / "assets/sfx/chuckle_1.mp3").read_bytes()
    lines = []
    for beat in beats:
        filename = f"offline-{uuid.uuid4().hex}.mp3"
        await storage.save_audio(filename, sample)
        lines.append({**beat, "audio_url": f"/api/audio/{filename}", "provider": "offline-mock"})
    return lines, ["offline-mock"]


async def fake_progressive(started, beats, *args, **kwargs):
    # Keep the staged/progressive roast pipeline offline as well as legacy battle synthesis.
    for task in started.values():
        task.cancel()
    started.clear()
    return await roast_routes.synthesize_show(beats, *args, **kwargs)


async def fake_battle_progressive(started, beats, *args, **kwargs):
    for task in started.values():
        task.cancel()
    started.clear()
    return await battle_routes.synthesize_show(beats, *args, **kwargs)


async def failed_synth(beats, *_args, **_kwargs):
    return [{**beat, "audio_url": None, "provider": "none"} for beat in beats], []


def fake_reel(**_kwargs):
    # The actual ffmpeg renderer has a separate smoke test; this exercises the async job/storage route.
    return b"\x00\x00\x00\x18ftypmp42offline-integration-video" + bytes(2048)


def main():
    mongo = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
    mongo.admin.command("ping")
    try:
        with tempfile.TemporaryDirectory(prefix="roastbox-offline-") as tmp:
            storage.LOCAL_STORAGE_DIR = Path(tmp) / "objects"
            storage.AUDIO_DIR = Path(tmp) / "cache"
            storage.AUDIO_DIR.mkdir()
            with TestClient(app) as client:
                check(client.get("/api/health").status_code == 200, "API starts against isolated MongoDB")

                # Simulate the Emergent session exchange without contacting Google or the provider.
                original_client = auth_routes.httpx.AsyncClient
                class FakeResponse:
                    status_code = 200
                    payload = {"email": "oauth-test@example.invalid"}
                    def json(self): return self.payload
                class FakeAsyncClient:
                    last_request = None
                    def __init__(self, **_kwargs): pass
                    async def __aenter__(self): return self
                    async def __aexit__(self, *_args): pass
                    async def get(self, *args, **kwargs):
                        FakeAsyncClient.last_request = (args, kwargs)
                        return FakeResponse()
                auth_routes.httpx.AsyncClient = FakeAsyncClient
                try:
                    invalid = client.post("/api/auth/session", json={"session_id": "offline"})
                    check(invalid.status_code == 502 and mongo[test_db].users.find_one({"email": "oauth-test@example.invalid"}) is None,
                          "OAuth rejects incomplete provider sessions before creating a user")
                    FakeResponse.payload = {"email": "oauth-test@example.invalid", "session_token": "offline-oauth-token"}
                    valid = client.post("/api/auth/session", json={"session_id": "offline"})
                    oauth_token = valid.json().get("session_token", "")
                    check(valid.status_code == 200 and oauth_token and oauth_token != "offline-oauth-token" and
                          client.get("/api/auth/me", headers=auth(oauth_token)).status_code == 200 and
                          FakeAsyncClient.last_request[0][0] == auth_routes.EMERGENT_AUTH_URL and
                          FakeAsyncClient.last_request[1]["headers"]["X-Session-ID"] == "offline",
                          "mocked OAuth exchange uses the original provider and creates a separate app session")
                    original_user = valid.json()["user"]["id"]
                    mongo[test_db].users.update_one({"id": original_user}, {"$set": {"credits": 37, "roast_battle_unlocked": True}})
                    FakeResponse.payload = {"email": "oauth-test@example.invalid", "session_token": "provider-token-2", "name": "Updated Name"}
                    repeat = client.post("/api/auth/session", json={"session_id": "offline-2"})
                    second_token = repeat.json().get("session_token", "")
                    profile = client.get("/api/auth/me", headers=auth(second_token)).json()
                    check(repeat.status_code == 200 and second_token != oauth_token and profile["id"] == original_user and
                          profile["credits"] == 37 and profile["roast_battle_unlocked"] and profile["name"] == "Updated Name",
                          "repeat Google login preserves the account, credits and purchases while refreshing profile")
                    mongo[test_db].users.update_one({"id": original_user}, {"$set": {"credits": 5}})

                    FakeResponse.payload = {"email": "unverified@example.invalid", "session_token": "provider-token", "email_verified": False}
                    unverified = client.post("/api/auth/session", json={"session_id": "offline-3"})
                    check(unverified.status_code == 401 and mongo[test_db].users.find_one({"email": "unverified@example.invalid"}) is None,
                          "explicitly unverified provider emails cannot create or link accounts")
                    FakeResponse.status_code = 503
                    unavailable = client.post("/api/auth/session", json={"session_id": "offline-4"})
                    check(unavailable.status_code == 502, "provider outage reports a retryable sign-in failure")
                    FakeResponse.status_code = 200
                    check(client.post("/api/auth/session", json={"session_id": ""}).status_code == 422,
                          "empty provider sessions are rejected before exchange")

                    FakeResponse.payload = {"email": "oauth-test@example.invalid", "session_token": "provider-token-3"}
                    third_token = client.post("/api/auth/session", json={"session_id": "offline-5"}).json()["session_token"]
                    signout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {second_token}", "Cookie": f"session_token={third_token}"})
                    check(signout.status_code == 200 and client.get("/api/auth/me", headers=auth(second_token)).status_code == 401 and
                          client.get("/api/auth/me", headers=auth(third_token)).status_code == 401 and
                          client.get("/api/auth/me", headers=auth(oauth_token)).status_code == 200,
                          "logout revokes both bearer and cookie sessions without revoking other devices")
                    fourth_token = client.post("/api/auth/session", json={"session_id": "offline-6"}).json()["session_token"]
                    mongo[test_db].sessions.update_one({"session_token": fourth_token}, {"$set": {"expires_at": "not-a-date"}})
                    invalid_expiry = client.get("/api/auth/me", headers=auth(fourth_token))
                    mongo[test_db].sessions.update_one({"session_token": fourth_token}, {"$set": {"expires_at": "2000-01-01T00:00:00+00:00"}})
                    expired = client.get("/api/auth/me", headers=auth(fourth_token))
                    check(invalid_expiry.status_code == 401 and expired.status_code == 401,
                          "malformed or expired sessions never authenticate")
                finally:
                    auth_routes.httpx.AsyncClient = original_client

                one, two = post_login(client), post_login(client)
                user_id, token = one["user"]["id"], one["session_token"]
                check(user_id != two["user"]["id"], "preview accounts are isolated")
                check(client.get("/api/auth/me", headers={"X-Roastbox-Session": token, "Authorization": "Bearer proxy-overwritten"}).status_code == 200,
                      "app session header works if a proxy reserves Authorization")
                third = post_login(client)["session_token"]
                client.post("/api/auth/logout", headers={"X-Roastbox-Session": third})
                check(client.get("/api/auth/me", headers={"X-Roastbox-Session": third}).status_code == 401,
                      "logout revokes an app-header session")
                tunnel = lambda tok, method, path: client.post("/api/session/dispatch", data={
                    "token": tok, "method": method, "path": path, "kind": "none"}, headers={"Cookie": "session_token=invalid"})
                tunneled_me = tunnel(token, "GET", "/api/auth/me")
                tunneled_invalid = tunnel("bad-token", "GET", "/api/auth/me")
                tunneled_escape = tunnel(token, "POST", "/api/session/dispatch")
                check(tunneled_me.status_code == 200 and tunneled_me.json()["id"] == user_id and
                      tunneled_invalid.status_code == 401 and tunneled_escape.status_code == 400,
                      "body session transport authenticates without headers or cookies and cannot recurse")
                cookie_headers = {"Cookie": f"session_token={token}", "Origin": "https://untrusted.example"}
                csrf_keys = client.post("/api/voice-settings/keys", headers=cookie_headers, json={"openai_key": "do-not-save"})
                csrf_logout = client.post("/api/auth/logout", headers=cookie_headers)
                check(csrf_keys.status_code == 403 and csrf_logout.status_code == 403 and
                      client.get("/api/auth/me", headers=auth(token)).status_code == 200,
                      "cross-site cookie-only mutations and logout are rejected without revoking the session")
                mongo[test_db].users.update_one({"id": user_id}, {"$set": {"plan_tier": "vip", "plan_until": "2000-01-01T00:00:00+00:00"}})
                expired_tier = client.get("/api/auth/me", headers=auth(token)).json()["plan_tier"]
                mongo[test_db].users.update_one({"id": user_id}, {"$set": {"plan_tier": "vip", "plan_until": "2099-01-01T00:00:00+00:00"}})
                active_tier = client.get("/api/auth/me", headers=auth(token)).json()["plan_tier"]
                mongo[test_db].users.update_one({"id": user_id}, {"$set": {"plan_tier": "free", "plan_until": None}})
                check(expired_tier == "free" and active_tier == "vip", "time-limited plan tier benefits expire correctly")
                check(client.post("/api/auth/dev-login", json={"email": "someone@example.com"}).status_code == 404,
                      "arbitrary-email development login is disabled")
                headers, other = auth(token), auth(two["session_token"])
                personas = client.get("/api/personas", headers=headers).json()["personas"]
                check(len(personas) == 40 and sum(p["is_premium"] for p in personas) == 15,
                      "original 40-persona catalog and entitlements")
                assert client.get("/api/personas/favorites", headers=headers).json()["favorites"] == []
                def favorite(pid):
                    return client.put(f"/api/personas/favorites/{pid}", headers=headers)
                with ThreadPoolExecutor(max_workers=3) as pool:
                    favorite_results = list(pool.map(favorite, ["persona_1", "persona_2", "persona_1"]))
                favorite_list = client.get("/api/personas/favorites", headers=headers).json()["favorites"]
                check(all(r.status_code == 200 for r in favorite_results) and set(favorite_list) == {"persona_1", "persona_2"}
                      and len(favorite_list) == 2 and client.get("/api/personas/favorites", headers=other).json()["favorites"] == []
                      and client.put("/api/personas/favorites/not-a-persona", headers=headers).status_code == 404,
                      "favorites are account-isolated, validated, idempotent and safe under concurrent updates")
                assert client.delete("/api/personas/favorites/persona_1", headers=headers).status_code == 200
                check(client.get("/api/personas/favorites", headers=headers).json()["favorites"] == ["persona_2"] and
                      tunnel(token, "PUT", "/api/personas/favorites/persona_3").status_code == 200 and
                      "persona_3" in tunnel(token, "GET", "/api/personas/favorites").json()["favorites"],
                      "favorites can be removed and work through the stripped-header preview transport")

                fake_key = "sk-offline-not-a-real-key"
                assert client.post("/api/voice-settings/keys", headers=headers, json={"openai_key": fake_key}).status_code == 200
                record = mongo[test_db].users.find_one({"id": user_id})
                check(fake_key not in record["openai_key_encrypted"] and
                      fake_key not in client.get("/api/auth/me", headers=headers).text,
                      "BYOK secrets are encrypted and not returned by the API")
                assert client.delete("/api/voice-settings/keys", headers=headers).status_code == 200

                roast_routes.write_script = fake_writer
                roast_routes.synthesize_show = fake_synth
                roast_routes.voice_beats_progressive = fake_progressive
                battle_routes.write_script = fake_writer
                battle_routes.synthesize_show = failed_synth
                battle_routes.voice_beats_progressive = fake_battle_progressive
                reel_routes.render_reel = fake_reel
                image = io.BytesIO()
                Image.new("RGB", (24, 24), "#777777").save(image, "JPEG")
                invalid_img = client.post("/api/roast/generate", headers=headers,
                    data={"persona_ids": "persona_1"}, files={"images": ("fake.jpg", b"not an image", "image/jpeg")})
                large_img = client.post("/api/roast/generate", headers=headers,
                    data={"persona_ids": "persona_1"}, files={"images": ("large.jpg", b"x" * (8 * 1024 * 1024 + 1), "image/jpeg")})
                many_imgs = client.post("/api/roast/generate", headers=headers, data={"persona_ids": "persona_1"},
                    files=[("images", (f"{i}.jpg", image.getvalue(), "image/jpeg")) for i in range(5)])
                too_long = client.post("/api/roast/generate", headers=headers,
                    data={"persona_ids": "persona_1", "user_context": "x" * 3001}, files={"images": ("face.jpg", image.getvalue(), "image/jpeg")})
                long_boundary = client.post("/api/roast/generate", headers=headers,
                    data={"persona_ids": "persona_1", "off_limits": "x" * 601}, files={"images": ("face.jpg", image.getvalue(), "image/jpeg")})
                unknown = client.post("/api/roast/generate", headers=headers,
                    data={"persona_ids": "persona_1,unknown"}, files={"images": ("face.jpg", image.getvalue(), "image/jpeg")})
                check(invalid_img.status_code == 400 and large_img.status_code == 413 and many_imgs.status_code == 400 and
                      too_long.status_code == 422 and long_boundary.status_code == 422 and unknown.status_code == 400,
                      "invalid, oversized or excessive uploads and unknown personas are rejected before AI calls")
                guarded = client.post("/api/roast/generate", headers=headers,
                    data={"persona_ids": "persona_1"}, files={"images": ("face.jpg", image.getvalue(), "image/jpeg")})
                check(guarded.status_code == 503 and "own OpenAI" in guarded.text,
                      "preview account cannot spend a configured hosted AI key")
                check(client.get("/api/personas/persona_1/voice-preview", headers=headers).status_code == 503,
                      "preview voice cannot spend a configured hosted key")
                old_eleven, old_openai = voice_orchestrator.synthesize_tts_elevenlabs, voice_orchestrator.synthesize_tts_openai
                hosted_fallback_calls = []
                async def broken_eleven(*_args, **_kwargs): raise RuntimeError("offline test failure")
                async def forbidden_hosted(*_args, **_kwargs):
                    hosted_fallback_calls.append(True)
                    return b"unexpected-hosted-audio"
                voice_orchestrator.synthesize_tts_elevenlabs, voice_orchestrator.synthesize_tts_openai = broken_eleven, forbidden_hosted
                try:
                    assert client.post("/api/voice-settings/keys", headers=headers, json={"elevenlabs_key": "offline-eleven-key"}).status_code == 200
                    failed_preview = client.get("/api/personas/persona_2/voice-preview", headers=headers)
                    check(failed_preview.status_code == 503 and not hosted_fallback_calls,
                          "failed BYOK ElevenLabs never falls back to hosted OpenAI in preview")
                finally:
                    voice_orchestrator.synthesize_tts_elevenlabs, voice_orchestrator.synthesize_tts_openai = old_eleven, old_openai
                    assert client.delete("/api/voice-settings/keys", headers=headers).status_code == 200
                check(client.post("/api/payments/checkout", headers=headers,
                                  json={"pack_id": "credits_starter", "origin_url": "http://testserver"}).status_code == 403,
                      "preview account cannot make a real purchase")
                parallel_user = post_login(client)
                parallel_headers = auth(parallel_user["session_token"])
                assert client.post("/api/voice-settings/keys", headers=parallel_headers, json={"openai_key": fake_key}).status_code == 200
                async def slow_writer(*args, **kwargs):
                    await asyncio.sleep(0.35)
                    return await fake_writer(*args, **kwargs)
                roast_routes.write_script = slow_writer
                try:
                    def generate_same_user(_):
                        return client.post("/api/roast/generate", headers=parallel_headers,
                            data={"persona_ids": "persona_1"}, files={"images": ("face.jpg", image.getvalue(), "image/jpeg")})
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        concurrent = list(pool.map(generate_same_user, range(2)))
                    check(sorted(r.status_code for r in concurrent) == [200, 409],
                          "concurrent expensive requests for one account are serialized across workers")
                finally:
                    roast_routes.write_script = fake_writer
                # Explicit hosted preview mode is shared, atomic and capped across
                # disposable accounts. All provider work remains mocked here.
                budget_saved = (preview_budget.ALLOW_PREVIEW_HOSTED_AI, preview_budget.PREVIEW_HOSTED_DAILY_SHOW_LIMIT,
                                preview_budget.PREVIEW_HOSTED_DAILY_VOICE_LIMIT)
                preview_budget.ALLOW_PREVIEW_HOSTED_AI = True
                preview_budget.PREVIEW_HOSTED_DAILY_SHOW_LIMIT = 2
                preview_budget.PREVIEW_HOSTED_DAILY_VOICE_LIMIT = 1
                budget_users = [post_login(client) for _ in range(3)]
                try:
                    def budget_show(u):
                        return client.post("/api/roast/generate", headers=auth(u["session_token"]),
                            data={"persona_ids": "persona_1"}, files={"images": ("face.jpg", image.getvalue(), "image/jpeg")})
                    with ThreadPoolExecutor(max_workers=3) as pool:
                        budget_results = list(pool.map(budget_show, budget_users))
                    personal_still_works = generate_same_user(0)
                    check(sorted(r.status_code for r in budget_results) == [200, 200, 429] and personal_still_works.status_code == 200,
                          "hosted preview show attempts are globally capped while personal keys still work")
                    original_line = voice_orchestrator.synthesize_line
                    preview_calls = []
                    async def fake_preview_line(*args, **kwargs):
                        name = kwargs["filename"]
                        preview_calls.append((args[0], name))
                        await asyncio.sleep(0.05)
                        await storage.save_audio(name, (ROOT / "assets/sfx/chuckle_1.mp3").read_bytes())
                        return f"/api/audio/{name}", "offline"
                    voice_orchestrator.synthesize_line = fake_preview_line
                    try:
                        preview_headers = auth(budget_users[0]["session_token"])
                        first_voice = client.get("/api/personas/persona_6/voice-preview", headers=preview_headers)
                        cached_voice = client.get("/api/personas/persona_6/voice-preview", headers=preview_headers)
                        second_voice = client.get("/api/personas/persona_7/voice-preview", headers=preview_headers)
                        anonymous_voice = client.get("/api/personas/persona_8/voice-preview", headers={"Cookie": "session_token=invalid"})
                        check(first_voice.status_code == 200 and cached_voice.status_code == 200 and
                              second_voice.status_code == 429 and anonymous_voice.status_code == 401,
                              "uncached hosted voice previews are separately capped and anonymous generation is blocked")
                        sample_zero = client.get("/api/personas/persona_9/voice-preview?sample=0", headers=parallel_headers)
                        def sample_one(_):
                            return client.get("/api/personas/persona_9/voice-preview?sample=1", headers=parallel_headers)
                        # Give every request a separate process-local lock to
                        # simulate different API workers sharing only MongoDB.
                        original_locks = personas_routes._preview_locks
                        class SeparateWorkerLocks(dict):
                            def setdefault(self, _key, default): return default
                        personas_routes._preview_locks = SeparateWorkerLocks()
                        try:
                            with ThreadPoolExecutor(max_workers=3) as pool:
                                sample_ones = list(pool.map(sample_one, range(3)))
                        finally:
                            personas_routes._preview_locks = original_locks
                        sample_one_data = sample_ones[0].json()
                        check(sample_zero.status_code == 200 and all(r.status_code == 200 for r in sample_ones)
                              and sample_zero.json()["text"] != sample_one_data["text"]
                              and sample_zero.json()["audio_url"] != sample_one_data["audio_url"]
                              and sum(name.endswith("persona_9_v2_s1.mp3") for _, name in preview_calls) == 1
                              and client.get(sample_one_data["audio_url"], headers=parallel_headers).status_code == 200
                              and client.get("/api/personas/persona_9/voice-preview?sample=2", headers=parallel_headers).status_code == 404
                              and client.get("/api/personas/persona_9/voice-preview?sample=-1", headers=parallel_headers).status_code == 422,
                              "each joke has its own cached playable sample; concurrent workers synthesize it only once")
                    finally:
                        voice_orchestrator.synthesize_line = original_line
                finally:
                    (preview_budget.ALLOW_PREVIEW_HOSTED_AI, preview_budget.PREVIEW_HOSTED_DAILY_SHOW_LIMIT,
                     preview_budget.PREVIEW_HOSTED_DAILY_VOICE_LIMIT) = budget_saved
                tunneled_show = client.post("/api/session/dispatch", data={"token": parallel_user["session_token"],
                    "method": "POST", "path": "/api/roast/generate", "kind": "form", "field:persona_ids": "persona_1"},
                    files={"file:images": ("face.jpg", image.getvalue(), "image/jpeg")}, headers={"Cookie": "session_token=invalid"})
                check(tunneled_show.status_code == 200 and
                      tunnel(parallel_user["session_token"], "GET", tunneled_show.json()["images"][0]).status_code == 200,
                      "body session transport supports multipart uploads and private binary media")
                assert client.post("/api/voice-settings/keys", headers=headers, json={"openai_key": fake_key}).status_code == 200
                captured_prompts = []
                async def capture_writer(prompt, *args, **kwargs):
                    captured_prompts.append(prompt)
                    return await fake_writer(prompt, *args, **kwargs)
                previous_writer = roast_routes.write_script
                roast_routes.write_script = capture_writer
                try:
                    response = client.post("/api/roast/generate", headers=headers,
                        data={"persona_ids": "persona_1", "subject_name": "Offline test", "duration_minutes": "3",
                              "user_context": "Always loses at karaoke", "off_limits": "Family stories"},
                        files={"images": ("face.jpg", image.getvalue(), "image/jpeg")})
                finally:
                    roast_routes.write_script = previous_writer
                check(response.status_code == 200, f"mocked roast pipeline creates a record (status {response.status_code})")
                check(captured_prompts and all(value in captured_prompts[0] for value in
                      ("Offline test", "Always loses at karaoke", "Family stories", "THE TURN PLAN")),
                      "personal details and optional boundaries reach the actual writer prompt")
                show = response.json()
                check(show["was_free_roast"] and show["credits_remaining"] == 100, "daily free roast cost and balance")
                saved_show = mongo[test_db].roasts.find_one({"id": show["roast_id"]})
                check(show["persona_ids"] == ["persona_1"] and any(b.get("stage") == "open_guest" and "Offline test" in b["text"] for b in show["transcript"])
                      and "burnt crispy" in show["transcript"][-1]["text"].lower()
                      and saved_show["off_limits"] == "Family stories",
                      "voiced opening names the guest, branded outro thanks the room, and optional boundaries persist")
                check(client.get(show["images"][0], headers=headers).status_code == 200 and
                      client.get(show["images"][0], headers=other).status_code == 404,
                      "subject image is stored and accessible only to its owner")
                audio_url = show["transcript"][0]["audio_url"]
                (storage.AUDIO_DIR / audio_url.rsplit("/", 1)[-1]).unlink()
                check(client.get(audio_url, headers=headers).status_code == 200 and client.get(audio_url, headers=other).status_code == 404,
                      "audio restores after a cache miss and is accessible only to its owner")
                check(client.post(f"/api/roast/{show['roast_id']}/share", headers=other).status_code == 404,
                      "another account cannot share this roast")
                share = client.post(f"/api/roast/{show['roast_id']}/share", headers=headers).json()
                public = client.get(f"/api/share/{share['share_id']}")
                check(public.status_code == 200 and not ({'user_id', 'off_limits', 'user_context'} & public.json().keys()),
                      "public sharing excludes owner data and private personalization notes")
                shared_image = public.json()["images"][0]
                shared_audio = public.json()["transcript"][0]["audio_url"]
                check(client.get(shared_image).status_code == 200 and client.get(shared_audio).status_code == 200,
                      "shared images and audio work through the share-scoped URLs")
                assert client.delete(f"/api/roast/{show['roast_id']}/share", headers=headers).status_code == 200
                check(client.get(f"/api/share/{share['share_id']}").status_code == 404 and
                      client.get(shared_image).status_code == 404 and client.get(shared_audio).status_code == 404,
                      "unsharing revokes the page and its share-scoped media links")

                before = client.get("/api/auth/me", headers=headers).json()["credits"]
                fail = client.post("/api/battle/generate", headers=headers, data={"persona_a": "persona_1", "persona_b": "persona_2"})
                after = client.get("/api/auth/me", headers=headers).json()["credits"]
                check(fail.status_code == 503 and before == after, "failed voice synthesis never charges credits")
                battle_routes.synthesize_show = fake_synth
                captured_prompts.clear()
                previous_battle_writer = battle_routes.write_script
                battle_routes.write_script = capture_writer
                try:
                    battle = client.post("/api/battle/generate", headers=headers,
                        data={"persona_a": "persona_1", "persona_b": "persona_2", "adult_language": "false",
                              "user_context": "An old plastic trophy", "off_limits": "family, health"})
                finally:
                    battle_routes.write_script = previous_battle_writer
                check(battle.status_code == 200 and battle.json()["credits_remaining"] == before - 5,
                      "mocked battle pipeline records and charges the expected amount")
                battle_record = mongo[test_db].roasts.find_one({"id": battle.json()["roast_id"]})
                check(captured_prompts and all(s in captured_prompts[0] for s in
                      ("An old plastic trophy", "family, health", "CONTENT MODE: CLEAN")) and
                      battle_record["off_limits"] == "family, health" and not battle_record["adult_language"],
                      "battle boundaries and clean mode reach the writer and persist privately")
                result = client.post(f"/api/roast/{show['roast_id']}/reel", headers=headers, json={"length": 30})
                assert result.status_code == 200, result.text
                reel_id = result.json()["id"]
                for _ in range(80):
                    reel = client.get(f"/api/reels/{reel_id}", headers=headers).json()
                    if reel["status"] in ("done", "failed"):
                        break
                    time.sleep(0.05)
                check(reel["status"] == "done" and client.get(reel["video_url"], headers=headers).status_code == 200,
                      "mocked background reel renders and retrieves through local storage")
                check(client.get(f"/api/reels/{reel_id}", headers=other).status_code == 404 and
                      client.get(reel["video_url"], headers=other).status_code == 404,
                      "another account cannot inspect private reel status or video")
                cached = client.post(f"/api/roast/{show['roast_id']}/reel", headers=headers, json={"length": 30}).json()
                check(cached["id"] == reel_id, "a completed current-style reel is reused")
                # Simulate an old-style completed export. The new style must render
                # a fresh file without charging an owner for the same length twice.
                mongo[test_db].reels.update_one({"id": reel_id}, {"$set": {"style_version": "legacy-test"}})
                before_upgrade = client.get("/api/auth/me", headers=headers).json()["credits"]
                upgraded = client.post(f"/api/roast/{show['roast_id']}/reel", headers=headers, json={"length": 30})
                assert upgraded.status_code == 200, upgraded.text
                new_id = upgraded.json()["id"]
                for _ in range(80):
                    new_reel = client.get(f"/api/reels/{new_id}", headers=headers).json()
                    if new_reel["status"] in ("done", "failed"):
                        break
                    time.sleep(0.05)
                after_upgrade = client.get("/api/auth/me", headers=headers).json()["credits"]
                check(new_id != reel_id and new_reel["status"] == "done" and before_upgrade == after_upgrade and
                      client.get(reel["video_url"], headers=headers).status_code == 200,
                      "a legacy reel upgrades without a second charge and its original remains downloadable")

                # A failed *paid* export must be refunded and retryable. Then
                # overlap two requests for the same length: the account lease may
                # reject one with 409, or both may receive the same queued job,
                # but only one render and one credit charge may occur.
                def failed_reel(**_kwargs):
                    raise RuntimeError("offline simulated reel-render failure")
                reel_routes.render_reel = failed_reel
                balance_before = client.get("/api/auth/me", headers=headers).json()["credits"]
                failure = client.post(f"/api/roast/{show['roast_id']}/reel", headers=headers, json={"length": 60})
                assert failure.status_code == 200, failure.text
                failure_id = failure.json()["id"]
                for _ in range(100):
                    failed_job = client.get(f"/api/reels/{failure_id}", headers=headers).json()
                    refunded_balance = client.get("/api/auth/me", headers=headers).json()["credits"]
                    if failed_job["status"] == "failed" and refunded_balance == balance_before:
                        break
                    time.sleep(0.05)
                check(failed_job["status"] == "failed" and refunded_balance == balance_before,
                      "a failed paid reel render is reported and its credits are refunded")
                render_calls = []
                def slow_reel(**kwargs):
                    render_calls.append(1)
                    time.sleep(0.5)
                    return fake_reel(**kwargs)
                reel_routes.render_reel = slow_reel
                try:
                    def retry_reel(_):
                        return client.post(f"/api/roast/{show['roast_id']}/reel", headers=headers, json={"length": 60})
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        retried = list(pool.map(retry_reel, range(2)))
                    successes = [r.json() for r in retried if r.status_code == 200]
                    assert successes and all(r.status_code in (200, 409) for r in retried)
                    assert len({r['id'] for r in successes}) == 1
                    retry_id = successes[0]["id"]
                    for _ in range(100):
                        retried_job = client.get(f"/api/reels/{retry_id}", headers=headers).json()
                        if retried_job["status"] in ("done", "failed"):
                            break
                        time.sleep(0.05)
                    after_retry = client.get("/api/auth/me", headers=headers).json()["credits"]
                    check(retried_job["status"] == "done" and len(render_calls) == 1 and
                          after_retry == balance_before - 5 and retry_id != failure_id,
                          "a failed reel can be retried; concurrent same-length requests render and charge only once")
                finally:
                    reel_routes.render_reel = fake_reel

                # Simulate crashes on both sides of debit/refund writes and
                # repeated/concurrent recovery without contacting any provider.
                uncharged, charged, refunded, legacy = ["reel-test-" + uuid.uuid4().hex for _ in range(4)]
                recover_balance = mongo[test_db].users.find_one({"id": user_id})["credits"]
                for rid, state, version, pending in [
                    (uncharged, "charging", 2, False), (charged, "charging", 2, False),
                    (refunded, "failed", 2, True), (legacy, "queued", None, False),
                ]:
                    job = {"id": rid, "user_id": user_id, "roast_id": show["roast_id"], "status": state,
                           "credits_spent": 5, "refund_pending": pending}
                    if version is not None: job["billing_version"] = version
                    mongo[test_db].reels.insert_one(job)
                mongo[test_db].users.update_one({"id": user_id}, {
                    "$inc": {"credits": -10}, "$addToSet": {"charged_reel_ids": {"$each": [charged, refunded]},
                                                               "refunded_reel_ids": refunded}})
                async def simultaneous_recovery():
                    await asyncio.gather(reel_routes.recover_interrupted_reels(), reel_routes.recover_interrupted_reels())
                client.portal.call(simultaneous_recovery)
                client.portal.call(reel_routes.recover_interrupted_reels)
                jobs = {r["id"]: r for r in mongo[test_db].reels.find({"id": {"$in": [uncharged, charged, refunded, legacy]}})}
                check(mongo[test_db].users.find_one({"id": user_id})["credits"] == recover_balance and
                      all(r["status"] == "failed" and not r.get("refund_pending") for r in jobs.values()) and
                      not jobs[uncharged].get("refund_confirmed") and
                      all(jobs[rid].get("refund_confirmed") for rid in (charged, refunded, legacy)) and
                      mongo[test_db].credit_transactions.count_documents({"_id": "reel-refund:" + uncharged}) == 0 and
                      all(mongo[test_db].credit_transactions.count_documents({"_id": "reel-refund:" + rid}) == 1
                          for rid in (charged, refunded, legacy)) and
                      all(mongo[test_db].credit_transactions.count_documents({"_id": "reel-spend:" + rid}) == 1
                          for rid in (charged, refunded)),
                      "interrupted pre-charge, post-charge, post-refund and legacy reels recover without double credits")
                crash_refund = "reel-test-" + uuid.uuid4().hex
                mongo[test_db].reels.insert_one({"id": crash_refund, "user_id": user_id, "roast_id": show["roast_id"],
                    "status": "failed", "billing_version": 2, "credits_spent": 5, "refund_pending": True})
                mongo[test_db].users.update_one({"id": user_id}, {"$inc": {"credits": -5}, "$addToSet": {"charged_reel_ids": crash_refund}})
                real_reel_ledger = reel_routes.credits_collection
                class FailReelLedgerOnce:
                    async def insert_one(self, _doc):
                        raise RuntimeError("simulated interruption after refund balance update")
                reel_routes.credits_collection = FailReelLedgerOnce()
                try:
                    try:
                        client.portal.call(reel_routes._refund_pending, crash_refund)
                    except RuntimeError:
                        pass
                    else:
                        raise AssertionError("Injected reel refund failure did not occur")
                finally:
                    reel_routes.credits_collection = real_reel_ledger
                client.portal.call(reel_routes.recover_interrupted_reels)
                client.portal.call(reel_routes.recover_interrupted_reels)
                check(mongo[test_db].users.find_one({"id": user_id})["credits"] == recover_balance and
                      mongo[test_db].reels.find_one({"id": crash_refund})["refund_confirmed"] and
                      mongo[test_db].credit_transactions.count_documents({"_id": "reel-refund:" + crash_refund}) == 1 and
                      mongo[test_db].credit_transactions.count_documents({"_id": "reel-spend:" + crash_refund}) == 1,
                      "a crash between reel refund balance and ledger writes is repaired exactly once")

                # A staged show is invisible before settlement. Crashes before
                # or after the atomic debit are reconciled without double spend.
                gen_engine = roast_routes.eng
                gen_ids = ["generation-test-" + uuid.uuid4().hex for _ in range(4)]
                gen_uncharged, gen_charged, gen_late, gen_free = gen_ids
                gen_balance = mongo[test_db].users.find_one({"id": user_id})["credits"]
                template = {k: v for k, v in saved_show.items() if k not in ("_id", "share_id")}
                for rid, state, is_free in [(gen_uncharged, "pending", False), (gen_charged, "pending", False),
                                            (gen_late, "aborted", False), (gen_free, "pending", True)]:
                    staged = {**template, "id": rid, "user_id": user_id, "billing_version": 2,
                              "billing_state": state, "billing_staged_at": "2000-01-01T00:00:00+00:00",
                              "billing_description": "Offline interrupted generation", "billing_free_date": gen_engine.today_utc() if is_free else None,
                              "credits_spent": 0 if is_free else 5, "was_free_roast": is_free}
                    if rid == gen_charged:
                        staged["share_id"] = "share-pending-" + uuid.uuid4().hex
                    mongo[test_db].roasts.insert_one(staged)
                mongo[test_db].users.update_one({"id": user_id}, {"$inc": {"credits": -10},
                    "$addToSet": {"generation_charge_ids": {"$each": [gen_charged, gen_late, gen_free]}}})
                prehistory = client.get("/api/roast/history", headers=headers).json()["history"]
                staged_share = mongo[test_db].roasts.find_one({"id": gen_charged})["share_id"]
                check(not any(item["id"] in gen_ids for item in prehistory) and
                      client.get("/api/share/" + staged_share).status_code == 404 and
                      client.post(f"/api/roast/{gen_charged}/share", headers=headers).status_code == 404 and
                      client.post(f"/api/roast/{gen_charged}/reel", headers=headers, json={"length": 30}).status_code == 404,
                      "unsettled shows are hidden from history, sharing and reel export")
                async def simultaneous_generation_recovery():
                    await asyncio.gather(gen_engine.recover_interrupted_generations(), gen_engine.recover_interrupted_generations())
                client.portal.call(simultaneous_generation_recovery)
                client.portal.call(gen_engine.recover_interrupted_generations)
                gen_records = {r["id"]: r for r in mongo[test_db].roasts.find({"id": {"$in": gen_ids}})}
                gen_history = client.get("/api/roast/history", headers=headers).json()["history"]
                history_ids = {item["id"] for item in gen_history}
                check(mongo[test_db].users.find_one({"id": user_id})["credits"] == gen_balance - 10 and
                      gen_records[gen_uncharged]["billing_state"] == "aborted" and
                      all(gen_records[rid]["billing_state"] == "committed" and rid in history_ids for rid in (gen_charged, gen_late, gen_free)) and
                      gen_uncharged not in history_ids and
                      mongo[test_db].credit_transactions.count_documents({"_id": "generation:" + gen_uncharged}) == 0 and
                      all(mongo[test_db].credit_transactions.count_documents({"_id": "generation:" + rid}) == 1 for rid in (gen_charged, gen_late, gen_free)),
                      "pre-debit, post-debit and free generation recovery publishes the right shows exactly once")
                from models import RoastRecord, User
                crash_show = RoastRecord(user_id=user_id, persona_ids=["persona_1"], credits_spent=5,
                                         transcript=[{"persona_id": "persona_1", "text": "offline fixture"}])
                user_for_commit = User(**mongo[test_db].users.find_one({"id": user_id}))
                real_generation_ledger = gen_engine.credits_collection
                class FailGenerationLedger:
                    async def insert_one(self, _doc):
                        raise RuntimeError("simulated generation ledger outage")
                gen_engine.credits_collection = FailGenerationLedger()
                try:
                    try:
                        client.portal.call(gen_engine.commit_record, user_for_commit, crash_show, [], "Offline paid show")
                    except RuntimeError:
                        pass
                    else:
                        raise AssertionError("Injected generation ledger failure did not occur")
                finally:
                    gen_engine.credits_collection = real_generation_ledger
                assert mongo[test_db].roasts.find_one({"id": crash_show.id})["billing_state"] == "pending"
                client.portal.call(gen_engine.recover_interrupted_generations)
                client.portal.call(gen_engine.recover_interrupted_generations)
                check(mongo[test_db].users.find_one({"id": user_id})["credits"] == gen_balance - 15 and
                      mongo[test_db].roasts.find_one({"id": crash_show.id})["billing_state"] == "committed" and
                      mongo[test_db].credit_transactions.count_documents({"_id": "generation:" + crash_show.id}) == 1,
                      "a generation ledger outage recovers the already-paid result without charging again")
                before_storage = mongo[test_db].users.find_one({"id": user_id})["credits"]
                unsaved_show = RoastRecord(user_id=user_id, persona_ids=["persona_1"], credits_spent=5)
                real_put = gen_engine.put_blob
                async def fail_subject_storage(*_args, **_kwargs):
                    raise OSError("offline storage failure")
                gen_engine.put_blob = fail_subject_storage
                try:
                    try:
                        client.portal.call(gen_engine.commit_record, user_for_commit, unsaved_show, [image.getvalue()], "Offline paid show")
                    except Exception as exc:
                        assert getattr(exc, "status_code", None) == 503
                    else:
                        raise AssertionError("Injected storage failure did not occur")
                finally:
                    gen_engine.put_blob = real_put
                check(mongo[test_db].users.find_one({"id": user_id})["credits"] == before_storage and
                      not mongo[test_db].roasts.find_one({"id": unsaved_show.id}),
                      "failed subject storage happens before any generation charge")

                # Exercise the real OpenAI client, script parser and speech orchestrator
                # against an in-process HTTP stub, never against a paid provider.
                provider_calls = []
                sample_mp3 = (ROOT / "assets/sfx/chuckle_1.mp3").read_bytes()
                from services.audio_mastering import master_voice_bytes
                leveled_sample_mp3 = master_voice_bytes(sample_mp3)
                class ProviderStub(BaseHTTPRequestHandler):
                    fixture_lines = None
                    def log_message(self, *_args): pass
                    def do_POST(self):
                        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
                        provider_calls.append((self.path, body, self.headers.get("Authorization")))
                        if self.path == "/v1/chat/completions":
                            lines = self.fixture_lines or [
                                {"persona_id": "persona_1", "type": "intro" if i == 0 else "joke",
                                 "text": f"Offline fixture line number {i} keeps the microphone moving.",
                                 "laugh_after": "small", "reaction": "laugh", "emotion": "cocky"}
                                for i in range(10)]
                            data = json.dumps({"id": "offline", "object": "chat.completion", "created": 1, "model": "gpt-4.1",
                                "choices": [{"index": 0, "finish_reason": "stop",
                                    "message": {"role": "assistant", "content": json.dumps({"script": lines})}}]}).encode()
                            content_type = "application/json"
                        elif self.path == "/v1/audio/speech":
                            data, content_type = sample_mp3, "audio/mpeg"
                        else:
                            self.send_error(404); return
                        self.send_response(200)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                provider = ThreadingHTTPServer(("127.0.0.1", 0), ProviderStub)
                worker = Thread(target=provider.serve_forever, daemon=True)
                worker.start()
                previous_base = os.environ.get("OPENAI_BASE_URL")
                os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{provider.server_port}/v1"
                try:
                    contract_user = post_login(client)
                    contract_headers = auth(contract_user["session_token"])
                    assert client.post("/api/voice-settings/keys", headers=contract_headers,
                                       json={"openai_key": fake_key}).status_code == 200
                    roast_routes.write_script, roast_routes.synthesize_show = real_writer, real_synth
                    roast_routes.voice_beats_progressive = real_progressive
                    contract = client.post("/api/roast/generate", headers=contract_headers,
                        data={"persona_ids": "persona_1"},
                        files={"images": ("face.jpg", image.getvalue(), "image/jpeg")})
                    check(contract.status_code == 200 and len(contract.json()["transcript"]) == 15
                          and "burnt crispy" in contract.json()["transcript"][-1]["text"].lower(),
                          f"real OpenAI-compatible client writes and voices a show and branded sign-off against a local stub ({contract.status_code})")
                    speech_bodies = [body for path, body, _ in provider_calls if path == "/v1/audio/speech"]
                    check(any(path == "/v1/chat/completions" and body.get("model") == "gpt-4.1" for path, body, _ in provider_calls)
                          and len(speech_bodies) == 15 and any("burnt crispy" in body.get("input", "").lower() for body in speech_bodies)
                          and all(h == f"Bearer {fake_key}" for _, _, h in provider_calls),
                          "BYOK chat, expressive opening/outro speech and authorization use the expected API contract")
                    # The real writer rejects an obvious clean-mode violation
                    # before TTS/credit debit, with no hidden rewrite request.
                    provider_calls.clear()
                    ProviderStub.fixture_lines = [
                        {"persona_id": "persona_1", "type": "joke",
                         "text": ("That is fucking ridiculous." if i == 0 else f"Offline fixture number {i} is moving.")}
                        for i in range(10)]
                    before_reject = client.get("/api/auth/me", headers=contract_headers).json()["credits"]
                    rejected = client.post("/api/roast/generate", headers=contract_headers,
                        data={"persona_ids": "persona_1", "adult_language": "false"},
                        files={"images": ("face.jpg", image.getvalue(), "image/jpeg")})
                    after_reject = client.get("/api/auth/me", headers=contract_headers).json()["credits"]
                    check(rejected.status_code == 502 and before_reject == after_reject and
                          len([1 for path, _, _ in provider_calls if path == "/v1/chat/completions"]) == 1 and
                          not any(path == "/v1/audio/speech" for path, _, _ in provider_calls) and
                          "provider may bill" in rejected.json()["detail"].lower(),
                          "clean-mode local rejection makes one model call, no TTS or RoastBox debit")
                    ProviderStub.fixture_lines = None
                    provider_calls.clear()
                    joke0 = client.get("/api/personas/persona_11/voice-preview?sample=0", headers=contract_headers)
                    joke1 = client.get("/api/personas/persona_11/voice-preview?sample=1", headers=contract_headers)
                    joke1_again = client.get("/api/personas/persona_11/voice-preview?sample=1", headers=contract_headers)
                    sent_lines = [body.get("input") for path, body, _ in provider_calls if path == "/v1/audio/speech"]
                    check(joke0.status_code == joke1.status_code == joke1_again.status_code == 200
                          and sent_lines == personas_routes._BY_ID["persona_11"]["punchlines"]
                          and client.get(joke1.json()["audio_url"], headers=contract_headers).content == leveled_sample_mp3,
                          "both sample buttons synthesize their exact punchline and replay a locally leveled cached voice")
                    saved = (openai_service.EMERGENT_LLM_KEY, openai_service.OPENAI_API_KEY,
                             roast_writer.EMERGENT_LLM_KEY, roast_writer.OPENAI_API_KEY,
                             personas_routes.EMERGENT_LLM_KEY, personas_routes.OPENAI_API_KEY)
                    openai_service.EMERGENT_LLM_KEY = roast_writer.EMERGENT_LLM_KEY = personas_routes.EMERGENT_LLM_KEY = ""
                    openai_service.OPENAI_API_KEY = roast_writer.OPENAI_API_KEY = personas_routes.OPENAI_API_KEY = fake_key
                    provider_calls.clear()
                    try:
                        hosted = client.post("/api/roast/generate", headers=auth(oauth_token),
                            data={"persona_ids": "persona_1"},
                            files={"images": ("face.jpg", image.getvalue(), "image/jpeg")})
                        hosted_preview = client.get("/api/personas/persona_3/voice-preview", headers=auth(oauth_token))
                        check(hosted.status_code == 200 and hosted_preview.status_code == 200 and
                              all(h == f"Bearer {fake_key}" for _, _, h in provider_calls) and
                              not any(body.get("model", "").startswith("claude") for _, body, _ in provider_calls),
                              "hosted direct OpenAI writing, speech and voice preview use the real client contract")
                    finally:
                        (openai_service.EMERGENT_LLM_KEY, openai_service.OPENAI_API_KEY,
                         roast_writer.EMERGENT_LLM_KEY, roast_writer.OPENAI_API_KEY,
                         personas_routes.EMERGENT_LLM_KEY, personas_routes.OPENAI_API_KEY) = saved
                finally:
                    provider.shutdown(); provider.server_close(); worker.join(timeout=3)
                    if previous_base is None: os.environ.pop("OPENAI_BASE_URL", None)
                    else: os.environ["OPENAI_BASE_URL"] = previous_base

                # A test-only staging environment must never accept a live key.
                saved_key = payment_routes.STRIPE_API_KEY
                payment_routes.STRIPE_API_KEY = "sk_live_not_a_real_key"
                try:
                    try:
                        payment_routes._checkout()
                    except payment_routes.HTTPException as exc:
                        check(exc.status_code == 503, "Stripe test-only guard rejects a live key before any provider request")
                    else:
                        raise AssertionError("Stripe test-only guard did not reject the live key")
                finally:
                    payment_routes.STRIPE_API_KEY = saved_key

                # The vendor SDK truncates float * 100. Every price must still
                # reach Stripe as the exact intended integer number of cents.
                catalog = payment_routes.PRODUCT_CATALOG
                amounts = [p["amount_usd"] for p in catalog.values()] + [
                    round(p["amount_usd"] * payment_routes.VIP_CREDIT_DISCOUNT, 2)
                    for p in catalog.values() if p["type"] == "credits"
                ]
                check(all(int(payment_routes._sdk_safe_amount(a) * 100) == round(a * 100) for a in amounts),
                      "Stripe SDK receives exact cents for every catalog and discounted price")

                # A mocked Stripe checkout/status flow still uses the app's real
                # transaction and entitlement code.
                checkout_requests = []
                checkout_id = "cs_test_checkout_" + uuid.uuid4().hex
                class FakeCheckout:
                    async def create_checkout_session(self, request):
                        checkout_requests.append(request)
                        return SimpleNamespace(url="https://checkout.stripe.com/c/pay/offline", session_id=checkout_id)
                    async def get_checkout_status(self, _sid):
                        return SimpleNamespace(payment_status="paid", amount_total=499, currency="usd")
                real_checkout = payment_routes._checkout
                payment_routes._checkout = lambda *_args, **_kwargs: FakeCheckout()
                try:
                    oauth_headers = auth(oauth_token)
                    unsafe = client.post("/api/payments/checkout", headers=oauth_headers,
                                         json={"pack_id": "credits_starter", "origin_url": "https://evil.example/path"})
                    mismatch = client.post("/api/payments/checkout", headers={**oauth_headers, "Origin": "https://real.example"},
                                           json={"pack_id": "credits_starter", "origin_url": "https://evil.example"})
                    check(unsafe.status_code == 400 and mismatch.status_code == 400 and not checkout_requests,
                          "checkout rejects unsafe or mismatched return origins")
                    checkout = client.post("/api/payments/checkout", headers=oauth_headers,
                                           json={"pack_id": "credits_starter", "origin_url": "http://127.0.0.1:3000"})
                    check(checkout.status_code == 200 and checkout_requests[0].amount == 4.99,
                          "mocked checkout uses server-authoritative product pricing")
                    status = client.get(f"/api/payments/status/{checkout_id}", headers=oauth_headers)
                    again = client.get(f"/api/payments/status/{checkout_id}", headers=oauth_headers)
                    check(status.status_code == 200 and again.status_code == 200 and again.json()["credits_balance"] == 55,
                          "mocked paid checkout grants credits exactly once")
                finally:
                    payment_routes._checkout = real_checkout

                # Activity is account-scoped, bounded and never exposes provider
                # session IDs, internal fields, transcripts or personal notes.
                for i in range(23):
                    mongo[test_db].payment_transactions.insert_one({
                        "id": f"other-payment-{i}", "user_id": user_id,
                        "stripe_session_id": f"cs_test_private_{uuid.uuid4().hex}", "amount_usd": 4.99,
                        "pack_id": "credits_starter", "payment_status": "pending", "internal_note": "PRIVATE_SENTINEL",
                        "created_at": f"2026-01-01T10:{i:02}:00+00:00"})
                own_activity_response = client.get("/api/payments/activity", headers=auth(oauth_token))
                other_activity_response = client.get("/api/payments/activity", headers=headers)
                own_activity, other_activity = own_activity_response.json(), other_activity_response.json()
                tunneled_activity = tunnel(token, "GET", "/api/payments/activity")
                private_names = {"stripe_session_id", "user_id", "internal_note", "transcript", "user_context", "off_limits", "_id"}
                rows = own_activity["payments"] + own_activity["credit_activity"] + own_activity["shows"] + \
                       other_activity["payments"] + other_activity["credit_activity"] + other_activity["shows"]
                check(own_activity_response.status_code == other_activity_response.status_code == 200 and
                      own_activity_response.headers.get("cache-control") == "private, no-store" and
                      any(p.get("payment_status") == "paid" and p.get("product_name") == "Starter Pack" for p in own_activity["payments"]) and
                      len(other_activity["payments"]) == other_activity["limit"] == 20 and
                      tunneled_activity.status_code == 200 and tunneled_activity.json() == other_activity and
                      not any(p.get("id", "").startswith("other-payment-") for p in own_activity["payments"]) and
                      not any(private_names & row.keys() for row in rows) and "PRIVATE_SENTINEL" not in other_activity_response.text and
                      client.get("/api/payments/activity", headers={"Cookie": "session_token=invalid"}).status_code == 401,
                      "account activity is private, scoped, bounded and excludes sensitive provider and roast data")

                # Offline signature verification and idempotence: no real Stripe request occurs.
                session_id = "cs_test_offline_" + uuid.uuid4().hex
                mongo[test_db].payment_transactions.insert_one({"stripe_session_id": session_id, "user_id": user_id,
                    "payment_status": "pending", "pack_id": "credits_starter", "pack_type": "credits", "credits": 50})
                payload = json.dumps({"id": "evt_offline", "type": "checkout.session.completed", "data": {
                    "object": {"id": session_id, "payment_status": "paid", "metadata": {}}}}, separators=(",", ":")).encode()
                credit_before = client.get("/api/auth/me", headers=headers).json()["credits"]
                bad = client.post("/api/payments/webhook", content=payload, headers={"stripe-signature": "invalid"})
                check(bad.status_code == 400 and client.get("/api/auth/me", headers=headers).json()["credits"] == credit_before,
                      "unsigned or invalid payment webhooks cannot grant credits")
                timestamp = int(time.time())
                signature = hmac.new(b"whsec_offline_test_secret", str(timestamp).encode() + b"." + payload, hashlib.sha256).hexdigest()
                sig_header = {"stripe-signature": f"t={timestamp},v1={signature}"}
                first = client.post("/api/payments/webhook", content=payload, headers=sig_header)
                second = client.post("/api/payments/webhook", content=payload, headers=sig_header)
                balance = client.get("/api/auth/me", headers=headers).json()["credits"]
                check(first.status_code == 200 and second.status_code == 200 and balance == credit_before + 50,
                      "signed payment webhook applies credit exactly once")

                def signed_event(sid, metadata=None):
                    content = json.dumps({"id": "evt_" + sid, "type": "checkout.session.completed", "data": {
                        "object": {"id": sid, "payment_status": "paid", "metadata": metadata or {}}}}, separators=(",", ":")).encode()
                    ts = int(time.time())
                    sig = hmac.new(b"whsec_offline_test_secret", str(ts).encode() + b"." + content, hashlib.sha256).hexdigest()
                    return content, {"stripe-signature": f"t={ts},v1={sig}"}

                unknown_payload, unknown_sig = signed_event("cs_test_unknown_" + uuid.uuid4().hex, {"source": "da_roastbox"})
                check(client.post("/api/payments/webhook", content=unknown_payload, headers=unknown_sig).status_code == 503,
                      "an early signed webhook for this app is retried until its checkout is tracked")

                # Simulate a crash after the atomic user update but before the ledger write.
                recovery_id = "cs_test_recovery_" + uuid.uuid4().hex
                mongo[test_db].payment_transactions.insert_one({"stripe_session_id": recovery_id, "user_id": user_id,
                    "payment_status": "pending", "pack_id": "credits_starter", "pack_type": "credits", "credits": 50})
                recovery_payload, recovery_sig = signed_event(recovery_id)
                recovery_before = client.get("/api/auth/me", headers=headers).json()["credits"]
                real_ledger = payment_routes.credits_collection
                class FailOnceLedger:
                    failed = False
                    async def insert_one(self, doc):
                        if not self.failed:
                            self.failed = True
                            raise RuntimeError("simulated crash after entitlement update")
                        return await real_ledger.insert_one(doc)
                    async def find_one(self, *args, **kwargs):
                        return await real_ledger.find_one(*args, **kwargs)
                payment_routes.credits_collection = FailOnceLedger()
                try:
                    try:
                        client.post("/api/payments/webhook", content=recovery_payload, headers=recovery_sig)
                    except RuntimeError as exc:
                        assert "simulated crash" in str(exc)
                    else:
                        raise AssertionError("Injected payment failure did not occur")
                    pending = mongo[test_db].payment_transactions.find_one({"stripe_session_id": recovery_id})
                    assert pending["payment_status"] == "pending"
                    recovered = client.post("/api/payments/webhook", content=recovery_payload, headers=recovery_sig)
                    recovery_after = client.get("/api/auth/me", headers=headers).json()["credits"]
                    check(recovered.status_code == 200 and recovery_after == recovery_before + 50 and
                          mongo[test_db].payment_transactions.find_one({"stripe_session_id": recovery_id})["payment_status"] == "paid" and
                          mongo[test_db].credit_transactions.count_documents({"stripe_session_id": recovery_id}) == 1,
                          "interrupted payment fulfillment retries without losing or double-granting credits")
                finally:
                    payment_routes.credits_collection = real_ledger

                # Duplicate events and simultaneous distinct passes must not lose
                # an extension, even without MongoDB multi-document transactions.
                oauth_id = client.get("/api/auth/me", headers=auth(oauth_token)).json()["id"]
                mongo[test_db].users.update_one({"id": oauth_id}, {"$set": {"plan_tier": "free", "plan_until": None}})
                pass_before = client.get("/api/auth/me", headers=auth(oauth_token)).json()["credits"]
                pass_ids = ["cs_test_pass_" + uuid.uuid4().hex for _ in range(2)]
                for sid in pass_ids:
                    mongo[test_db].payment_transactions.insert_one({"stripe_session_id": sid, "user_id": oauth_id,
                        "payment_status": "pending", "pack_id": "plus_subscription", "pack_type": "plus_subscription", "credits": 150})
                events = [signed_event(sid) for sid in pass_ids for _ in range(4)]
                with ThreadPoolExecutor(max_workers=8) as pool:
                    results = list(pool.map(lambda item: client.post("/api/payments/webhook", content=item[0], headers=item[1]), events))
                after_pass = mongo[test_db].users.find_one({"id": oauth_id})
                until = datetime.fromisoformat(after_pass["plan_until"])
                check(all(r.status_code == 200 for r in results) and after_pass["credits"] == pass_before + 300 and
                      until > datetime.now(timezone.utc) + timedelta(days=59) and
                      all(mongo[test_db].credit_transactions.count_documents({"stripe_session_id": sid}) == 1 for sid in pass_ids),
                      "concurrent duplicate webhooks apply each pass and its extension exactly once")

                # New pass benefits must expire without revoking separately
                # purchased permanent add-ons or changing legacy user flags.
                assert not after_pass.get("premium_personas_unlocked") and not after_pass.get("premium_voices_unlocked")
                plus_voice = client.post("/api/roast/generate", headers=auth(oauth_token),
                                         data={"persona_ids": "persona_1", "use_premium_voice": "true"})
                assert plus_voice.status_code == 400  # authorized, then stopped before AI for missing image
                vip_id = "cs_test_vip_" + uuid.uuid4().hex
                mongo[test_db].payment_transactions.insert_one({"stripe_session_id": vip_id, "user_id": oauth_id,
                    "payment_status": "pending", "pack_id": "vip_subscription", "pack_type": "vip_subscription", "credits": 500})
                vip_payload, vip_sig = signed_event(vip_id)
                assert client.post("/api/payments/webhook", content=vip_payload, headers=vip_sig).status_code == 200
                vip = client.get("/api/auth/me", headers=auth(oauth_token)).json()
                premium_id = next(p["id"] for p in personas_routes._PERSONAS if p.get("tier") == "premium")
                premium_check = lambda: client.post("/api/roast/generate", headers=auth(oauth_token), data={"persona_ids": premium_id})
                catalog_vip = client.get("/api/personas", headers=auth(oauth_token)).json()
                check(vip["plan_tier"] == "vip" and not vip["premium_personas_unlocked"] and
                      not vip["premium_voices_unlocked"] and catalog_vip["premium_unlocked"] and premium_check().status_code == 400,
                      "active VIP grants time-limited persona/voice access without permanent add-on flags")
                mongo[test_db].users.update_one({"id": oauth_id}, {"$set": {"plan_until": "2000-01-01T00:00:00+00:00"}})
                expired = client.get("/api/auth/me", headers=auth(oauth_token)).json()
                expired_personas = client.get("/api/personas", headers=auth(oauth_token)).json()
                expired_voice = client.post("/api/roast/generate", headers=auth(oauth_token),
                                            data={"persona_ids": "persona_1", "use_premium_voice": "true"})
                check(expired["plan_tier"] == "free" and not expired_personas["premium_unlocked"] and
                      premium_check().status_code == 402 and expired_voice.status_code == 402,
                      "new pass persona and voice access expires on the server before AI is called")
                for product in ("premium_personas_bundle", "premium_voices_bundle"):
                    sid = "cs_test_bundle_" + uuid.uuid4().hex
                    mongo[test_db].payment_transactions.insert_one({"stripe_session_id": sid, "user_id": oauth_id,
                        "payment_status": "pending", "pack_id": product, "pack_type": catalog[product]["type"], "credits": 0})
                    bundle_payload, bundle_sig = signed_event(sid)
                    assert client.post("/api/payments/webhook", content=bundle_payload, headers=bundle_sig).status_code == 200
                permanent = client.get("/api/auth/me", headers=auth(oauth_token)).json()
                permanent_catalog = client.get("/api/personas", headers=auth(oauth_token)).json()
                permanent_voice = client.post("/api/roast/generate", headers=auth(oauth_token),
                                              data={"persona_ids": "persona_1", "use_premium_voice": "true"})
                check(permanent["premium_personas_unlocked"] and permanent["premium_voices_unlocked"] and
                      permanent_catalog["premium_unlocked"] and premium_check().status_code == 400 and permanent_voice.status_code == 400,
                      "separate permanent persona and voice purchases survive pass expiry")
                print("Offline integration checks completed successfully.", flush=True)
    finally:
        mongo.drop_database(test_db)
        mongo.close()


if __name__ == "__main__":
    main()
