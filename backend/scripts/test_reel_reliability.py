#!/usr/bin/env python3
"""Offline regressions for complete highlight selection and real MP4 downloads."""
import sys
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routes.reels import _public, _video_response
from routes import reels as routes
from services.highlight_reel import build_timeline, highlight_plan, intro_length, select_highlights


def main():
    # Announcements and the formal sign-off must not crowd out actual jokes.
    beats = [
        {"type": "intro", "stage": "open_persona", "text": "A comic's intro", "laugh_after": "big"},
        {"type": "punchline", "text": "A long but complete roast joke.", "laugh_after": "explosive"},
        {"type": "closer", "show_signoff": True, "text": "Thank you, everybody.", "laugh_after": "explosive"},
    ]
    durs = [10, 24, 3]
    assert select_highlights(beats, durs, 30, 2) == []
    picked, compact, scale, outro = highlight_plan(beats, durs, 30, 2)
    assert picked == [1] and scale < 1
    _, _, total = build_timeline([compact[i] for i in picked], [durs[i] for i in picked], 2,
                                  intro_seconds=intro_length(2) * scale, outro_seconds=outro)
    assert 24 < total <= 30, total
    # No mid-sentence hacks: impossible lengths remain actionable, not silently
    # truncated, and a dependent tag carries the preceding setup.
    try:
        highlight_plan([beats[1]], [100], 30, 2)
    except ValueError as error:
        assert "60s" in str(error)
    else:
        raise AssertionError("A 100s voice must not be cut into a fake 30s reel")
    conversation = [{"type": "joke", "text": "Setup", "laugh_after": "none"},
                    {"type": "tag", "text": "Payoff", "laugh_after": "explosive"}]
    assert select_highlights(conversation, [4, 2], 30, 2) == [0, 1]
    legacy_signoff = {"type": "closer", "text": "Da RoastBox, where people come to get roasted and leave burnt crispy."}
    assert select_highlights([legacy_signoff, conversation[0]], [2, 2], 30, 1) == [1]

    media = b"\x00\x00\x00\x18ftypisom" + bytes(range(256)) * 16
    filename = "da-roastbox-30s-test.mp4"
    full = _video_response(media, filename)
    assert full.status_code == 200 and full.body == media
    assert full.headers["content-type"] == "video/mp4"
    assert full.headers["accept-ranges"] == "bytes" and full.headers["content-disposition"].startswith("inline;")
    part = _video_response(media, filename, byte_range="bytes=0-31")
    assert part.status_code == 206 and part.body == media[:32]
    assert part.headers["content-range"] == f"bytes 0-31/{len(media)}"
    suffix = _video_response(media, filename, byte_range="bytes=-16")
    assert suffix.status_code == 206 and suffix.body == media[-16:]
    for bad in ("bytes=10000-", "bytes=9-1", "bytes=-0", "bytes=", "bytes=0-1,4-6", "elephants"):
        assert _video_response(media, filename, byte_range=bad).status_code == 416, bad
    attachment = _video_response(media, filename, download=True, byte_range="bytes=0-31")
    assert attachment.status_code == 200 and attachment.body == media
    assert attachment.headers["content-disposition"] == f'attachment; filename="{filename}"'
    head = _video_response(media, filename, head=True)
    assert head.body == b"" and head.headers["content-length"] == str(len(media))
    public = _public({"id": "test12345", "status": "done", "length": 30})
    assert public["download_url"].endswith("?download=true") and "30s" in public["filename"]
    assert _public({"id": "test12345", "status": "queued"})["video_url"] is None
    print("PASS: long-joke compact fallback, real punchlines (not bookends), setup/tag continuity, byte-range playback, attachment filenames and full downloads")


async def missing_file_rebuild():
    existing = {"id": "old-reel", "roast_id": "owned-show", "length": 30, "user_id": "owner", "status": "done"}
    roast_store = SimpleNamespace(find_one=AsyncMock(return_value={"id": "owned-show", "user_id": "owner"}))
    reel_store = SimpleNamespace(find_one=AsyncMock(side_effect=[existing, {"id": "old-reel"}]),
                                 update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
                                 insert_one=AsyncMock())
    user = SimpleNamespace(id="owner", credits=0, is_preview=False, lifetime_founder=False, plan_tier="free")
    render, charge = AsyncMock(), AsyncMock()
    with patch.object(routes, "roasts_collection", roast_store), patch.object(routes, "reels_collection", reel_store), \
         patch.object(routes, "get_blob", AsyncMock(return_value=None)), patch.object(routes, "_render_job", render), \
         patch.object(routes, "_charge_reel", charge):
        result = await routes.create_reel("owned-show", length=30, regenerate=False, current_user=user)
        if routes._tasks:
            await asyncio.gather(*list(routes._tasks))
    assert result["status"] == "queued" and result["id"] != existing["id"]
    charge.assert_not_awaited()
    inserted = reel_store.insert_one.call_args.args[0]
    assert inserted["credits_spent"] == 0, "Rebuilding a missing owned MP4 must not charge again"
    assert any(call.args[1].get("$set", {}).get("status") == "unavailable" for call in reel_store.update_one.call_args_list)
    print("PASS: missing saved MP4 automatically requeues for its owner with zero extra export charge")


if __name__ == "__main__":
    main()
    asyncio.run(missing_file_rebuild())
