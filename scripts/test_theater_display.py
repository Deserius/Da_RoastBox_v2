#!/usr/bin/env python3
"""Exercise Studio, Battle and shared-show playback without calling paid providers.

Run with the local preview/API already running. All generated shows, photos and
voice clips are intercepted fixtures; preview login uses the local test account.
"""
from __future__ import annotations

from ui_helpers import accept_adult_consent, accept_adult_consent_async

import io
import json
import math
import os
import struct
import time
import wave
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
APP = os.environ.get("ROASTBOX_TEST_ORIGIN", "http://127.0.0.1:3000").rstrip("/")
OUT = Path("/home/user/.cache/da-roastbox")
OUT.mkdir(parents=True, exist_ok=True)


def photo(name):
    image = Image.open(ROOT / "frontend/public/assets/personas" / name).convert("RGB")
    out = io.BytesIO()
    image.save(out, "JPEG", quality=90)
    return out.getvalue()


def tone(seconds=2.5):
    data = io.BytesIO()
    with wave.open(data, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        samples = (struct.pack("<h", int(900 * math.sin(2 * math.pi * 250 * i / 16000)))
                   for i in range(int(16000 * seconds)))
        wav.writeframes(b"".join(samples))
    return data.getvalue()


PHOTOS = [photo("persona_1.webp"), photo("persona_2.webp")]
VOICE = tone()
FIRST = "FIRSTCAPTION Here is the first roaster speaking one joke at a time for the audience."
SECOND = "SECONDCAPTION A different roaster takes the microphone with a completely new joke."
THIRD = "THIRDCAPTION " + ("This deliberately long caption keeps wrapping neatly as the current roaster continues speaking. " * 14)
FOURTH = "FOURTHCAPTION Silent fallback stays readable."
BEATS = [
    {"persona_id": "persona_1", "text": FIRST, "audio_url": "/api/testmedia/voice-1", "image_index": 0, "laugh_after": "none", "reaction": "laugh"},
    {"persona_id": "persona_2", "text": SECOND, "audio_url": "/api/testmedia/voice-2", "image_index": 1, "laugh_after": "none", "reaction": "laugh", "pause_before_ms": 1000},
    {"persona_id": "persona_1", "text": THIRD, "audio_url": "/api/testmedia/voice-3", "image_index": 0, "laugh_after": "none", "reaction": "laugh"},
    {"persona_id": "persona_2", "text": FOURTH, "audio_url": "/api/testmedia/missing", "image_index": 1, "laugh_after": "none", "reaction": "laugh"},
]
RESULT = {
    "roast_id": "offline-theater-test", "transcript": BEATS,
    "images": ["/api/testmedia/photo-0", "/api/testmedia/photo-1"],
    "credits_spent": 0, "credits_remaining": 100, "was_free_roast": True,
}
BATTLE_RESULT = {**RESULT, "battle": {"winner": "persona_1", "scores": {"persona_1": 2, "persona_2": 1}}}


def install_fixtures(context):
    context.route("**/api/roast/generate", lambda route: route.fulfill(json=RESULT))
    context.route("**/api/battle/generate", lambda route: route.fulfill(json=BATTLE_RESULT))

    def fake_media(route):
        name = route.request.url.rsplit("/", 1)[-1]
        if name.startswith("photo-"):
            route.fulfill(status=200, body=PHOTOS[int(name[-1])], content_type="image/jpeg")
        elif name.startswith("voice-"):
            route.fulfill(status=200, body=VOICE, content_type="audio/wav")
        else:
            route.fulfill(status=404, body="not found")

    context.route("**/api/testmedia/**", fake_media)


def login(page):
    page.goto(APP, wait_until="domcontentloaded")
    accept_adult_consent(page)
    page.get_by_test_id("preview-login-btn").click()
    page.wait_for_url("**/studio", timeout=20000)
    page.get_by_test_id("persona-card-persona_1").wait_for(timeout=15000)


def start_studio(page):
    page.get_by_test_id("persona-card-persona_1").click()
    page.get_by_test_id("persona-card-persona_2").click()
    page.get_by_test_id("subject-name-input").fill("Morgan")
    page.get_by_test_id("context-textarea").fill("Collects karaoke trophies")
    page.get_by_test_id("off-limits-input").fill("Family stories")
    page.get_by_test_id("image-file-input").set_input_files({"name": "test.jpg", "mimeType": "image/jpeg", "buffer": PHOTOS[0]})
    page.get_by_test_id("generate-roast-btn").click()
    page.get_by_test_id("roast-theater").wait_for(timeout=10000)


def wait_beat(page, number):
    page.wait_for_function("expected => document.querySelector('[data-testid=theater-progress]')?.textContent === expected",
                           arg=f"{number}/{len(BEATS)}", timeout=22000)
    page.get_by_test_id("theater-stage").wait_for(timeout=3000)
    assert page.get_by_test_id("theater-bubble").count() == 1
    assert page.get_by_test_id("theater-typing-text").count() == 1


def assert_layout(page):
    rect = page.evaluate("""() => {
      const r = s => document.querySelector(s).getBoundingClientRect().toJSON();
      return {w: innerWidth, h: innerHeight, stage: r('.th-stage'), photo: r('.th-photo'),
              bubble: r('.th-bubble'), speaker: r('.th-speaker')};
    }""")
    assert rect["stage"]["width"] >= rect["w"] - 2 and rect["stage"]["height"] >= rect["h"] - 2, rect
    assert rect["photo"]["width"] >= rect["w"] - 2 and rect["photo"]["height"] >= rect["h"] - 2, rect
    for name in ("bubble", "speaker"):
        box = rect[name]
        assert box["x"] >= -1 and box["y"] >= -1 and box["right"] <= rect["w"] + 1 and box["bottom"] <= rect["h"] + 1, rect


def test_studio_desktop(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    install_fixtures(ctx)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    sent = []
    page.on("request", lambda req: sent.append((req.post_data_buffer or b"").decode("utf-8", "replace")) if "/api/roast/generate" in req.url else None)
    login(page)
    start_studio(page)
    assert sent and all(value in sent[-1] for value in ("Morgan", "Collects karaoke trophies", "Family stories")), sent
    page.get_by_test_id("theater-splash").wait_for(timeout=4000)
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / "cinematic-splash.png"))
    page.get_by_test_id("theater-lineup").wait_for(timeout=8000)
    page.wait_for_timeout(850)
    assert page.get_by_test_id("theater-comic-persona_1").is_visible()
    assert page.get_by_test_id("theater-comic-persona_2").is_visible()
    page.screenshot(path=str(OUT / "cinematic-lineup.png"))
    page.get_by_test_id("theater-hotseat").wait_for(timeout=8000)
    assert "Morgan" in page.get_by_test_id("theater-hotseat").inner_text()
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "cinematic-hotseat.png"))
    wait_beat(page, 1)
    page.wait_for_function("document.querySelector('[data-testid=theater-typing-text]')?.textContent.includes('FIRSTCAPTION')")
    early = page.get_by_test_id("theater-typing-text").inner_text()
    assert len(early.replace("▍", "")) < len(FIRST), early
    page.wait_for_timeout(850)
    later = page.get_by_test_id("theater-typing-text").inner_text()
    assert len(later) > len(early), (early, later)
    first_photo = page.get_by_test_id("theater-photo").get_attribute("src")
    assert_layout(page)
    page.screenshot(path=str(OUT / "theater-desktop.png"))

    wait_beat(page, 2)
    assert page.get_by_test_id("theater-photo").get_attribute("src") != first_photo
    during_pause = page.get_by_test_id("theater-typing-text").inner_text()
    assert "FIRSTCAPTION" not in page.get_by_test_id("theater-stage").inner_text()
    assert "SECONDCAPTION" not in during_pause, during_pause
    page.wait_for_function("document.querySelector('[data-testid=theater-typing-text]')?.textContent.includes('SECONDCAPTION')")
    second_early = page.get_by_test_id("theater-typing-text").inner_text()
    assert len(second_early.replace("▍", "")) < len(SECOND), second_early
    assert "Nana Snap" in page.locator(".th-speaker").inner_text()

    wait_beat(page, 3)
    assert page.get_by_test_id("theater-photo").get_attribute("src") == first_photo
    assert "SECONDCAPTION" not in page.get_by_test_id("theater-stage").inner_text()
    page.wait_for_timeout(2100)
    scroll = page.locator(".th-bubble").evaluate("e => ({top:e.scrollTop, height:e.scrollHeight, client:e.clientHeight})")
    assert scroll["height"] > scroll["client"] and scroll["top"] >= scroll["height"] - scroll["client"] - 2, scroll
    assert_layout(page)

    wait_beat(page, 4)
    assert "THIRDCAPTION" not in page.get_by_test_id("theater-stage").inner_text()
    page.wait_for_function("document.querySelector('[data-testid=theater-typing-text]')?.textContent.includes('FOURTHCAPTION')")
    page.get_by_test_id("theater-outro").wait_for(timeout=12000)
    assert "Morgan" in page.get_by_test_id("theater-thanks").inner_text()
    assert "everybody for coming" in page.get_by_test_id("theater-outro").inner_text().lower()
    assert "where people come to get roasted and leave burnt crispy" in page.get_by_test_id("theater-motto").inner_text().lower().replace("\n", " ")
    page.screenshot(path=str(OUT / "cinematic-outro.png"))
    page.get_by_test_id("theater-done-btn").click()
    assert not page.get_by_test_id("transcript-disclosure").get_attribute("open")
    assert not page.get_by_test_id("transcript-line-0").is_visible()
    page.get_by_text("View full transcript").click()
    assert page.get_by_test_id("transcript-line-0").is_visible()
    page.get_by_test_id("watch-theater-btn").click()
    wait_beat(page, 1)
    assert page.get_by_test_id("theater-bubble").count() == 1
    page.get_by_test_id("theater-close-btn").click()
    assert not errors, errors
    ctx.close()
    print("PASS: Studio beat replacement, photo switching, speech timing, long caption scrolling, missing audio, outro and replay")


