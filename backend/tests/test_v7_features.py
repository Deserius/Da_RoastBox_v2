"""v7: Roast Battle, share links, HD reels, voice previews, script parser metadata. One battle LLM call at most."""
import random
import time
import uuid
import pytest
import requests

from tests._env import API
from services.roast_writer import parse_beats, SYSTEM_PROMPT, battle_beats
from routes.battle import score_battle
from services.highlight_reel import build_timeline, select_highlights

PERSONAS = [{"id": "persona_21"}, {"id": "persona_22"}]


def _login(prefix="TEST_v7"):
    r = requests.post(f"{API}/auth/dev-login", json={"email": f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"}, timeout=15)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


class TestWriterUnit:
    def test_original_prompt_restored(self):
        assert SYSTEM_PROMPT.startswith('You are the HEAD WRITER for "Da RoastBox!" — an 18+ adult-entertainment')
        assert "UNCENSORED 18+ adult-only app" in SYSTEM_PROMPT and "PERFORMANCE METADATA" in SYSTEM_PROMPT

    def test_parse_metadata_defaults(self):
        raw = '{"script":[{"persona_id":"persona_21","type":"tag","text":"hi","emotion":"WHISPER","reaction":"ooh","laugh_after":"big"},' \
              '{"persona_id":"bogus","type":"weird","text":"bye","emotion":"nope","reaction":"x"}]}'
        beats = parse_beats(raw, PERSONAS)
        assert beats[0]["type"] == "intro" or beats[0]["type"] == "tag"
        assert beats[0]["emotion"] == "whisper" and beats[0]["reaction"] == "ooh"
        assert beats[1]["persona_id"] == "persona_21" and beats[1]["emotion"] == "cocky"
        assert beats[-1]["type"] == "closer" and beats[-1]["laugh_after"] == "explosive"

    def test_battle_scoring_deterministic(self):
        beats = [{"persona_id": "a", "laugh_after": "explosive", "reaction": "ooh"},
                 {"persona_id": "b", "laugh_after": "small", "reaction": "groan"}]
        res = score_battle(beats, "a", "b", random.Random(1))
        assert res["winner"] == "a" and set(res["scores"]) == {"a", "b"}
        assert battle_beats(4) == 20

    def test_reel_timeline_monotonic(self):
        beats = [{"persona_id": "a", "type": "intro", "laugh_after": "small", "reaction": "cheer"},
                 {"persona_id": "a", "type": "punchline", "laugh_after": "big", "reaction": "laugh"},
                 {"persona_id": "a", "type": "tag", "laugh_after": "medium", "reaction": "ooh"}]
        starts, events, total = build_timeline(beats, [2.0, 3.0, 1.0], 1)
        assert starts == sorted(starts) and total > starts[-1] + 1.0
        assert any(bank == "ooh" for _, bank, _ in events)

    def test_highlights_fit_length(self):
        beats = [{"persona_id": "a", "type": "intro", "laugh_after": "small"}] + [
            {"persona_id": "a", "type": "punchline", "laugh_after": lvl, "reaction": "laugh"}
            for lvl in ["small", "explosive", "medium", "big", "small", "big", "explosive", "medium"]]
        durs = [4.0] + [5.0] * 8
        for limit in (30, 60):
            picked = select_highlights(beats, durs, limit, 2)
            _, _, total = build_timeline([beats[i] for i in picked], [durs[i] for i in picked], 2)
            assert picked == sorted(picked) and 0 not in picked and total <= limit
        assert 2 in select_highlights(beats, durs, 30, 2)  # an explosive beat makes the 30s cut


class TestApi:
    def test_battle_locked_402(self):
        r = requests.post(f"{API}/battle/generate", headers=_login(),
                          data={"persona_a": "persona_21", "persona_b": "persona_22"}, timeout=20)
        assert r.status_code == 402

    def test_battle_access_endpoint(self):
        d = requests.get(f"{API}/battle/access", headers=_login(), timeout=15).json()
        assert d["unlocked"] is False and d["base_cost"] == 5

    def test_share_unknown_404(self):
        assert requests.get(f"{API}/share/does-not-exist", timeout=15).status_code == 404

    def test_share_requires_owner(self):
        assert requests.post(f"{API}/roast/nope/share", headers=_login(), timeout=15).status_code == 404

    def test_reel_requires_owner(self):
        assert requests.post(f"{API}/roast/nope/reel", headers=_login(), timeout=15).status_code == 404
        assert requests.get(f"{API}/reels/nope/video.mp4", timeout=15).status_code == 404

    def test_voice_preview_cached(self):
        r1 = requests.get(f"{API}/personas/persona_21/voice-preview", timeout=60)
        assert r1.status_code == 200
        t = time.time()
        r2 = requests.get(f"{API}/personas/persona_21/voice-preview", timeout=15)
        assert r2.json() == r1.json() and time.time() - t < 3
        audio = requests.get(f"{API.rsplit('/api', 1)[0]}{r1.json()['audio_url']}", timeout=30)
        assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg" and len(audio.content) > 5000

    def test_personas_hide_voice_internals(self):
        p = requests.get(f"{API}/personas", timeout=15).json()["personas"][0]
        assert "voice_direction" not in p and "elevenlabs" not in p

    def test_crowd_sfx_served(self):
        base = API.rsplit("/api", 1)[0]
        for name in ("laugh_big_1", "ooh_1", "room_tone", "explosive_1"):
            r = requests.get(f"{base}/assets/sfx/crowd/{name}.mp3", timeout=15)
            assert r.status_code == 200 and len(r.content) > 5000, name
