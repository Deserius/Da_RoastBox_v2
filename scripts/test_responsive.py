#!/usr/bin/env python3
"""Offline responsive/touch regressions against the running workspace preview.

Uses real local preview login but intercepts all AI, voice and reel generation.
Chromium Android emulation is not a substitute for testing physical devices.
"""
from __future__ import annotations

from ui_helpers import accept_adult_consent, accept_adult_consent_async

import os
import re
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from test_persona_browser import fake_voices
from test_google_login_ui import make_context, callback_for, PROVIDER_START
from test_theater_display import PHOTOS, BEATS, RESULT, install_fixtures, assert_layout
import imageio_ffmpeg

APP = os.environ.get("ROASTBOX_TEST_ORIGIN", "http://127.0.0.1:3000").rstrip("/")
OUT = Path("/home/user/.cache/da-roastbox")
OUT.mkdir(parents=True, exist_ok=True)


def enter(page, touch=False, expected_width=None):
    page.goto(APP, wait_until="domcontentloaded")
    if expected_width is not None:
        layout(page, expected_width, f"splash {expected_width}px")
    if touch:
        accept_adult_consent(page)
        page.get_by_test_id("preview-login-btn").tap()
    else:
        accept_adult_consent(page)
        page.get_by_test_id("preview-login-btn").click()
    page.wait_for_url("**/studio", timeout=20000)
    page.get_by_test_id("persona-card-persona_1").wait_for(timeout=15000)


def layout(page, expected_width, label):
    result = page.evaluate("""() => {
      const w = document.documentElement.clientWidth;
      const bad = Array.from(document.querySelectorAll('button,a,input,select,textarea,.panel')).filter(e => {
        const s = getComputedStyle(e), b = e.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' && b.width > 3 && (b.left < -2 || b.right > w + 2);
      }).slice(0, 8).map(e => ({ tag: e.tagName, id: e.dataset.testid, text: e.innerText?.slice(0, 30),
                                left: e.getBoundingClientRect().left, right: e.getBoundingClientRect().right }));
      return { width: w, inner: innerWidth, scroll: document.documentElement.scrollWidth, bad };
    }""")
    assert result["width"] == expected_width and result["inner"] <= expected_width + 1, (label, result)
    assert result["scroll"] <= expected_width + 1 and not result["bad"], (label, result)


def test_layout_matrix(playwright):
    # Foldable narrow, common phones, landscape, tablet, desktop and ultrawide.
    cases = [
        ("very-narrow", 200, 400, True), ("narrow", 240, 568, True),
        ("fold", 280, 653, True), ("small-phone", 320, 568, True),
        ("android", 412, 839, True), ("short-landscape", 568, 320, True), ("phone-landscape", 844, 390, True),
        ("tablet", 768, 1024, True), ("tablet-landscape", 1024, 768, True),
        ("desktop", 1440, 900, False), ("ultrawide", 2560, 1440, False),
    ]
    for name, width, height, touch in cases:
        # Fresh browser per size avoids accumulating renderer memory on small CI hosts.
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=touch, has_touch=touch,
                                  reduced_motion="reduce")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        enter(page, touch, expected_width=width)
        layout(page, width, f"{name} studio")
        for route, tid in (("roasters", "roasters-page"), ("battle", "battle-page"),
                           ("credits", "credits-page"), ("settings", "settings-page")):
            button = page.get_by_test_id(f"nav-{route}-btn")
            button.tap() if touch else button.click()
            page.get_by_test_id(tid).wait_for(timeout=15000)
            if route == "settings":
                page.get_by_test_id("service-configuration").wait_for(timeout=15000)
            elif route == "credits":
                page.get_by_test_id("pack-credits_starter").wait_for(timeout=15000)
            elif route == "battle":
                page.get_by_test_id("battle-persona-persona_1").wait_for(timeout=15000)
            layout(page, width, f"{name} {route}")
        assert not errors, (name, errors)
        ctx.close()
        browser.close()
        print(f"PASS: {name} {width}×{height} — Studio, Roasters, Battle, Credits and Settings", flush=True)