def test_mobile(browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, device_scale_factor=1)
    install_fixtures(ctx)
    page = ctx.new_page()
    login(page)
    start_studio(page)
    wait_beat(page, 1)
    page.wait_for_timeout(1100)
    assert_layout(page)
    page.screenshot(path=str(OUT / "theater-mobile.png"))
    wait_beat(page, 2)
    assert "FIRSTCAPTION" not in page.get_by_test_id("theater-stage").inner_text()
    wait_beat(page, 3)
    page.wait_for_timeout(1800)
    assert_layout(page)
    scroll = page.locator(".th-bubble").evaluate("e => ({top:e.scrollTop,height:e.scrollHeight,client:e.clientHeight})")
    assert scroll["height"] > scroll["client"] and scroll["top"] >= scroll["height"] - scroll["client"] - 2, scroll
    page.get_by_test_id("theater-close-btn").click()
    ctx.close()
    print("PASS: mobile photo/caption layout, single current caption and long-text scrolling")


def test_saved_replay(browser):
    ctx = browser.new_context(viewport={"width": 1100, "height": 800})
    install_fixtures(ctx)
    saved = {"id": RESULT["roast_id"], "transcript": BEATS, "image_count": 2, "mode": "roast",
             "subject_name": "Test subject", "created_at": "2026-11-03T12:00:00Z", "hd_export": True}
    ctx.route("**/api/roast/history", lambda route: route.fulfill(json={"history": [saved]}))
    def saved_photo(route):
        index = int(route.request.url.rsplit("/", 1)[-1].split(".")[0])
        route.fulfill(body=PHOTOS[index], content_type="image/jpeg")
    ctx.route("**/api/media/subject/offline-theater-test/*.jpg", saved_photo)
    generated = []
    page = ctx.new_page()
    page.on("request", lambda req: generated.append(req.url) if "/api/roast/generate" in req.url else None)
    login(page)
    page.reload(wait_until="domcontentloaded")
    page.get_by_test_id("recent-shows").locator("summary").click()
    page.get_by_test_id("recent-show-offline-theater-test").get_by_role("button", name="Watch again").click()
    wait_beat(page, 1)
    assert page.get_by_test_id("theater-photo").is_visible()
    assert not generated, "Replaying a saved show must not generate or charge for another show"
    page.get_by_test_id("theater-close-btn").click()
    ctx.close()
    print("PASS: a saved show can be replayed after reload without generating or spending credits")


