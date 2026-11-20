#!/usr/bin/env python3
"""End-to-end check of the staged show opening: host welcome, one card per comic, then the hot seat."""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_helpers import accept_adult_consent

FIXTURE = Path("/tmp/show_open_subject.jpg")


def make_photo():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (700, 700), (110, 150, 190))
    d = ImageDraw.Draw(img)
    d.ellipse((200, 140, 500, 440), fill=(235, 205, 175))
    d.rectangle((160, 470, 540, 680), fill=(190, 70, 70))
    d.rectangle((215, 175, 485, 215), fill=(40, 40, 40))
    img.save(FIXTURE, "JPEG", quality=85)


def run():
    make_photo()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--mute-audio", "--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto("http://127.0.0.1:3000")
        page.get_by_test_id("skip-intro-btn").click()
        accept_adult_consent(page)
        page.get_by_test_id("preview-login-btn").click()
        page.wait_for_url("**/studio")
        page.wait_for_selector('[data-testid="roast-studio"]')
        token = page.evaluate("() => window.localStorage.getItem('roastbox_token')")
        assert token, "no preview session token in localStorage"
        # Generate through the API with the browser's own session, then replay it
        # from Recent shows so the theater is exercised without a second long wait.
        import requests
        files = {"images": ("subject.jpg", FIXTURE.read_bytes(), "image/jpeg")}
        data = {"persona_ids": "persona_1,persona_2", "subject_name": "Opening Night Guest",
                "user_context": "Showed up to a black-tie event in a neon tracksuit with a pet lizard.",
                "duration_minutes": "3", "roast_tier": "standard", "adult_language": "false", "heat": "hot"}
        # Free-tier models are flaky; a couple of retries keeps this a UI check, not a provider check.
        resp = None
        for attempt in range(3):
            resp = requests.post("http://127.0.0.1:3000/api/roast/generate", headers={"X-Roastbox-Session": token},
                                 data=data, files=files, timeout=600)
            if resp.status_code == 200:
                break
        assert resp.status_code == 200, f"generation failed after retries: {resp.status_code} {resp.text[:200]}"
        stages = [b.get("stage") for b in resp.json()["transcript"]]
        assert stages[:5] == ["open_host", "open_lineup", "open_persona", "open_persona", "open_guest"], stages
        page.reload()
        page.wait_for_selector('[data-testid="roast-studio"]')
        page.get_by_test_id("recent-shows").click()
        page.get_by_role("button", name="▶ Watch again").first.click()
        expect(page.get_by_test_id("roast-theater")).to_be_visible()

        seen = []

        def note(name, locator):
            locator.wait_for(state="visible", timeout=90000)
            seen.append(name)

        note("host", page.get_by_test_id("theater-open-open_host"))
        assert "flame thrower" in page.get_by_test_id("theater-open-open_host").inner_text()
        note("lineup", page.get_by_test_id("theater-open-open_lineup"))
        assert "line up" in page.get_by_test_id("theater-open-open_lineup").inner_text()
        # One large portrait at a time, one per selected comic.
        for persona_id in ("persona_1", "persona_2"):
            card = page.get_by_test_id(f"theater-open-persona-{persona_id}")
            note(f"persona:{persona_id}", card)
        portrait = page.get_by_test_id("theater-open-portrait")
        box = portrait.bounding_box()
        assert box and box["height"] > 240, f"portrait too small: {box}"
        assert portrait.evaluate("el => el.naturalWidth") > 0, "portrait image failed to load"
        note("guest", page.get_by_test_id("theater-open-guest"))
        guest_photo = page.get_by_test_id("theater-open-guest-photo")
        assert guest_photo.evaluate("el => el.naturalWidth") > 0, "guest photo failed to load"
        # After the opening the normal show stage takes over.
        page.wait_for_selector('[data-testid="theater-stage"]', timeout=120000)
        print("PASS: staged opening shows host welcome, one large comic card each, then the hot seat:", ", ".join(seen))
        browser.close()


if __name__ == "__main__":
    run()
