#!/usr/bin/env python3
"""Offline About Developer checks against the running Da RoastBox preview.

Uses bundled images/audio and the isolated local preview login. Never calls any
AI, image, TTS, payment or Google provider. Browser phone sizes are emulated.
"""
from __future__ import annotations

from ui_helpers import enter_preview

import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

APP = os.environ.get("ROASTBOX_TEST_ORIGIN", "http://127.0.0.1:3000").rstrip("/")
SHOTS = Path("/home/user/.cache/da-roastbox-author/screens")
SHOTS.mkdir(parents=True, exist_ok=True)

AUDIO_HOOK = """(() => {
  const NativeAudio = window.Audio;
  window.__bookAudios = [];
  window.Audio = function (...args) {
    const a = new NativeAudio(...args);
    window.__bookAudios.push(a);
    return a;
  };
})();"""


def open_developer_book(scope):
    enter_preview(scope)
    scope.get_by_test_id("menu-toggle").click()
    scope.get_by_test_id("menu-about-developer-btn").click()


def assert_book_fits(page, width, height, label):
    data = page.get_by_test_id("about-author-dialog").evaluate("""e => {
      const b = e.getBoundingClientRect();
      const close = e.querySelector('[data-testid=author-close]').getBoundingClientRect();
      return {left:b.left, right:b.right, top:b.top, bottom:b.bottom,
              inner:e.clientWidth, scroll:e.scrollWidth, closeLeft:close.left,
              closeRight:close.right, closeTop:close.top, closeBottom:close.bottom,
              viewport:document.documentElement.clientWidth,
              bodyScroll:document.documentElement.scrollWidth};
    }""")
    assert data["left"] >= -1 and data["right"] <= width + 1, (label, data)
    assert data["top"] >= -1 and data["bottom"] <= height + 1, (label, data)
    assert data["scroll"] <= data["inner"] + 1, (label, data)
    assert data["viewport"] == width and data["bodyScroll"] <= width + 1, (label, data)
    assert data["closeLeft"] >= 0 and data["closeRight"] <= width + 1, (label, data)
    assert data["closeTop"] >= 0 and data["closeBottom"] <= height + 1, (label, data)


def test_layouts(browser):
    cases = [(200, 400), (240, 568), (280, 653), (320, 568), (412, 839),
             (568, 320), (844, 390), (768, 1024), (1024, 768), (1440, 900), (2560, 1440)]
    for width, height in cases:
        touch = width < 1100
        ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=touch, has_touch=touch,
                                  reduced_motion="reduce")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(APP, wait_until="domcontentloaded")
        open_developer_book(page)
        page.get_by_test_id("author-cover").wait_for()
        assert_book_fits(page, width, height, f"{width}×{height} cover")
        assert page.get_by_test_id("about-author-dialog").get_attribute("role") == "dialog"
        page.get_by_test_id("author-start-reading").click()
        expect(page.get_by_test_id("author-page-title")).to_have_text("The Kid Who Asked Why")
        assert_book_fits(page, width, height, f"{width}×{height} page")
        # Changing a page on a very short screen must not inherit the cover's
        # scrolled position and hide the beginning of the new chapter.
        assert page.get_by_test_id("about-author-dialog").evaluate("e => e.scrollTop") < 2
        page.get_by_test_id("author-next").click()
        expect(page.get_by_test_id("author-page-title")).to_have_text("The QBasic Incident")
        assert page.get_by_test_id("about-author-dialog").evaluate("e => e.scrollTop") < 2
        assert_book_fits(page, width, height, f"{width}×{height} next")
        page.keyboard.press("Escape")
        expect(page.get_by_test_id("about-author-dialog")).to_have_count(0)
        assert not errors, (width, height, errors)
        ctx.close()
        print(f"PASS: author modal, close button and navigation fit {width}×{height}", flush=True)