def test_battle_and_share(browser):
    ctx = browser.new_context(viewport={"width": 1100, "height": 800})
    install_fixtures(ctx)
    page = ctx.new_page()
    login(page)
    page.get_by_test_id("nav-battle-btn").click()
    page.get_by_test_id("battle-persona-persona_1").click()
    page.get_by_test_id("battle-persona-persona_2").click()
    page.get_by_test_id("battle-fight-btn").click()
    wait_beat(page, 1)
    assert page.get_by_test_id("theater-score").is_visible()
    assert_layout(page)
    wait_beat(page, 2)
    assert "FIRSTCAPTION" not in page.get_by_test_id("theater-stage").inner_text()
    page.get_by_test_id("theater-close-btn").click()

    roster = page.request.get(APP + "/api/personas").json()["personas"]
    personas = [p for p in roster if p["id"] in ("persona_1", "persona_2")]
    ctx.route("**/api/share/offline-theater-test", lambda route: route.fulfill(json={**RESULT, "personas": personas, "mode": "roast", "subject_name": "Test"}))
    page.goto(APP + "/r/offline-theater-test", wait_until="domcontentloaded")
    page.get_by_test_id("share-play-btn").click()
    wait_beat(page, 1)
    assert_layout(page)
    wait_beat(page, 2)
    assert "FIRSTCAPTION" not in page.get_by_test_id("theater-stage").inner_text()
    page.get_by_test_id("theater-close-btn").click()
    assert not page.get_by_test_id("transcript-line-0").is_visible()
    ctx.close()
    print("PASS: Battle and shared shows use the same single-caption photo-first theater")