def test_android_touch(browser, playwright):
    ctx = browser.new_context(**playwright.devices["Pixel 7"])
    page = ctx.new_page()
    enter(page, touch=True)
    expect(page.get_by_test_id("persona-mobile-expand")).to_be_visible()
    expect(page.get_by_test_id("persona-card-persona_9")).not_to_be_visible()
    page.get_by_test_id("persona-mobile-expand").tap()
    expect(page.get_by_test_id("persona-card-persona_9")).to_be_visible()
    page.get_by_test_id("persona-card-persona_9").locator(".persona-card-main").tap()
    page.get_by_test_id("persona-mobile-expand").tap()
    expect(page.get_by_test_id("persona-card-persona_9")).to_be_visible()  # selected comics remain visible
    page.get_by_test_id("studio-jump-step-hotseat").tap()
    page.wait_for_function("document.querySelector('[data-testid=step-hotseat]').getBoundingClientRect().top < 40")
    with page.expect_file_chooser() as chosen:
        page.get_by_test_id("upload-zone").tap()
    assert chosen.value.is_multiple()
    chosen.value.set_files([{"name": f"photo-{i}.jpg", "mimeType": "image/jpeg", "buffer": PHOTOS[i % 2]} for i in range(4)])
    expect(page.get_by_test_id("remove-image-3")).to_be_visible()
    expect(page.get_by_test_id("image-file-input")).to_be_disabled()
    page.get_by_test_id("remove-image-0").tap()
    expect(page.get_by_test_id("image-file-input")).to_be_enabled()
    with page.expect_file_chooser() as chosen:
        page.get_by_test_id("upload-zone").tap()
    chosen.value.set_files({"name": "replacement.jpg", "mimeType": "image/jpeg", "buffer": PHOTOS[0]})
    expect(page.get_by_test_id("remove-image-3")).to_be_visible()
    page.get_by_test_id("nav-battle-btn").tap()
    page.get_by_test_id("battle-persona-persona_1").wait_for()
    with page.expect_file_chooser() as chosen:
        page.get_by_test_id("battle-upload-btn").tap()
    assert not chosen.value.is_multiple()
    chosen.value.set_files({"name": "battle-photo.jpg", "mimeType": "image/jpeg", "buffer": PHOTOS[0]})
    expect(page.get_by_test_id("battle-upload-btn")).to_contain_text("battle-photo.jpg")
    layout(page, 412, "Android touch and chooser")
    ctx.close()
    print("PASS: Pixel 7 touch, roster expansion, step jumping and both native photo choosers")


BLOCK_MEDIA = """(() => {
  window.__blockedPlayCalls = 0;
  const original = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function (...args) {
    if (window.__blockedPlayCalls > 0) {
      window.__blockedPlayCalls -= 1;
      return Promise.reject(new DOMException('Autoplay blocked for test', 'NotAllowedError'));
    }
    return original.apply(this, args);
  };
})();"""


def test_audio_gestures(browser, playwright):
    ctx = browser.new_context(**playwright.devices["Pixel 7"])
    ctx.add_init_script(BLOCK_MEDIA)
    calls = []
    fake_voices(ctx, calls)
    install_fixtures(ctx)
    page = ctx.new_page()
    requests = []
    page.on("request", lambda req: requests.append(req.url))
    enter(page, touch=True)
    page.get_by_test_id("persona-info-persona_1").tap()
    modal = page.get_by_test_id("persona-detail-modal")
    modal.wait_for()
    page.evaluate("window.__blockedPlayCalls = 1")
    sample = modal.get_by_test_id("persona-voice-preview-btn")
    sample.tap()
    expect(modal.get_by_text("TAP TO PLAY")).to_be_visible(timeout=10000)
    assert len(calls) == 1, calls
    sample.tap()
    expect(modal.get_by_text("NOW PLAYING")).to_be_visible(timeout=10000)
    assert len(calls) == 1, "A playback retry must not regenerate a voice"
    modal.get_by_test_id("persona-detail-close-btn").tap()

    page.get_by_test_id("persona-card-persona_1").locator(".persona-card-main").tap()
    page.get_by_test_id("image-file-input").set_input_files({"name": "test.jpg", "mimeType": "image/jpeg", "buffer": PHOTOS[0]})
    page.evaluate("window.__blockedPlayCalls = 1")
    page.get_by_test_id("generate-roast-btn").tap()
    page.get_by_test_id("theater-audio-gate").wait_for(timeout=20000)
    before = sum("/api/testmedia/voice-1" in url for url in requests)
    first = page.get_by_test_id("theater-progress").inner_text()
    page.wait_for_timeout(500)
    assert page.get_by_test_id("theater-progress").inner_text() == first, "Blocked speech must wait for the user"
    page.get_by_test_id("theater-resume-audio").tap()
    expect(page.get_by_test_id("theater-audio-gate")).not_to_be_visible(timeout=10000)
    page.wait_for_function("document.querySelector('[data-testid=theater-typing-text]')?.textContent.includes('FIRSTCAPTION')")
    assert sum("/api/testmedia/voice-1" in url for url in requests) == before, "Resuming must reuse the loaded clip"
    page.get_by_test_id("theater-close-btn").tap()

    page.evaluate("window.__blockedPlayCalls = 1")
    page.get_by_test_id("watch-theater-btn").tap()
    page.get_by_test_id("theater-audio-gate").wait_for(timeout=20000)
    page.get_by_test_id("theater-captions-only").tap()
    expect(page.get_by_test_id("theater-audio-gate")).not_to_be_visible()
    page.wait_for_function("document.querySelector('[data-testid=theater-typing-text]')?.textContent.includes('FIRSTCAPTION')")
    page.get_by_test_id("theater-close-btn").tap()
    assert sum("/api/roast/generate" in url for url in requests) == 1
    ctx.close()
    print("PASS: Android-style autoplay rejection offers a no-regeneration retry and captions-only mode")


