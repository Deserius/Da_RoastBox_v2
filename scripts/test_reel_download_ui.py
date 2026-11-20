#!/usr/bin/env python3
"""Real browser + real API: saved reels, playback, creation and one-click MP4 save.

No writer/TTS call: reuses a generated show from the shared preview account.
The phone case strips auth headers to exercise the embedded-preview body tunnel.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roastbox_session import client, token

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from services.highlight_reel import FFMPEG

BASE = "http://127.0.0.1:3000"


def enter_studio(page):
    page.goto(BASE + "/studio", wait_until="domcontentloaded")
    page.get_by_test_id("skip-intro-btn").click()
    page.locator('[data-testid="roast-studio"], [data-testid="disclaimer-checkbox"]').first.wait_for(timeout=30000)
    consent = page.get_by_test_id("disclaimer-checkbox")
    # Direct authenticated navigation has the shared explicit consent gate.
    if consent.count() and consent.is_visible():
        consent.click()
    page.get_by_test_id("roast-studio").wait_for(timeout=30000)


def open_saved_show(page, roast_id):
    details = page.get_by_test_id("recent-shows")
    details.wait_for(timeout=30000)
    if details.get_attribute("open") is None:
        details.locator("summary").click()
    page.get_by_test_id(f"recent-reels-{roast_id}").click()


def playable(page):
    page.get_by_test_id("reel-ready").wait_for(timeout=180000)
    video = page.get_by_test_id("reel-video")
    video.wait_for(timeout=120000)
    page.wait_for_function("""() => {
      const v = document.querySelector('[data-testid="reel-video"]');
      return v && v.readyState >= 2 && v.videoWidth === 1080 && v.videoHeight === 1920 && v.duration > 5;
    }""", timeout=120000)
    video.evaluate("video => video.play()")
    page.wait_for_function("document.querySelector('[data-testid=\"reel-video\"]').currentTime > 0.3", timeout=15000)
    return video


def save_and_probe(page, button, width):
    with page.expect_download(timeout=120000) as info:
        page.get_by_test_id(button).click()
    download = info.value
    assert download.failure() is None, download.failure()
    assert download.suggested_filename.startswith("da-roastbox-") and download.suggested_filename.endswith(".mp4")
    saved = ROOT / ".cache" / f"reel-download-{width}.mp4"
    download.save_as(saved)
    data = saved.read_bytes()
    assert len(data) > 100000 and data[4:8] == b"ftyp"
    probe = subprocess.run([FFMPEG, "-hide_banner", "-i", str(saved)], capture_output=True, text=True).stderr
    assert "1080x1920" in probe and "h264" in probe.lower() and "Audio: aac" in probe, probe
    return hashlib.sha256(data).hexdigest(), download.suggested_filename


def exercise(browser, roast_id, session_token, width, height, *, tunnel=False, create=False):
    context = browser.new_context(viewport={"width": width, "height": height}, accept_downloads=True)
    context.add_init_script(f"localStorage.setItem('roastbox_token', {json.dumps(session_token)});")
    if tunnel:
        def strip_auth(route):
            headers = {key: value for key, value in route.request.headers.items()
                       if key.lower() not in {"authorization", "x-roastbox-session", "cookie"}}
            route.continue_(headers=headers)
        context.route("**/api/**", strip_auth)
    page = context.new_page()
    errors, creates, dispatches = [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: creates.append(request.url) if request.method == "POST" and request.url.endswith("/reel") else None)
    page.on("request", lambda request: dispatches.append(request.url) if request.url.endswith("/session/dispatch") else None)
    enter_studio(page)
    open_saved_show(page, roast_id)
    # The latest finished export opens automatically, without rerendering it.
    playable(page)
    assert not creates, "Restoring an export must never charge or regenerate"
    sha, name = save_and_probe(page, "reel-download-btn", width)
    page.get_by_test_id("reel-close-btn").click()
    sha2, name2 = save_and_probe(page, "reel-download-direct-btn", width)
    assert sha2 == sha and name2 == name, "The closed-player Download button must save the SAME reel"
    if create:
        page.get_by_test_id("reel-change-length").click()
        page.get_by_test_id("reel-60-btn").click()
        playable(page)  # completes and opens on its own; no additional View click
        assert creates, "Export button did not queue a reel"
        _, new_name = save_and_probe(page, "reel-download-btn", width)
        assert "60s" in new_name
        page.get_by_test_id("reel-close-btn").click()
    posts_before = len(creates)
    enter_studio(page)  # Full reload: brand splash repeats; exports remain saved.
    open_saved_show(page, roast_id)
    playable(page)
    assert len(creates) == posts_before, "A full reload must restore, not regenerate"
    bounds = page.get_by_test_id("reel-ready").bounding_box()
    assert bounds["x"] >= -1 and bounds["x"] + bounds["width"] <= width + 1, bounds
    assert bounds["y"] >= -1 and bounds["y"] + bounds["height"] <= height + 1, bounds
    assert not errors, errors
    if tunnel:
        assert dispatches, "Auth-stripping proxy case did not use the secure body tunnel"
    print(f"PASS: {width}x{height}{' auth-stripping preview' if tunnel else ''}: real video playback, identical modal/direct MP4 downloads, reload recovery" + (", export auto-opens" if create else ""), flush=True)
    context.close()


def main():
    with client() as api:
        history = api.get("/roast/history").json()["history"]
        roast = next(show for show in history if show.get("transcript"))
        # Ensure there is one real export to restore without a writer call.
        response = api.post(f"/roast/{roast['id']}/reel", json={"length": 30})
        response.raise_for_status()
        doc = response.json()
        if doc["status"] != "done":
            raise SystemExit("Run python scripts/test_reel_api.py 30 first to finish the initial export.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--mute-audio", "--disable-dev-shm-usage", "--autoplay-policy=no-user-gesture-required"])
        try:
            exercise(browser, roast["id"], token(), 1440, 900, create=True)
            exercise(browser, roast["id"], token(), 390, 844, tunnel=True)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