def test_small_lineup_and_reduced_motion(browser):
    ctx = browser.new_context(viewport={"width": 320, "height": 568}, is_mobile=True,
                              device_scale_factor=1, reduced_motion="reduce")
    install_fixtures(ctx)
    page = ctx.new_page()
    login(page)
    for i in range(1, 6):
        page.get_by_test_id(f"persona-card-persona_{i}").click()
    page.get_by_test_id("subject-name-input").fill("Morgan")
    page.get_by_test_id("image-file-input").set_input_files({"name": "test.jpg", "mimeType": "image/jpeg", "buffer": PHOTOS[0]})
    page.get_by_test_id("generate-roast-btn").click()
    page.get_by_test_id("theater-lineup").wait_for(timeout=10000)
    page.wait_for_timeout(2500)
    for i in range(1, 6):
        assert page.get_by_test_id(f"theater-comic-persona_{i}").is_visible()
    rects = page.evaluate("""() => ({w: innerWidth, h: innerHeight,
      lineup: document.querySelector('.th-lineup').getBoundingClientRect().toJSON(),
      cards: Array.from(document.querySelectorAll('.th-comic')).map(e => e.getBoundingClientRect().toJSON()),
      anim: getComputedStyle(document.querySelector('.th-comic')).animationDuration})""")
    assert rects["lineup"]["top"] >= 0 and rects["lineup"]["bottom"] <= rects["h"], rects
    assert all(r["left"] >= 0 and r["right"] <= rects["w"] and r["bottom"] <= rects["h"] for r in rects["cards"]), rects
    assert float(rects["anim"].rstrip("s")) < .01, rects
    page.screenshot(path=str(OUT / "cinematic-five-comics-mobile.png"))
    page.get_by_test_id("theater-close-btn").click()
    ctx.close()
    print("PASS: five-comic introduction fits a small screen and honors reduced-motion preferences")


def test_rapid_fire_pacing(browser):
    ctx = browser.new_context(viewport={"width": 1100, "height": 800})
    install_fixtures(ctx)
    rapid = [{"persona_id": f"persona_{1 + i % 2}", "text": f"Rapid joke {i + 1}",
              "audio_url": f"/api/testmedia/voice-{i + 1}", "image_index": 0,
              "type": "punchline", "laugh_after": "explosive", "reaction": "laugh", "rapid_fire": True,
              "pause_before_ms": 1000, "pause_after_ms": 1000} for i in range(3)]
    ctx.route("**/api/roast/generate", lambda route: route.fulfill(json={**RESULT, "transcript": rapid}))
    page = ctx.new_page()
    login(page)
    start_studio(page)
    page.wait_for_function("document.querySelector('[data-testid=theater-progress]')?.textContent === '1/3'", timeout=22000)
    started = time.monotonic()
    page.wait_for_function("document.querySelector('[data-testid=theater-progress]')?.textContent === '2/3'", timeout=10000)
    elapsed = time.monotonic() - started
    assert 2.2 < elapsed < 5.2, elapsed  # 2.5 s voice, then a shortened laugh hold, not a 3.4 s pause.
    page.get_by_test_id("theater-close-btn").click()
    ctx.close()
    print("PASS: rapid-fire handoffs ride the laugh without long gaps")


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
        try:
            test_studio_desktop(browser)
            test_mobile(browser)
            test_saved_replay(browser)
            test_battle_and_share(browser)
            test_small_lineup_and_reduced_motion(browser)
            test_rapid_fire_pacing(browser)
        finally:
            browser.close()