def test_embedded_android_and_google(browser, playwright):
    options = playwright.devices["Pixel 7"]
    ctx = browser.new_context(**options)
    page = ctx.new_page()
    page.set_content(f'<meta name="viewport" content="width=device-width, initial-scale=1"><style>body{{margin:0}}</style><iframe src="{APP}/" style="width:100vw;height:100vh;border:0"></iframe>')
    frame = page.frame(url=re.compile("^" + re.escape(APP)))
    if frame is None:
        page.wait_for_timeout(500)
        frame = page.frame(url=re.compile("^" + re.escape(APP)))
    assert frame is not None
    accept_adult_consent(frame)
    frame.get_by_test_id("preview-login-btn").tap()
    frame.wait_for_url("**/studio", timeout=20000)
    frame.get_by_test_id("nav-settings-btn").tap()
    frame.get_by_test_id("settings-page").wait_for()
    assert frame.evaluate("document.documentElement.clientWidth") == 412
    assert frame.evaluate("innerWidth") == 412
    ctx.close()

    # Exercise the OAuth window in an Android-sized embedded browser, with a
    # local identity stub. No real Google account or network login is used.
    ctx, calls = make_context(browser, **options)
    page = ctx.new_page()
    page.set_content(f'<meta name="viewport" content="width=device-width, initial-scale=1"><style>body{{margin:0}}</style><iframe src="{APP}/" style="width:100vw;height:100vh;border:0"></iframe>')
    frame = page.frame(url=re.compile("^" + re.escape(APP)))
    if frame is None:
        page.wait_for_timeout(500)
        frame = page.frame(url=re.compile("^" + re.escape(APP)))
    assert frame is not None
    accept_adult_consent(frame)
    with page.expect_popup() as opened:
        frame.get_by_test_id("splash-login-btn").tap()
    popup = opened.value
    popup.wait_for_url(PROVIDER_START + "**")
    callback, params = callback_for(popup.url)
    assert params["mode"] == ["popup"]
    popup.evaluate("url => { window.location.href = url; }", callback + "#session_id=android-offline-id")
    frame.wait_for_url("**/studio", timeout=20000)
    assert [(k, v) for k, v in calls if k == "session"] == [("session", {"session_id": "android-offline-id"})]
    ctx.close()
    print("PASS: Android-sized embedded preview navigation and mocked Google popup/state exchange")


def test_profile_dialogs(browser):
    cases = [(200, 400), (240, 568), (280, 653), (320, 568), (412, 839), (568, 320), (844, 390), (768, 1024), (1024, 768), (1440, 900)]
    for width, height in cases:
        touch = width < 1200
        ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=touch, has_touch=touch)
        page = ctx.new_page()
        enter(page, touch)
        info = page.get_by_test_id("persona-info-persona_1")
        info.tap() if touch else info.click()
        modal = page.get_by_test_id("persona-detail-modal")
        modal.wait_for()
        bounds = modal.bounding_box()
        assert bounds["x"] >= -1 and bounds["y"] >= -1 and bounds["x"] + bounds["width"] <= width + 1 and bounds["y"] + bounds["height"] <= height + 1, (width, height, bounds)
        clip = modal.evaluate("""e => {
          const root = e.getBoundingClientRect();
          return Array.from(e.querySelectorAll('button,h2,p')).filter(el => {
            const b = el.getBoundingClientRect();
            return b.width > 2 && (b.left < root.left - 2 || b.right > root.right + 2);
          }).map(el => ({text:el.innerText, box:el.getBoundingClientRect().toJSON()}));
        }""")
        assert not clip, (width, height, clip)
        # Bottom controls remain reachable even when the viewport is short.
        modal.get_by_test_id("persona-detail-pick-btn").scroll_into_view_if_needed()
        assert modal.get_by_test_id("persona-detail-pick-btn").is_visible()
        modal.get_by_test_id("persona-detail-close-btn").click()
        ctx.close()
    print("PASS: profile dialogs fit and scroll across phone, landscape, tablet and desktop")