def test_audio_images_and_state(browser):
    ctx = browser.new_context(viewport={"width": 412, "height": 839}, is_mobile=True, has_touch=True,
                              reduced_motion="reduce")
    ctx.add_init_script(AUDIO_HOOK)
    page = ctx.new_page()
    errors, bad_responses = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("response", lambda response: bad_responses.append((response.status, response.url))
            if "/assets/about-author/" in response.url and response.status >= 400 else None)
    page.goto(APP, wait_until="domcontentloaded")
    open_developer_book(page)
    page.get_by_test_id("author-listen-story").tap()
    expect(page.get_by_test_id("author-page-title")).to_have_text("The Kid Who Asked Why")
    page.wait_for_function("window.__bookAudios.length && !window.__bookAudios.at(-1).paused && window.__bookAudios.at(-1).currentTime > 0.1", timeout=15000)
    page.locator(".author-volume input").fill("0.25")
    page.wait_for_function("Math.abs(window.__bookAudios.at(-1).volume - 0.25) < 0.01")
    page.get_by_test_id("author-play").tap()
    page.wait_for_function("window.__bookAudios.at(-1).paused")
    page.get_by_test_id("author-play").tap()
    page.wait_for_function("!window.__bookAudios.at(-1).paused")
    page.get_by_test_id("author-replay").tap()
    page.wait_for_function("window.__bookAudios.at(-1).currentTime < 2")
    assert page.get_by_test_id("author-auto-advance").is_checked()
    # Seek near the actual end; the ended event should advance AND play the next
    # bundled MP3, without waiting 20 seconds or making a synthesis request.
    page.wait_for_function("Number.isFinite(window.__bookAudios.at(-1).duration) && window.__bookAudios.at(-1).duration > 1")
    page.evaluate("window.__bookAudios.at(-1).currentTime = window.__bookAudios.at(-1).duration - 0.1")
    expect(page.get_by_test_id("author-page-title")).to_have_text("The QBasic Incident", timeout=10000)
    page.wait_for_function("window.__bookAudios.length >= 2 && !window.__bookAudios.at(-1).paused", timeout=10000)
    assert abs(page.evaluate("window.__bookAudios.at(-1).volume") - 0.25) < 0.01
    page.get_by_test_id("author-play").tap()  # stop audio while checking page-by-page navigation
    for chapter in range(2, 11):
        if chapter > 2: page.get_by_test_id("author-next").tap()
        img = page.get_by_test_id("author-chapter-image")
        expect(img).to_have_attribute("src", f"/assets/about-author/images/{chapter:02}.webp")
        page.wait_for_function("""() => { const e = document.querySelector('[data-testid=author-chapter-image]');
            return e && e.complete && e.naturalWidth > 0; }""")
        assert f"PAGE {chapter:02} OF 10" in page.get_by_test_id("about-author-dialog").inner_text()
    text = page.get_by_test_id("author-story-text").inner_text()
    assert text.index("God") < text.index("mama") < text.index("hold dear") < text.index("AI solutions")
    assert "ChatGPTs" in text and "Deserius Arte" in text and "Hustler Anomalies Enterprises LLC" in text
    assert page.get_by_test_id("author-next").is_disabled()
    page.get_by_test_id("author-previous").tap()
    expect(page.get_by_test_id("author-page-title")).to_have_text("The Squirrel Conspiracy")
    page.get_by_test_id("author-cover-btn").tap()
    expect(page.get_by_test_id("author-cover")).to_be_visible()
    page.get_by_test_id("author-close").tap()
    expect(page.get_by_test_id("about-author-dialog")).to_have_count(0)
    assert page.evaluate("window.__bookAudios.every(a => a.paused)")
    assert not errors and not bad_responses, (errors, bad_responses)
    print("PASS: real MP3 playback, pause/resume/replay, automatic advance, all chapter images and gratitude order", flush=True)

    # Opening the book from the signed-in shell must not destroy a Studio draft.
    page.get_by_test_id("menu-close").tap()
    page.get_by_test_id("subject-name-input").fill("My unsaved studio draft")
    page.get_by_test_id("context-textarea").fill("Keep this detail while the book opens.")
    page.get_by_test_id("menu-toggle").tap()
    page.get_by_test_id("menu-about-developer-btn").tap()
    page.get_by_test_id("author-close").tap()
    assert page.url.endswith("/studio")
    assert page.get_by_test_id("subject-name-input").input_value() == "My unsaved studio draft"
    assert page.get_by_test_id("context-textarea").input_value() == "Keep this detail while the book opens."
    assert not errors and not bad_responses, (errors, bad_responses)
    ctx.close()
    print("PASS: opening and closing the book preserves the active Studio draft and route", flush=True)


