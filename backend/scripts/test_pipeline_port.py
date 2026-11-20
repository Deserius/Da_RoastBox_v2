"""Regression tests for the reference-project pipeline port.

These lock down behaviour taken from the upstream Da RoastBox audit:

* intensity vocabulary (light / savage / nuclear / atomic) folding onto heat
* the extended crowd-reaction ladder (shock / gasp / hype / applause) mapping
  onto the volume steps and crowd samples the existing player understands
* the LIVE PANEL and PLANT-AND-PAY-OFF show structure reaching both prompts
* per-persona ElevenLabs pace hints
* the `reaction` beat type being accepted
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "roastbox_pipeline_test")
os.environ.setdefault("JWT_SECRET", "0123456789abcdef0123456789abcdef")
os.environ["APP_ENV"] = "development"

from services import roast_writer as w  # noqa: E402
from services.elevenlabs_service import PERSONA_RATE  # noqa: E402


def check(name, condition, detail=""):
    if not condition:
        raise AssertionError(f"{name} failed{': ' + detail if detail else ''}")
    print(f"PASS: {name}")


PERSONAS = [{"id": "persona_1", "name": "Host", "displayName": "Host"},
            {"id": "persona_2", "name": "Second", "displayName": "Second"},
            {"id": "persona_3", "name": "Third", "displayName": "Third"}]


def test_intensity_aliases():
    expected = {"light": "mild", "savage": "hot", "nuclear": "fire", "atomic": "inferno"}
    for alias, heat in expected.items():
        check(f"intensity '{alias}' folds onto '{heat}'", w.normalize_heat(alias) == heat,
              w.normalize_heat(alias))
    # Existing vocabulary must be untouched.
    for heat in w.HEAT_LEVELS:
        check(f"existing heat '{heat}' still valid", w.normalize_heat(heat) == heat)
    check("unknown intensity falls back to hot", w.normalize_heat("bogus") == "hot")
    check("empty intensity falls back to hot", w.normalize_heat(None) == "hot")
    check("intensity is case/space tolerant", w.normalize_heat("  ATOMIC  ") == "inferno")


def test_reaction_ladder():
    # Volume steps stay on the ladder the crowd engine already renders.
    check("shock renders at big volume", w.LAUGH_VOLUME["shock"] == "big")
    check("gasp renders at medium volume", w.LAUGH_VOLUME["gasp"] == "medium")
    check("hype renders at explosive volume", w.LAUGH_VOLUME["hype"] == "explosive")
    check("applause renders at big volume", w.LAUGH_VOLUME["applause"] == "big")

    # Each flavour picks a real crowd sample, so audio actually plays.
    for flavour in ("shock", "gasp"):
        check(f"'{flavour}' triggers the ooh sample", w.LAUGH_REACTION[flavour] == "ooh")
    for flavour in ("hype", "applause"):
        check(f"'{flavour}' triggers the cheer sample", w.LAUGH_REACTION[flavour] == "cheer")

    # A flavour must never leak into laugh_after: the player, the battle
    # scoreboard and the crowd engine only understand the five-step ladder, so
    # the richer flavour is carried separately.
    for flavour, ladder, sample in (("shock", "big", "ooh"), ("gasp", "medium", "ooh"),
                                    ("hype", "explosive", "cheer"), ("applause", "big", "cheer")):
        level, got_sample, got_flavour = w._normalize_reaction(flavour, None)
        check(f"'{flavour}' keeps a ladder value in laugh_after", level == ladder, level)
        check(f"'{flavour}' is preserved as flavour", got_flavour == flavour, got_flavour)
        check(f"'{flavour}' picks a crowd sample", got_sample == sample, got_sample)
        check(f"'{flavour}' never leaks a non-ladder value",
              level in {"none", "small", "medium", "big", "explosive"}, level)

    # An explicit reaction from the writer wins over the derived sample.
    level, sample, _ = w._normalize_reaction("hype", "groan")
    check("explicit reaction is preserved", sample == "groan", sample)
    # Junk must not crash or leak through.
    level, sample, flavour = w._normalize_reaction("nonsense", "nonsense")
    check("unknown values fall back safely",
          (level, sample) == ("small", "laugh"), f"{level},{sample}")


def test_parser_carries_reactions():
    import json
    script = {"script": [
        {"persona_id": "persona_1", "type": "intro", "text": "Welcome to the show tonight.", "laugh_after": "hype"},
        {"persona_id": "persona_2", "type": "reaction", "text": "Oh he did NOT just say that.", "laugh_after": "shock"},
        {"persona_id": "persona_3", "type": "punchline", "text": "Your outfit is a cry for help.", "laugh_after": "gasp"},
        {"persona_id": "persona_1", "type": "callback", "text": "Remember the outfit? Still screaming.", "laugh_after": "applause"},
        {"persona_id": "persona_2", "type": "closer", "text": "Goodnight and please update the wardrobe.", "laugh_after": "explosive"},
    ]}
    beats = w.parse_beats(json.dumps(script), PERSONAS, 1)
    check("reaction beats survive parsing", any(b["type"] == "reaction" for b in beats),
          str([b["type"] for b in beats]))
    check("every flavoured beat keeps its flavour",
          [b["laugh_flavour"] for b in beats] == ["hype", "shock", "gasp", "applause", "explosive"],
          str([b["laugh_flavour"] for b in beats]))
    ladder = {"none", "small", "medium", "big", "explosive"}
    check("laugh_after stays on the ladder the player scores",
          all(b["laugh_after"] in ladder for b in beats),
          str([b["laugh_after"] for b in beats]))
    check("flavours fold onto the right ladder steps",
          [b["laugh_after"] for b in beats] == ["explosive", "big", "medium", "big", "explosive"],
          str([b["laugh_after"] for b in beats]))
    check("flavours map to playable crowd samples",
          [b["reaction"] for b in beats[1:4]] == ["ooh", "ooh", "cheer"],
          str([b["reaction"] for b in beats[1:4]]))


def test_prompts_carry_show_structure():
    for token in ("shock", "gasp", "hype", "applause", "CROWD REACTION MARKING"):
        check(f"system prompt documents '{token}'", token in w.SYSTEM_PROMPT)

    prompt = w.build_roast_prompt(PERSONAS, "Dave", "loves golf", 5, False, False,
                                  heat="atomic", adult=True, n_images=1)
    check("roast prompt explains live panel interaction", "LIVE PANEL" in prompt)
    check("roast prompt asks for a callback payoff", "CALL" in prompt.upper())
    check("atomic heat reaches the prompt as INFERNO", "INFERNO" in prompt)
    check("turn plan still lists every selected comic",
          all(p["id"] in prompt for p in PERSONAS))


def test_voice_pace_hints():
    check("pace hints cover the persona set", len(PERSONA_RATE) >= 25, str(len(PERSONA_RATE)))
    check("a slow persona is slower than neutral", PERSONA_RATE["persona_p4"] < 1.0)
    check("a fast persona is faster than neutral", PERSONA_RATE["persona_8"] > 1.0)
    # Distinct tempos are the point: personas must not all share one rate.
    check("pace hints actually vary", len(set(PERSONA_RATE.values())) >= 5,
          str(sorted(set(PERSONA_RATE.values()))))


test_intensity_aliases()
test_reaction_ladder()
test_parser_carries_reactions()
test_prompts_carry_show_structure()
test_voice_pace_hints()
print("PASS: reference pipeline behaviour is ported and wired")