def test_public_share_and_checkout(browser):
    personas = [
        {"id": "persona_1", "displayName": "Big Sun-K", "name": "Big Sun-K", "image": "assets/personas/persona_1.webp", "color": "#ff7136"},
        {"id": "persona_2", "displayName": "Nana Snap", "name": "Nana Snap", "image": "assets/personas/persona_2.webp", "color": "#ffc529"},
    ]
    for width, height, touch in [(200, 400, True), (320, 568, True), (844, 390, True), (1440, 900, False)]:
        ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=touch, has_touch=touch)
        payload = {**RESULT, "personas": personas, "mode": "roast", "subject_name": "AReallyLongUnbrokenGuestName" * 4}
        ctx.route("**/api/share/offline-responsive", lambda route: route.fulfill(json=payload))
        page = ctx.new_page()
        page.goto(APP + "/r/offline-responsive", wait_until="domcontentloaded")
        page.get_by_test_id("disclaimer-checkbox").click()
        page.get_by_test_id("share-play-btn").wait_for()
        layout(page, width, f"public share {width}×{height}")
        page.get_by_test_id("transcript-disclosure").locator("summary").click()
        layout(page, width, f"public transcript {width}×{height}")
        enter(page, touch)
        for path, tid in (("/credits/success", "checkout-success"), ("/credits/cancel", "checkout-cancel")):
            page.goto(APP + path, wait_until="domcontentloaded")
            page.get_by_test_id(tid).wait_for(timeout=15000)
            layout(page, width, f"{path} {width}×{height}")
        ctx.close()
    print("PASS: public share, expanded transcript and checkout return pages across screen sizes")


def make_tiny_video():
    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i",
                        "color=c=orange:s=90x160:r=10", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", tmp.name], check=True)
        return Path(tmp.name).read_bytes()


def test_theater_layouts(playwright):
    for width, height, touch in [(200, 400, True), (280, 653, True), (320, 568, True), (568, 320, True), (844, 390, True),
                                  (768, 1024, True), (1440, 900, False)]:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=touch, has_touch=touch)
        install_fixtures(ctx)
        one_beat = {**RESULT, "transcript": [BEATS[0]]}
        ctx.route("**/api/roast/generate", lambda route: route.fulfill(json=one_beat))
        page = ctx.new_page()
        enter(page, touch)
        for pid in ("persona_1", "persona_2"):
            card = page.get_by_test_id(f"persona-card-{pid}").locator(".persona-card-main")
            card.tap() if touch else card.click()
        page.get_by_test_id("image-file-input").set_input_files({"name": "test.jpg", "mimeType": "image/jpeg", "buffer": PHOTOS[0]})
        page.get_by_test_id("generate-roast-btn").click()
        page.get_by_test_id("theater-lineup").wait_for(timeout=12000)
        page.wait_for_timeout(350)
        box = page.get_by_test_id("theater-lineup").bounding_box()
        assert box["x"] >= -1 and box["y"] >= -1 and box["x"] + box["width"] <= width + 1 and box["y"] + box["height"] <= height + 1, (width, height, box)
        page.get_by_test_id("theater-stage").wait_for(timeout=12000)
        assert_layout(page)
        for control in page.locator(".th-topbar button").all():
            bounds = control.bounding_box()
            assert bounds["x"] >= -1 and bounds["x"] + bounds["width"] <= width + 1, (width, height, bounds)
        if page.get_by_test_id("theater-audio-gate").is_visible():
            page.get_by_test_id("theater-resume-audio").click()
        page.get_by_test_id("theater-outro").wait_for(timeout=12000)
        done = page.get_by_test_id("theater-done-btn")
        done.scroll_into_view_if_needed()
        assert done.is_visible()
        bounds = page.locator(".th-outro").bounding_box()
        assert bounds["x"] >= -1 and bounds["y"] >= -1 and bounds["x"] + bounds["width"] <= width + 1 and bounds["y"] + bounds["height"] <= height + 1, (width, height, bounds)
        if (width, height) == (844, 390):
            page.screenshot(path=str(OUT / "theater-landscape.png"))
        done.click()
        ctx.close()
        browser.close()
        print(f"PASS: theater layout {width}×{height}", flush=True)
    print("PASS: cinematic lineup, photo/captions and outro fit short-landscape, phone, tablet and desktop")