def test_embedded_and_keyboard(browser):
    ctx = browser.new_context(viewport={"width": 412, "height": 839}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.set_content(f'<meta name="viewport" content="width=device-width, initial-scale=1"><style>body{{margin:0}}</style><iframe src="{APP}/" style="width:100vw;height:100vh;border:0"></iframe>')
    frame = page.frame_locator("iframe")
    open_developer_book(frame)
    expect(frame.get_by_test_id("author-cover")).to_be_visible()
    frame.get_by_test_id("author-start-reading").tap()
    expect(frame.get_by_test_id("author-page-title")).to_have_text("The Kid Who Asked Why")
    frame.get_by_test_id("author-close").tap()
    expect(frame.get_by_test_id("about-author-dialog")).to_have_count(0)
    ctx.close()

    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(APP, wait_until="domcontentloaded")
    open_developer_book(page)
    for _ in range(12):
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.closest('[data-testid=about-author-dialog]') !== null")
    page.keyboard.press("Escape")
    expect(page.get_by_test_id("about-author-dialog")).to_have_count(0)
    expect(page.get_by_test_id("menu-about-developer-btn")).to_be_focused(timeout=3000)
    ctx.close()
    print("PASS: embedded preview, keyboard focus trap, Escape and focus return", flush=True)


def test_narration_fallback(browser):
    ctx = browser.new_context(viewport={"width": 412, "height": 839}, is_mobile=True, has_touch=True)
    ctx.add_init_script(AUDIO_HOOK)
    ctx.add_init_script("""(() => {
      const play = HTMLMediaElement.prototype.play;
      let rejectFirst = true;
      HTMLMediaElement.prototype.play = function (...args) {
        if (rejectFirst && (this.currentSrc || this.src).includes('/assets/about-author/audio/')) { rejectFirst = false; return Promise.reject(new DOMException('Blocked', 'NotAllowedError')); }
        return play.apply(this, args);
      };
    })();""")
    page = ctx.new_page()
    page.goto(APP, wait_until="domcontentloaded")
    open_developer_book(page)
    page.get_by_test_id("author-listen-story").tap()
    expect(page.get_by_test_id("author-audio-error")).to_contain_text("Tap Play")
    expect(page.get_by_test_id("author-story-text")).to_contain_text("Before the tattoos")
    page.get_by_test_id("author-play").tap()
    page.wait_for_function("window.__bookAudios.length === 1 && !window.__bookAudios[0].paused && window.__bookAudios[0].currentTime > 0.1")
    expect(page.get_by_test_id("author-audio-error")).to_have_count(0)
    page.get_by_test_id("author-close").tap()
    ctx.close()

    missing = browser.new_context(viewport={"width": 412, "height": 839})
    missing.route("**/assets/about-author/audio/01.mp3", lambda route: route.fulfill(status=404, body="missing fixture"))
    page = missing.new_page()
    page.goto(APP, wait_until="domcontentloaded")
    open_developer_book(page)
    page.get_by_test_id("author-start-reading").click()
    expect(page.get_by_test_id("author-audio-error")).to_contain_text("couldn't be loaded", timeout=10000)
    expect(page.get_by_test_id("author-story-text")).to_contain_text("Before the tattoos")
    page.get_by_test_id("author-next").click()
    expect(page.get_by_test_id("author-page-title")).to_have_text("The QBasic Incident")
    page.get_by_test_id("author-close").click()
    missing.close()
    print("PASS: blocked playback can be retried; a missing audio asset leaves the story readable and navigable", flush=True)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
        try:
            test_layouts(browser)
            test_audio_images_and_state(browser)
            test_embedded_and_keyboard(browser)
            test_narration_fallback(browser)
        finally:
            browser.close()
    print("About Developer offline checks completed successfully.")


if __name__ == "__main__":
    main()
