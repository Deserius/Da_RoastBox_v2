#!/usr/bin/env python3
"""Optional live writer/TTS regression: a new 3-comic show, including Lil Glizzy.

Uses the explicitly enabled preview account and a synthetic image. Reuses a
previous successful run unless --force is passed. Provider calls may be billed
by the app operator; this is not an offline test.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_sample_roast import make_photo
from roastbox_session import client

CAST = ["persona_1", "persona_p8", "persona_4"]
NAME = "Lineup Regression Guest"


def main():
    started = time.monotonic()
    with client(timeout=240) as api:
        history = api.get("/roast/history").json()["history"]
        show = None if "--force" in sys.argv else next((item for item in history if item.get("subject_name") == NAME
                    and any(b.get("introduced_persona_id") for b in item.get("transcript", []))), None)
        if show is None:
            response = api.post("/roast/generate", files={"images": ("synthetic-guest.jpg", make_photo(), "image/jpeg")},
                data={"persona_ids": ",".join(CAST), "subject_name": NAME,
                      "user_context": "An adult friend arrived at a black-tie wedding in a neon tracksuit with a pet lizard on his shoulder and insisted on DJing the ceremony.",
                      "duration_minutes": "3", "roast_tier": "standard", "heat": "inferno", "adult_language": "true", "adult_subjects_confirmed": "true",
                      "off_limits": "family, health"})
            response.raise_for_status()
            result = response.json()
            show = {**result, "id": result["roast_id"]}
        transcript = show["transcript"]
        intros = [beat for beat in transcript if beat.get("stage") == "open_persona"]
        assert [beat["introduced_persona_id"] for beat in intros] == CAST
        assert {beat["persona_id"] for beat in intros} == {CAST[0]}
        assert [beat.get("stage") for beat in transcript[:2]] == ["open_host", "open_lineup"]
        assert transcript[5]["stage"] == "open_guest"
        assert all(beat.get("audio_url") for beat in transcript), "Do not ship a silent intro"
        assert all("came to cook" not in beat["text"].lower() for beat in intros)
        assert all(len(beat["text"].split()) >= 10 for beat in intros)
        assert all(not any(key.startswith("_") for key in beat) for beat in transcript), "Provisional stream metadata leaked"
        assert all(beat["type"] != "intro" for beat in transcript if not beat.get("stage")), "Early TTS overwrote a final joke type"
        for beat in intros:
            response = api.get(beat["audio_url"].removeprefix("/api"))
            assert response.status_code == 200 and len(response.content) > 1000
            print(beat["text"], flush=True)
        marker = Path(__file__).resolve().parents[1] / ".cache" / "lineup-test-roast-id"
        marker.parent.mkdir(exist_ok=True)
        marker.write_text(show["id"])
        print(f"PASS: live host-voiced lineup jokes + correct cast portraits + full voiced script ({len(transcript)} beats, {time.monotonic() - started:.1f}s)")


if __name__ == "__main__":
    main()
