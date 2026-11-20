"""v6 persona expansion: 25 free + 15 premium roasters, all fully configured. No LLM calls."""
import json
import uuid
from pathlib import Path
import pytest
import requests

from tests._env import API

BACKEND = Path(__file__).resolve().parents[1]
PUBLIC = BACKEND.parent / "frontend" / "public"
PERSONAS = json.loads((BACKEND / "data" / "personas.json").read_text())
NEW_FREE = {f"persona_{i}" for i in range(21, 26)}
NEW_PREMIUM = {f"persona_p{i}" for i in range(6, 16)}
REQUIRED = ["id", "name", "displayName", "tagline", "description", "role", "age", "rating", "color",
            "image", "gender", "tier", "comic_inspiration", "speech", "quirks_prompt", "lingo",
            "punchlines", "topics", "tts_voice", "elevenlabs"]


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{API}/auth/dev-login", json={"email": f"TEST_v6_{uuid.uuid4().hex[:8]}@example.com"}, timeout=15)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


class TestPersonaData:
    def test_counts(self):
        assert len(PERSONAS) == 40
        assert sum(p["tier"] == "premium" for p in PERSONAS) == 15
        assert sum(p["tier"] == "free" for p in PERSONAS) == 25

    def test_unique_ids_and_names(self):
        assert len({p["id"] for p in PERSONAS}) == 40
        assert len({p["displayName"] for p in PERSONAS}) == 40

    @pytest.mark.parametrize("p", PERSONAS, ids=lambda p: p["id"])
    def test_persona_complete(self, p):
        for key in REQUIRED:
            assert p.get(key) not in (None, "", []), f"{p['id']} missing {key}"
        assert p["tts_voice"] in {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
        assert p["elevenlabs"]["voice_id"]
        assert (PUBLIC / p["image"]).stat().st_size > 10_000, f"portrait missing for {p['id']}"

    def test_new_ids_present(self):
        ids = {p["id"] for p in PERSONAS}
        assert NEW_FREE <= ids and NEW_PREMIUM <= ids


class TestPersonaApi:
    def test_anonymous_locks_all_premium(self):
        data = requests.get(f"{API}/personas", timeout=15).json()
        locked = {p["id"] for p in data["personas"] if p["locked"]}
        assert locked == {p["id"] for p in PERSONAS if p["tier"] == "premium"}

    def test_new_free_personas_unlocked(self, headers):
        data = requests.get(f"{API}/personas", headers=headers, timeout=15).json()
        by_id = {p["id"]: p for p in data["personas"]}
        for pid in NEW_FREE:
            assert by_id[pid]["locked"] is False
        for pid in NEW_PREMIUM:
            assert by_id[pid]["locked"] is True and by_id[pid]["is_premium"] is True

    def test_new_premium_persona_gated_on_generate(self, headers):
        files = {"images": ("a.jpg", b"\xff\xd8\xff", "image/jpeg")}
        r = requests.post(f"{API}/roast/generate", headers=headers,
                          data={"persona_ids": "persona_p15"}, files=files, timeout=30)
        assert r.status_code == 402

    def test_bundle_mentions_15(self):
        packs = {p["id"]: p for p in requests.get(f"{API}/payments/packs", timeout=15).json()["packs"]}
        assert "15" in packs["premium_personas_bundle"]["tagline"]


class TestDiagnostics:
    def test_health(self):
        assert requests.get(f"{API}/health", timeout=10).json()["status"] == "ok"

    def test_diagnostics_shallow(self):
        d = requests.get(f"{API}/diagnostics", timeout=15).json()
        assert d["checks"]["mongo"]["ok"] is True
        assert d["personas"]["total"] == 40
        assert d["personas"]["missing_images"] == [] and d["personas"]["missing_voice_config"] == []
        assert d["config"]["emergent_llm_key"] and d["config"]["stripe_api_key"]

    def test_deep_requires_auth(self):
        assert requests.get(f"{API}/diagnostics?deep=true", timeout=15).status_code == 401