def test_reel_dialog_and_download(playwright):
    video = make_tiny_video()
    for width, height, touch in [(200, 400, True), (280, 653, True), (320, 568, True), (568, 320, True), (844, 390, True), (1440, 900, False)]:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=touch, has_touch=touch, accept_downloads=True)
        install_fixtures(ctx)
        lengths = []
        def reel(route):
            length = route.request.post_data_json["length"]
            lengths.append(length)
            route.fulfill(json={"id": f"reel-{length}-fixture", "length": length, "status": "done", "video_url": f"/api/test-reel/{length}.mp4"})
        ctx.route(re.compile(r".*/api/roast/[^/]+/reels$"), lambda route: route.fulfill(json={"reels": []}))
        ctx.route(re.compile(r".*/api/roast/[^/]+/reel$"), reel)
        ctx.route(re.compile(r".*/api/roast/[^/]+/share$"), lambda route: route.fulfill(json={"share_path": "/r/" + "mock" * 15}))
        ctx.route("**/api/test-reel/**", lambda route: route.fulfill(body=video, content_type="video/mp4"))
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        enter(page, touch)
        card = page.get_by_test_id("persona-card-persona_1").locator(".persona-card-main")
        card.tap() if touch else card.click()
        page.get_by_test_id("image-file-input").set_input_files({"name": "test.jpg", "mimeType": "image/jpeg", "buffer": PHOTOS[0]})
        go = page.get_by_test_id("generate-roast-btn")
        go.tap() if touch else go.click()
        page.get_by_test_id("roast-theater").wait_for(timeout=10000)
        page.get_by_test_id("theater-close-btn").click()
        page.get_by_test_id("share-roast-btn").click()
        page.get_by_test_id("share-link-input").wait_for()
        layout(page, width, f"reel and share controls {width}×{height}")
        page.get_by_test_id("reel-30-btn").click()
        # A finished export now opens automatically; no second View click.
        modal = page.get_by_test_id("reel-ready")
        modal.wait_for()
        page.get_by_test_id("reel-video").wait_for(timeout=10000)
        page.wait_for_function("document.querySelector('[data-testid=reel-video]')?.videoWidth > 0")
        bounds = modal.bounding_box()
        assert bounds["x"] >= -1 and bounds["y"] >= -1 and bounds["x"] + bounds["width"] <= width + 1 and bounds["y"] + bounds["height"] <= height + 1, (width, height, bounds)
        assert page.get_by_test_id("reel-video").get_attribute("src").startswith("blob:")
        with page.expect_download(timeout=10000) as downloaded:
            page.get_by_test_id("reel-download-btn").click()
        assert "30s" in downloaded.value.suggested_filename
        assert Path(downloaded.value.path()).read_bytes() == video
        page.get_by_test_id("reel-close-btn").click()
        page.get_by_test_id("reel-change-length").click()
        page.get_by_test_id("reel-60-btn").click()
        expect(page.get_by_test_id("reel-view-btn")).to_contain_text("60s")
        assert lengths == [30, 60], lengths
        assert not errors, (width, height, errors)
        ctx.close()
        browser.close()
        print(f"PASS: reel layout {width}×{height}", flush=True)
    print("PASS: mocked 30/60 reel choice, video preview, download and length switching across layouts")


def main():
    with sync_playwright() as playwright:
        # Default autoplay policy: do not disable the browser's restrictions.
        test_layout_matrix(playwright)
        tests = [
            lambda b: test_embedded_android_and_google(b, playwright),
            test_profile_dialogs,
            test_public_share_and_checkout,
            lambda b: test_android_touch(b, playwright),
            lambda b: test_audio_gestures(b, playwright),
        ]
        for test in tests:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                test(browser)
            finally:
                browser.close()
        test_theater_layouts(playwright)
        test_reel_dialog_and_download(playwright)


if __name__ == "__main__":
    main()
