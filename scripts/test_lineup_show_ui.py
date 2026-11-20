#!/usr/bin/env python3
"""Replay a saved show: one large correct portrait per host-voiced intro joke.

No writer/TTS calls. Run test_lineup_api.py once to create the synthetic show.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roastbox_session import client, token
from test_reel_download_ui import enter_studio

ROOT = Path(__file__).resolve().parents[1]


def exercise(browser, show, width, height):
    ctx = browser.new_context(viewport={"width": width, "height": height})
    ctx.add_init_script(f"localStorage.setItem('roastbox_token', {json.dumps(token())});")
    # Only the regression browser runs speech faster to avoid long timed waits;
    # the application and exported MP4 retain their normal voices/speaking rate.
    ctx.add_init_script("""(() => {
      const play = HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play = function (...args) { this.playbackRate = 3; return play.apply(this, args); };
    })();""")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    enter_studio(page)
    if width >= 1000:
        left, right = page.locator(".studio-side").bounding_box(), page.locator(".studio-roster").bounding_box()
        assert abs(left["width"] - right["width"]) < 1 and abs(left["y"] - right["y"]) < 1, (left, right)
        assert abs(left["height"] - right["height"]) < 1
        page.screenshot(path=str(ROOT / ".cache" / "studio-balanced.png"))
    page.get_by_test_id("recent-shows").locator("summary").click()
    page.get_by_test_id(f"recent-show-{show['id']}").get_by_role("button", name="▶ Watch again").click()
    page.get_by_test_id("theater-open-open_host").wait_for(timeout=30000)
    page.get_by_test_id("theater-open-open_lineup").wait_for(timeout=60000)
    for intro in (beat for beat in show["transcript"] if beat.get("stage") == "open_persona"):
        pid = intro["introduced_persona_id"]
        card = page.get_by_test_id(f"theater-open-persona-{pid}")
        card.wait_for(timeout=60000)
        portrait = card.get_by_test_id("theater-open-portrait")
        assert portrait.get_attribute("src") == intro["media"]
        assert portrait.evaluate("img => img.complete && img.naturalWidth > 0")
        assert page.get_by_test_id("theater-open-portrait").count() == 1, "One comic at a time"
        caption = card.get_by_test_id("theater-lineup-roast")
        assert caption.get_attribute("aria-label") == intro["text"]
        assert "came to cook" not in intro["text"].lower()
        bounds = portrait.bounding_box()
        assert bounds["height"] > (240 if width >= 1000 else 200), bounds
        assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width + 1
        if pid == "persona_p8":
            page.screenshot(path=str(ROOT / ".cache" / f"lineup-glizzy-{width}.png"))
    page.get_by_test_id("theater-open-guest").wait_for(timeout=60000)
    expect(page.get_by_test_id("theater-open-guest-photo")).to_be_visible()
    page.get_by_test_id("theater-stage").wait_for(timeout=60000)
    page.get_by_test_id("theater-close-btn").click()
    assert not errors, errors
    print(f"PASS: {width}x{height}: host intro → lineup → three correct large portraits with one-joke captions → guest → roast", flush=True)
    ctx.close()


def main():
    marker = ROOT / ".cache" / "lineup-test-roast-id"
    if not marker.exists():
        raise SystemExit("Run python scripts/test_lineup_api.py once first.")
    with client() as api:
        history = api.get("/roast/history").json()["history"]
        show = next(item for item in history if item["id"] == marker.read_text().strip())
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--mute-audio", "--disable-dev-shm-usage", "--autoplay-policy=no-user-gesture-required"])
        try:
            exercise(browser, show, 1440, 900)
            exercise(browser, show, 390, 844)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
