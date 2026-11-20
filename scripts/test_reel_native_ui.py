#!/usr/bin/env python3
"""Real saved MP4 playback/download through native links; no LLM/TTS calls.

Default: shared test-preview account. --roast-id explicitly allows a maintainer
with local database access to inspect that show's actual owner account via a
fresh 10-minute diagnostic session, removed in finally. Never reads user tokens.
--rebuild is zero-charge only: requires an existing completed export.
"""
import argparse
import hashlib
import json
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from roastbox_session import client, token
from test_reel_download_ui import enter_studio, open_saved_show, playable, save_and_probe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roast-id")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    cleanup = None
    if args.roast_id:
        sys.path.insert(0, str(ROOT / "backend"))
        from config import MONGO_URL, DB_NAME
        from pymongo import MongoClient
        db = MongoClient(MONGO_URL)[DB_NAME]
        show = db.roasts.find_one({"id": args.roast_id}, {"_id": 0, "id": 1, "user_id": 1})
        if not show:
            raise SystemExit("Show not found")
        session = secrets.token_urlsafe(32)
        db.sessions.insert_one({"session_token": session, "user_id": show["user_id"],
             "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(), "purpose": "reel-diagnostic"})
        cleanup = lambda: db.sessions.delete_one({"session_token": session, "purpose": "reel-diagnostic"})
    else:
        session = token()
        with client() as api:
            show = next(item for item in api.get("/roast/history").json()["history"] if item.get("transcript"))
    try:
        with httpx.Client(base_url="http://127.0.0.1:8001/api", headers={"X-Roastbox-Session": session}, timeout=180) as api:
            response = api.get(f"/roast/{show['id']}/reels"); response.raise_for_status()
            done = [item for item in response.json()["reels"] if item["status"] == "done"]
            if not done:
                raise SystemExit("This show has no completed export. No render/charge was started.")
            reel = done[0]
            if args.rebuild:
                response = api.post(f"/roast/{show['id']}/reel", json={"length": reel["length"], "regenerate": True})
                response.raise_for_status(); reel = response.json()
                deadline = time.monotonic() + 180
                while reel["status"] in ("queued", "rendering") and time.monotonic() < deadline:
                    # Test-only bounded job polling, not dev-server startup polling.
                    time.sleep(1)
                    reel = api.get(f"/reels/{reel['id']}").json()
                assert reel["status"] == "done", reel
            response = api.get(reel["video_url"][4:]); response.raise_for_status()
            expected = hashlib.sha256(response.content).hexdigest()
            print(f"Actual saved export: {len(response.content):,} bytes; show={show['id']}; reel={reel['id']}", flush=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--mute-audio", "--disable-dev-shm-usage", "--autoplay-policy=no-user-gesture-required"])
            try:
                for width, height in ((1440, 900), (390, 844)):
                    context = browser.new_context(viewport={"width": width, "height": height}, accept_downloads=True)
                    context.add_init_script(f"localStorage.setItem('roastbox_token', {json.dumps(session)});")
                    dispatches, streams, errors = [], [], []
                    def proxy(route):
                        request = route.request
                        # Disallow AI-generation/payment calls from diagnostic sessions.
                        if request.method == "POST" and not request.url.endswith(("/session/dispatch", "/playback-report")):
                            route.abort(); return
                        if request.url.endswith("/session/dispatch"):
                            dispatches.append(request.url)
                        if "/file.mp4?" in request.url:
                            streams.append(request.headers.get("range", "download"))
                        headers = {k: v for k, v in request.headers.items() if k not in ("authorization", "x-roastbox-session", "cookie")}
                        route.continue_(headers=headers)
                    context.route("**/api/**", proxy)
                    def csp_document(route):
                        response = route.fetch()
                        # Deliberately disallow blob: media. The primary reel must
                        # work as a native, authenticated-by-capability HTTP stream.
                        route.fulfill(response=response, headers={**response.headers,
                            "Content-Security-Policy": "media-src http://127.0.0.1:3000/api/reels/; object-src 'none'"})
                    context.route("**/studio", csp_document)
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    enter_studio(page)
                    open_saved_show(page, show["id"])
                    video = playable(page)
                    assert "/file.mp4?grant=" in video.get_attribute("src") and not video.get_attribute("src").startswith("blob:")
                    assert video.evaluate("v => v.error?.code || 0") == 0
                    video.evaluate("v => { v.currentTime = Math.min(15, v.duration / 2); }")
                    page.wait_for_function("() => { const v = document.querySelector('[data-testid=\"reel-video\"]'); return v && !v.seeking && v.readyState >= 2 && v.currentTime > 10; }", timeout=30000)
                    actual, _ = save_and_probe(page, "reel-download-btn", width)
                    assert actual == expected
                    page.get_by_test_id("reel-close-btn").click()
                    actual, _ = save_and_probe(page, "reel-download-direct-btn", width)
                    assert actual == expected
                    assert dispatches and streams and not errors, errors
                    assert len(context.pages) == 1, "Download must not open a new tab"
                    print(f"PASS: {width}x{height}: actual-owner reel, blob media blocked, auth headers stripped, native playback/seek, identical modal+closed-player file downloads", flush=True)
                    context.close()
            finally:
                browser.close()
    finally:
        if cleanup:
            cleanup()


if __name__ == "__main__":
    main()
