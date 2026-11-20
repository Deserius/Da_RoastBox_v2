"""v7 gap coverage: authenticated deep diagnostics, p12 gating, BYOK save/clear, SKU count. No roast LLM calls."""
import uuid
import pytest
import requests

from tests._env import API


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{API}/auth/dev-login", json={"email": f"TEST_v7_{uuid.uuid4().hex[:8]}@example.com"}, timeout=15)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


# Diagnostics deep (live provider calls: tiny LLM + TTS ping)
def test_deep_diagnostics_authenticated(headers):
    d = requests.get(f"{API}/diagnostics?deep=true", headers=headers, timeout=90).json()
    for k in ("mongo", "llm", "tts", "stripe"):
        assert d["checks"][k]["ok"] is True, f"{k}: {d['checks'][k]}"
    assert d["status"] == "ok"


# Premium persona gating
def test_p12_returns_402(headers):
    files = {"images": ("a.jpg", b"\xff\xd8\xff", "image/jpeg")}
    r = requests.post(f"{API}/roast/generate", headers=headers,
                      data={"persona_ids": "persona_p12"}, files=files, timeout=30)
    assert r.status_code == 402
    assert "premium" in r.json()["detail"].lower()


# Catalog
def test_eleven_skus():
    packs = requests.get(f"{API}/payments/packs", timeout=15).json()["packs"]
    assert len(packs) == 11


# BYOK save -> me -> clear -> me
def test_byok_save_and_clear(headers):
    r = requests.post(f"{API}/voice-settings/keys", headers=headers,
                      json={"openai_key": "sk-test-fake", "elevenlabs_key": "el-fake"}, timeout=15)
    assert r.status_code == 200 and r.json()["has_byok_openai"] and r.json()["has_byok_elevenlabs"]
    me = requests.get(f"{API}/auth/me", headers=headers, timeout=15).json()
    assert me.get("has_byok_openai") is True
    assert "openai_key_encrypted" not in me or not me["openai_key_encrypted"] or me["openai_key_encrypted"] != "sk-test-fake"
    r = requests.delete(f"{API}/voice-settings/keys", headers=headers, timeout=15)
    assert r.status_code == 200
    me = requests.get(f"{API}/auth/me", headers=headers, timeout=15).json()
    assert me.get("has_byok_openai") is False and me.get("has_byok_elevenlabs") is False


def test_byok_empty_body_400(headers):
    r = requests.post(f"{API}/voice-settings/keys", headers=headers, json={}, timeout=15)
    assert r.status_code == 400
