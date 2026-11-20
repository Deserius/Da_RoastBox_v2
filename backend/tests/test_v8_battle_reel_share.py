"""v8 regression: Battle validation, HD Reel ownership/status/video/refund, public share pages, diagnostics, crowd SFX.

Uses roasts already generated via the UI (no LLM calls here). Looks up the newest roast + battle of
TEST_t1_battle@roastbox.com; tests depending on them are skipped if absent.
"""
import time
import uuid
import os
from pathlib import Path
from datetime import datetime, timezone

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

from tests._env import API, BASE_URL

# Use this checkout's configuration rather than the original Emergent /app mount.
ENV = {**dotenv_values(Path(__file__).resolve().parents[1] / ".env"), **os.environ}
DB = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
OWNER_EMAIL = "TEST_t1_battle@roastbox.com"
CROWD = ["applause_outro", "chuckle_1", "chuckle_2", "explosive_1", "explosive_2", "groan_1", "intro_cheer",
         "laugh_big_1", "laugh_big_2", "laugh_med_1", "laugh_med_2", "ooh_1", "ooh_2", "room_tone"]


def _login(email):
    r = requests.post(f"{API}/auth/dev-login", json={"email": email})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


@pytest.fixture(scope="module")
def owner():
    return _login(OWNER_EMAIL)


@pytest.fixture(scope="module")
def other():
    return _login(f"TEST_v8_other_{uuid.uuid4().hex[:6]}@roastbox.com")


@pytest.fixture(scope="module")
def owner_doc():
    return DB.users.find_one({"email": OWNER_EMAIL}, {"_id": 0})


def _latest(user_id, mode):
    q = {"user_id": user_id, "mode": "battle"} if mode == "battle" else {"user_id": user_id, "mode": {"$ne": "battle"}}
    q["id"] = {"$not": {"$regex": "^TEST_"}}
    return DB.roasts.find_one(q, {"_id": 0}, sort=[("created_at", -1)])


@pytest.fixture(scope="module")
def studio_roast(owner, owner_doc):
    r = _latest(owner_doc["id"], "roast")
    if not r:
        pytest.skip("no studio roast generated")
    return r


@pytest.fixture(scope="module")
def battle_roast(owner, owner_doc):
    r = _latest(owner_doc["id"], "battle")
    if not r:
        pytest.skip("no battle generated")
    return r


# --- Battle validation (no LLM) ---
class TestBattleValidation:
    def test_same_fighter_400(self, owner):
        r = requests.post(f"{API}/battle/generate", headers=owner, data={"persona_a": "persona_22", "persona_b": "persona_22"})
        assert r.status_code == 400

    def test_unknown_fighter_400(self, owner):
        r = requests.post(f"{API}/battle/generate", headers=owner, data={"persona_a": "persona_22", "persona_b": "nope"})
        assert r.status_code == 400

    def test_access_unlocked(self, owner):
        r = requests.get(f"{API}/battle/access", headers=owner)
        assert r.status_code == 200 and r.json()["unlocked"] is True

    def test_battle_record_shape(self, battle_roast):
        res = battle_roast["battle"]
        assert set(res["scores"]) == set(battle_roast["persona_ids"])
        assert res["winner"] == max(res["scores"], key=res["scores"].get)
        assert battle_roast["credits_spent"] == 5
        assert all("emotion" in b and "reaction" in b for b in battle_roast["transcript"])


