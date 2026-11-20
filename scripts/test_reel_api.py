#!/usr/bin/env python3
"""End-to-end reel check against the live API: queue, poll, download, probe.

Usage: python scripts/test_reel_api.py [length]   (default 30)
Uses the preview session so no real credits are needed.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roastbox_session import client as session_client, token

BASE = "http://127.0.0.1:8001/api"
BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
from services.highlight_reel import FFMPEG  # noqa: E402


def probe(data: bytes) -> str:
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", "pipe:0"], input=data, capture_output=True)
    return p.stderr.decode(errors="ignore")


def main() -> int:
    length = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    with session_client(BASE, timeout=600.0) as c:
        history = c.get("/roast/history").json().get("history", [])
        roast = next((h for h in history if h.get("transcript")), None)
        if not roast:
            raise SystemExit("no roast in history — generate one first")
        print(f"roast {roast['id']}: {len(roast['transcript'])} beats, images={roast.get('image_count')}")
        res = c.post(f"/roast/{roast['id']}/reel", json={"length": length})
        print("queue:", res.status_code, res.text[:200])
        res.raise_for_status()
        reel = res.json()
        deadline = time.time() + 600
        while time.time() < deadline:
            doc = c.get(f"/reels/{reel['id']}").json()
            print("  status:", doc["status"], doc.get("error") or "")
            if doc["status"] in ("done", "failed"):
                break
            time.sleep(5)
        if doc["status"] != "done":
            raise SystemExit(f"REEL FAILED: {doc.get('error')}")
        response = c.get(f"/reels/{reel['id']}/video.mp4")
        response.raise_for_status()
        video = response.content
        assert response.headers["content-type"].startswith("video/mp4")
        saved = c.get(f"/roast/{roast['id']}/reels").json()["reels"]
        assert any(item["id"] == reel["id"] and item["status"] == "done" for item in saved)
        cached = c.post(f"/roast/{roast['id']}/reel", json={"length": length})
        cached.raise_for_status()
        assert cached.json()["id"] == reel["id"], "duplicate clicks must reuse the finished reel"
        part = c.get(f"/reels/{reel['id']}/video.mp4", headers={"Range": "bytes=0-1023"})
        assert part.status_code == 206 and part.content == video[:1024]
        assert part.headers["content-range"] == f"bytes 0-1023/{len(video)}"
        attachment = c.get(f"/reels/{reel['id']}/video.mp4?download=true")
        assert attachment.status_code == 200 and "attachment;" in attachment.headers["content-disposition"]
        assert doc["filename"] in attachment.headers["content-disposition"]
        assert hashlib.sha256(attachment.content).digest() == hashlib.sha256(video).digest()
        tunneled = c.post("/session/dispatch", data={"token": token(), "method": "GET", "kind": "none",
                           "path": f"/api/reels/{reel['id']}/video.mp4?download=true"})
        assert tunneled.status_code == 200 and tunneled.content == video, "embedded-preview media transport failed"
        assert "attachment;" in tunneled.headers["content-disposition"]
        denied = httpx.get(f"{BASE}/reels/{reel['id']}/video.mp4", timeout=20)
        assert denied.status_code == 401, "private MP4 must require authentication"
        info = probe(video)
        print(f"video {len(video)} bytes")
        for line in info.splitlines():
            if "Duration" in line or "Stream #" in line:
                print("   ", line.strip())
        assert "1080x1920" in info, "not 1080x1920"
        assert "h264" in info.lower(), "not h264"
        assert "Audio: aac" in info, "no aac audio"
        # Long enough to be a real reel, not a single frame.
        dur = float(info.split("Duration: ")[1].split(",")[0].split(":")[2])
        print(f"duration {dur:.2f}s")
        assert dur >= 8, "reel too short"
    print(f"PASS: API reel {length}s renders, restores, seeks, plays and downloads (normal + tunneled auth) ({len(video)} bytes, {dur:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
