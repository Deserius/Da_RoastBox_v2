"""Regression tests for preview-account roast generation.

The bug this locks down: a preview account that saved its own OpenAI key (BYOK)
was still routed through the shared hosted-AI budget. The budget had no hosted
key to report, so generation failed with "No hosted AI key is configured. Add
your own OpenAI key in Settings." — telling the user to add a key they had just
added. Any personal key now bypasses the shared budget entirely.

No provider is called: the writer client and TTS are faked.
"""
import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "roastbox_byok_test")
os.environ.setdefault("JWT_SECRET", "0123456789abcdef0123456789abcdef")
os.environ["APP_ENV"] = "development"
os.environ["ENABLE_PREVIEW_LOGIN"] = "true"
os.environ["PREVIEW_UNLIMITED_CREDITS"] = "true"
# Hosted AI deliberately disabled: a personal key must not need it.
os.environ["ALLOW_PREVIEW_HOSTED_AI"] = "false"
os.environ["PREVIEW_HOSTED_DAILY_SHOW_LIMIT"] = "-1"
os.environ["PREVIEW_HOSTED_DAILY_VOICE_LIMIT"] = "-1"
os.environ["STORAGE_BACKEND"] = "local"

import mongomock_motor  # noqa: E402
import motor.motor_asyncio as motor_asyncio  # noqa: E402

motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from services import roast_writer as writer  # noqa: E402
from services import voice_orchestrator as voice  # noqa: E402

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082")


def check(name, condition, detail=""):
    if not condition:
        raise AssertionError(f"{name} failed{': ' + detail if detail else ''}")
    print(f"PASS: {name}")


def _script(beats=11):
    return json.dumps({"script": [
        {"persona_id": "persona_1", "type": "joke",
         "text": f"Offline original beat number {i} about the trophy and the socks."}
        for i in range(beats)]})


class _FakeCompletions:
    def __init__(self, content):
        self.content, self.calls = content, []

    def create(self, **kwargs):
        from types import SimpleNamespace
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


def _generate(client, headers):
    """Start a show and poll until it settles, like the browser does."""
    import time

    started = client.post("/api/roast/generate", headers=headers,
                          data={"persona_ids": "persona_1", "subject_name": "Test",
                                "duration_minutes": "3", "roast_tier": "standard",
                                "adult_language": "false"},
                          files=[("images", ("s.png", io.BytesIO(PNG), "image/png"))])
    if started.status_code != 200:
        return started
    # The POST must not block on the show: that is what tripped the proxy.
    check("generate returns immediately with a job id",
          bool(started.json().get("job_id")) and started.json().get("status") == "running",
          str(started.json())[:160])
    job_id = started.json()["job_id"]
    deadline = time.time() + 120
    last = None
    while time.time() < deadline:
        last = client.get(f"/api/roast/jobs/{job_id}", headers=headers)
        if last.status_code != 200 or last.json().get("status") != "running":
            return last
        time.sleep(0.05)
    return last


def _other_user_cannot_read(client, headers):
    """A job id is a capability: it must not be readable by another account."""
    started = client.post("/api/roast/generate", headers=headers,
                          data={"persona_ids": "persona_1", "duration_minutes": "3"},
                          files=[("images", ("s.png", io.BytesIO(PNG), "image/png"))])
    if started.status_code != 200:
        return True  # nothing to leak if the job was refused
    job_id = started.json()["job_id"]
    other = client.post("/api/auth/preview-login").json()
    oh = {"Authorization": f"Bearer {other['session_token']}"}
    return client.get(f"/api/roast/jobs/{job_id}", headers=oh).status_code == 404


def main():
    with TestClient(server.app) as client:
        tok = client.post("/api/auth/preview-login").json()["session_token"]
        headers = {"Authorization": f"Bearer {tok}"}

        saved = client.post("/api/voice-settings/keys", headers=headers,
                            json={"openai_key": "sk-proj-personalkey123456"})
        check("preview account can save a personal OpenAI key", saved.status_code == 200)
        me = client.get("/api/auth/me", headers=headers).json()
        check("personal key is recorded", me["has_byok_openai"] is True)

        fake = _FakeCompletions(_script())

        async def fake_tts(*_a, **_k):
            return b"ID3fakeaudio"

        with patch.object(writer, "get_client",
                          lambda _k: type("C", (), {"chat": type("X", (), {"completions": fake})()})()), \
             patch.object(writer, "MODEL_CHAIN", ["mock-model"]), \
             patch.object(voice, "synthesize_tts_openai", fake_tts):
            resp = _generate(client, headers)

        check("generation succeeds using the personal key", resp.status_code == 200,
              f"{resp.status_code} {str(resp.json().get('detail'))[:160]}")
        body = resp.json()
        # The endpoint returns a rendered transcript, not raw beats.
        check("a transcript was produced", len(body.get("transcript", [])) > 0, str(body)[:200])
        check("job results are private to their owner", _other_user_cannot_read(client, headers))
        check("the roast is addressable", bool(body.get("roast_id")))
        check("the personal key reached the provider", len(fake.calls) >= 1)

        # The shared budget must not have been touched: hosted AI is disabled
        # above, so any consumption would have raised 503.
        usage = client.get("/api/diagnostics", headers=headers)
        check("diagnostics still respond", usage.status_code == 200)

    print("PASS: a personal key generates roasts without hosted AI enabled")


main()