# --- HD Reel ---
class TestReel:
    def test_other_user_reel_404(self, other, studio_roast):
        r = requests.post(f"{API}/roast/{studio_roast['id']}/reel", headers=other)
        assert r.status_code == 404

    def test_reel_status_and_video(self, owner, other, studio_roast):
        reel = DB.reels.find_one({"roast_id": studio_roast["id"], "status": "done"}, {"_id": 0})
        if not reel:
            pytest.skip("no finished reel")
        s = requests.get(f"{API}/reels/{reel['id']}", headers=owner)
        assert s.status_code == 200 and s.json()["status"] == "done"
        assert s.json()["video_url"] == f"/api/reels/{reel['id']}/video.mp4"
        assert requests.get(f"{API}/reels/{reel['id']}", headers=other).status_code == 404
        v = requests.get(f"{BASE_URL}{s.json()['video_url']}")
        assert v.status_code == 200 and v.headers["content-type"].startswith("video/mp4")
        assert len(v.content) > 100_000 and v.content[4:8] == b"ftyp"
        d = requests.get(f"{BASE_URL}{s.json()['video_url']}?download=true")
        assert "attachment" in d.headers.get("content-disposition", "")

    def test_reel_repost_idempotent_no_charge(self, owner, studio_roast, owner_doc):
        before = DB.users.find_one({"id": owner_doc["id"]})["credits"]
        r = requests.post(f"{API}/roast/{studio_roast['id']}/reel", headers=owner)
        assert r.status_code == 200 and r.json()["status"] in ("queued", "rendering", "done")
        assert DB.users.find_one({"id": owner_doc["id"]})["credits"] == before

    def test_reel_unknown_404(self, owner):
        assert requests.get(f"{API}/reels/does-not-exist", headers=owner).status_code == 404
        assert requests.get(f"{API}/reels/does-not-exist/video.mp4").status_code == 404

    def test_reel_failure_refunds_exactly_once(self, owner, owner_doc):
        # Broken battle doc (scores reference personas not in catalog) -> render raises -> refund.
        rid = f"TEST_broken_{uuid.uuid4().hex[:8]}"
        DB.roasts.insert_one({"id": rid, "user_id": owner_doc["id"], "mode": "battle", "persona_ids": [],
                              "transcript": [{"persona_id": "x", "type": "intro", "text": "hi there", "laugh_after": "none"}],
                              "battle": {"scores": {"ghost_a": 1, "ghost_b": 2}, "winner": "ghost_b"},
                              "created_at": datetime.now(timezone.utc).isoformat()})
        try:
            before = DB.users.find_one({"id": owner_doc["id"]})["credits"]
            r = requests.post(f"{API}/roast/{rid}/reel", headers=owner)
            assert r.status_code == 200
            reel_id = r.json()["id"]
            status = None
            for _ in range(30):
                status = requests.get(f"{API}/reels/{reel_id}", headers=owner).json()
                if status["status"] in ("done", "failed"):
                    break
                time.sleep(2)
            assert status["status"] == "failed"
            after = DB.users.find_one({"id": owner_doc["id"]})["credits"]
            assert after == before, f"refund mismatch: before={before} after={after}"
        finally:
            DB.roasts.delete_one({"id": rid})
            DB.reels.delete_many({"roast_id": rid})


# --- Public share ---
class TestShare:
    def test_studio_share_public(self, owner, studio_roast):
        r = requests.post(f"{API}/roast/{studio_roast['id']}/share", headers=owner)
        assert r.status_code == 200
        sid = r.json()["share_id"]
        assert r.json()["share_path"] == f"/r/{sid}"
        p = requests.get(f"{API}/share/{sid}")
        assert p.status_code == 200
        data = p.json()
        assert data["mode"] != "battle" and len(data["transcript"]) == len(studio_roast["transcript"])
        assert "user_id" not in data and "user_context" not in data
        assert all("emotion" in b for b in data["transcript"])

    def test_battle_share_public_has_winner(self, owner, battle_roast):
        sid = requests.post(f"{API}/roast/{battle_roast['id']}/share", headers=owner).json()["share_id"]
        data = requests.get(f"{API}/share/{sid}").json()
        assert data["mode"] == "battle" and data["battle"]["winner"] in data["battle"]["scores"]
        assert len(data["personas"]) == 2

    def test_share_idempotent(self, owner, studio_roast):
        a = requests.post(f"{API}/roast/{studio_roast['id']}/share", headers=owner).json()["share_id"]
        b = requests.post(f"{API}/roast/{studio_roast['id']}/share", headers=owner).json()["share_id"]
        assert a == b


# --- Diagnostics + crowd SFX ---
def test_deep_diagnostics_storage(owner):
    r = requests.get(f"{API}/diagnostics?deep=true", headers=owner)
    assert r.status_code == 200
    assert "storage" in r.text.lower() and "ok" in r.text.lower()


@pytest.mark.parametrize("name", CROWD)
def test_crowd_sfx(name):
    r = requests.get(f"{BASE_URL}/assets/sfx/crowd/{name}.mp3")
    assert r.status_code == 200 and len(r.content) > 1000
    assert "html" not in r.headers.get("content-type", "")
