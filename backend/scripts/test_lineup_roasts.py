#!/usr/bin/env python3
"""No providers: host-voiced one-joke intros, safe fallbacks and writer recovery."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routes.personas import all_personas, get_personas_by_ids
from services import roast_writer as w
from services.voice_orchestrator import voice_beats_progressive


def core(cast, count=10):
    return [{"persona_id": cast[i % len(cast)]["id"], "type": "joke",
             "text": f"Original test line {i} puts the punch at the end.", "laugh_after": "big"}
            for i in range(count)]


def check_intros():
    cast = get_personas_by_ids(["persona_1", "persona_p8", "persona_4"])
    jokes = {
        cast[0]["id"]: "That name sounds like a juice box that got recalled for excessive confidence.",
        cast[1]["id"]: "With a name like that, we know who's got stock in Oscar Mayer.",
        cast[2]["id"]: "His idea of crowd work is an email marked urgent.",
    }
    raw = json.dumps({"lineup_roasts": jokes, "script": core(cast)})
    beats = w._attach_lineup_roasts(w.parse_beats(raw, cast), raw, cast, adult=False, off_limits=None)
    final = w.finish_roast_script(beats, cast, "Test Guest", 10, adult=False)
    intros = [b for b in final if b.get("stage") == "open_persona"]
    assert len(intros) == len(cast)
    assert [b["introduced_persona_id"] for b in intros] == [p["id"] for p in cast]
    assert {b["persona_id"] for b in intros} == {cast[0]["id"]}, "One host announces the cast"
    for beat, persona in zip(intros, cast):
        assert persona["displayName"] in beat["text"] and jokes[persona["id"]] in beat["text"]
        assert beat["media"] == "/" + persona["image"]
        assert beat["reaction"] == "laugh" and "came to cook" not in beat["text"]
    assert "Oscar Mayer" in intros[1]["text"]
    assert [b["stage"] for b in final[:2]] == ["open_host", "open_lineup"]
    assert final[len(cast) + 2]["stage"] == "open_guest"
    assert final[-1]["show_signoff"] and "burnt crispy" in final[-1]["text"]
    assert not any(any(k.startswith("_") for k in beat) for beat in final)
    # Optional bad metadata cannot break a valid whole show; filter it and use
    # an original character-specific local joke, respecting clean/off-limits.
    bad = json.dumps({"lineup_roasts": {cast[1]["id"]: "That fucking sausage belongs on the forbidden topic."}, "script": core(cast)})
    parsed = w._attach_lineup_roasts(w.parse_beats(bad, cast), bad, cast, adult=False, off_limits="sausage")
    safe = w.finish_roast_script(parsed, cast, "Guest", 10, adult=False, off_limits="sausage")
    assert not any(w._CLEAN_WORDS.search(b["text"]) for b in safe)
    assert "sausage" not in safe[3]["text"].lower()
    for persona in all_personas():
        assert len(w._LINEUP_FALLBACKS.get(persona["id"], [])) >= 2, persona["id"]
        for joke in w._LINEUP_FALLBACKS[persona["id"]]:
            assert w._usable_lineup_joke(joke, persona, adult=False, off_limits=None), (persona["id"], joke)
    # Complete nested beats survive a missing outer JSON tail, including braces
    # and quotes inside spoken text. The old brace-depth salvage lost all of them.
    truncated = '{"script": [' + json.dumps(core(cast)[0]) + ',' + json.dumps({**core(cast)[1], "text": 'A {literal} brace and "quoted" joke.'}) + ',{"text":"unfinished'
    assert len(w._extract_candidates(truncated)) == 2
    state = {"pos": 0}
    prefix = '{"lineup_roasts": {"persona_1": "A separate intro joke."}, "script": [' + json.dumps(core(cast)[0])
    assert len(w._scan_objects(prefix, state)) == 1, "First beat must stream BEFORE the closing wrapper"
    assert len(w._scan_objects(prefix + ',' + json.dumps(core(cast)[1]) + ']}', state)) == 1
    print("PASS: one host, correct large portraits, one joke per comic, Oscar Mayer example, all 40 fallbacks, clean/boundaries and truncated JSON")


async def check_recovery():
    cast = get_personas_by_ids(["persona_1", "persona_p8"])
    valid = json.dumps({"lineup_roasts": {}, "script": core(cast)})
    class Fake:
        def __init__(self):
            self.chat = SimpleNamespace(completions=self)
            self.calls = []
        def create(self, **kwargs):
            self.calls.append(kwargs)
            content, reason = ("", "length") if len(self.calls) == 1 else (valid, "stop")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=reason)])
    fake = Fake()
    with patch.object(w, "ROAST_WRITER_PROVIDER", "openrouter"), patch.object(w, "OPENROUTER_API_KEY", "test-only"), \
         patch.object(w, "ROAST_WRITER_PROFILE", "free"), patch.object(w, "ROAST_FREE_WRITER_ONLY", True), \
         patch.object(w, "ROAST_WRITER_MODEL", "test:free"), patch.object(w, "ROAST_FREE_BACKUP_MODEL", ""), \
         patch.object(w, "ROAST_POLLINATIONS_FALLBACK", False), patch.object(w, "ROAST_ALLOW_PAID_WRITER_FALLBACK", False), \
         patch.object(w, "ROAST_WRITER_TRUNCATION_RETRY", True), patch.object(w, "_creative_client", return_value=fake):
        out = await w.write_script("offline", cast, [], [], expected_beats=10, adult=False)
    assert len(out) == 10 and len(fake.calls) == 2
    assert fake.calls[1]["max_tokens"] > fake.calls[0]["max_tokens"]
    assert {call["model"] for call in fake.calls} == {"test:free"}
    final_beat = {"persona_id": "p1", "text": "Same already-voiced line.", "type": "joke", "rapid_fire": True}
    async def early_voice():
        return {"persona_id": "p1", "text": final_beat["text"], "type": "intro", "_standalone": True,
                "audio_url": "/api/audio/test.mp3", "provider": "test"}
    started = {final_beat["text"]: asyncio.create_task(early_voice())}
    voiced, _ = await voice_beats_progressive(started, [final_beat], {}, byok_eleven=None, byok_openai=None, premium_voices=False)
    assert voiced[0]["type"] == "joke" and voiced[0]["rapid_fire"] and "_standalone" not in voiced[0]
    print("PASS: token-limit recovery stays on the configured free writer; early TTS cannot overwrite the final show script")


if __name__ == "__main__":
    check_intros()
    asyncio.run(check_recovery())
