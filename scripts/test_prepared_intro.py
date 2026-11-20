#!/usr/bin/env python3
"""Intercepted splash/audio tests for a separately served prepared build.

ALL /api calls are fulfilled locally; every non-test-origin request is blocked.
No real login, DB, AI, voice, payment, email or cloud request can be made. Serve
an isolated build with API_PROXY_TARGET pointing to a non-live stub (not 8001).
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
APP = os.environ.get("ROASTBOX_TEST_ORIGIN", "http://127.0.0.1:3212").rstrip("/")
ORIGIN = urlsplit(APP).netloc
CATALOG = json.loads((ROOT / "backend/data/personas.json").read_text())
GATE = r"""(() => {
  window.__introPlays = 0;
  window.__introTrustedGesture = false;
  const grant = (event) => {
    if (event.isTrusted && (event.type !== 'keydown' || ['Enter', ' '].includes(event.key)))
      window.__introTrustedGesture = true;
  };
  window.addEventListener('pointerdown', grant, true);
  window.addEventListener('keydown', grant, true);
  const original = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function (...args) {
    if ((this.currentSrc || this.src).includes('hae-cinematic-swoosh')) {
      window.__introPlays++;
      if (!window.__introTrustedGesture)
        return Promise.reject(new DOMException('Autoplay blocked for fixture', 'NotAllowedError'));
    }
    return original.apply(this, args);
  };
})();"""


def context(browser, *, blocked=True, reduced="no-preference", mobile=False):
    ctx = browser.new_context(viewport={"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900},
                              reduced_motion=reduced, has_touch=mobile, is_mobile=mobile)
    stats = {"mock_api": [], "blocked_external": [], "errors": []}
    def guard(route):
        request = route.request
        parsed = urlsplit(request.url)
        if parsed.netloc != ORIGIN:
            stats["blocked_external"].append(request.url)
            route.abort("blockedbyclient")
        elif parsed.path.startswith("/api/"):
            stats["mock_api"].append({"method": request.method, "path": parsed.path})
            if parsed.path == "/api/auth/me":
                route.fulfill(status=401, json={"detail": "Fixture is not authenticated"})
            elif parsed.path == "/api/personas":
                route.fulfill(json=CATALOG)
            elif parsed.path == "/api/auth/email/status":
                route.fulfill(json={"login_available": False, "registration_available": False, "recovery_available": False})
            else:
                route.fulfill(json={})
        else:
            route.continue_()
    ctx.route("**/*", guard)
    if blocked:
        ctx.add_init_script(GATE)
    page = ctx.new_page()
    page.on("pageerror", lambda error: stats["errors"].append(str(error)))
    page.goto(APP, wait_until="domcontentloaded")
    expect(page.get_by_test_id("cinematic-intro")).to_be_visible()
    return ctx, page, stats


def synchronized(page):
    page.wait_for_function("""() => {
      const audio = document.querySelector('audio[src*="hae-cinematic-swoosh"]');
      return audio && !audio.paused && audio.currentTime > .12;
    }""", timeout=6000)
    timing = page.evaluate("""() => {
      const audio = document.querySelector('audio[src*="hae-cinematic-swoosh"]');
      const scene = document.querySelector('.hae-intro-scene');
      return {audio: audio.currentTime, visual: scene.getAnimations()[0]?.currentTime / 1000,
              paused: audio.paused, run: document.querySelector('[data-intro-run]').dataset.introRun};
    }""")
    if timing["visual"] is not None:
        assert abs(timing["audio"] - timing["visual"]) < .35, timing
    expect(page.get_by_test_id("intro-sound-btn")).to_have_text("Mute")
    return timing


def run_tests(browser):
    reports = []
    ctx, page, stats = context(browser)
    page.wait_for_timeout(1500)
    assert page.evaluate("window.__introPlays") >= 2
    assert page.evaluate("document.querySelector('audio[src*=hae-cinematic]').paused")
    expect(page.get_by_test_id("intro-sound-hint")).to_be_visible()
    page.evaluate("window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}))")
    assert page.get_by_test_id("cinematic-intro").get_attribute("data-intro-run") == "0"
    page.keyboard.press("Enter")
    timing = synchronized(page)
    assert timing["run"] == "1", timing
    page.keyboard.press("Space")
    assert page.get_by_test_id("cinematic-intro").get_attribute("data-intro-run") == "1"
    # A late unlock starts a new complete intro, not the old nearly-finished timer.
    page.wait_for_timeout(5400)
    expect(page.get_by_test_id("cinematic-intro")).to_be_visible()
    expect(page.get_by_test_id("cinematic-intro")).to_have_count(0, timeout=3000)
    expect(page.get_by_test_id("inline-disclaimer")).to_be_visible()
    assert page.get_by_test_id("enter-roast-btn").is_disabled()
    assert not stats["errors"], stats
    reports.append({"test": "blocked autoplay, synthetic-key rejection, real Enter, synchronized replay and renewed timer", "result": "PASS", "timing": timing})
    ctx.close()

    ctx, page, stats = context(browser)
    page.wait_for_timeout(350)
    page.keyboard.press("Space")
    timing = synchronized(page)
    page.get_by_test_id("intro-sound-btn").click()
    assert page.evaluate("document.querySelector('audio[src*=hae-cinematic]').paused")
    page.locator(".hae-intro").click(position={"x": 720, "y": 500})
    page.evaluate("document.activeElement?.blur()")
    page.keyboard.press("Enter")
    assert page.evaluate("document.querySelector('audio[src*=hae-cinematic]').paused")
    assert page.get_by_test_id("cinematic-intro").get_attribute("data-intro-run") == "1"
    page.get_by_test_id("intro-sound-btn").click()
    assert synchronized(page)["run"] == "2"
    page.keyboard.press("Escape")
    expect(page.get_by_test_id("cinematic-intro")).to_have_count(0)
    assert not stats["errors"], stats
    reports.append({"test": "real Space, explicit mute respected, explicit replay and Escape", "result": "PASS", "timing": timing})
    ctx.close()

    ctx, page, stats = context(browser, mobile=True)
    page.wait_for_timeout(700)
    page.touchscreen.tap(190, 400)
    timing = synchronized(page)
    assert timing["run"] == "1"
    size = page.evaluate("({width: document.documentElement.scrollWidth, viewport: innerWidth})")
    assert size["width"] <= size["viewport"] + 1
    page.get_by_test_id("skip-intro-btn").click()
    expect(page.get_by_test_id("inline-disclaimer")).to_be_visible()
    page.get_by_test_id("disclaimer-checkbox").check()
    expect(page.get_by_test_id("enter-roast-btn")).to_be_enabled()
    assert not stats["errors"], stats
    reports.append({"test": "trusted mobile tap, audio sync, fit and unchanged explicit 21+ gate", "result": "PASS", "timing": timing})
    ctx.close()

    ctx, page, stats = context(browser)
    page.wait_for_timeout(200)
    count = page.evaluate("window.__introPlays")
    page.get_by_test_id("skip-intro-btn").focus()
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("cinematic-intro")).to_have_count(0)
    assert page.evaluate("window.__introPlays") == count
    assert not stats["errors"], stats
    reports.append({"test": "keyboard activation of Skip never starts unwanted sound", "result": "PASS"})
    ctx.close()

    ctx, page, stats = context(browser, reduced="reduce", mobile=True)
    assert page.locator(".hae-water-fx").evaluate("element => getComputedStyle(element).display") == "none"
    expect(page.get_by_test_id("cinematic-intro")).to_have_count(0, timeout=5000)
    assert not stats["errors"], stats
    reports.append({"test": "reduced motion remains static and advances automatically", "result": "PASS"})
    ctx.close()

    ctx, page, stats = context(browser, blocked=False)
    timing = synchronized(page)
    assert timing["run"] == "0"
    assert not stats["errors"], stats
    reports.append({"test": "allowed autoplay starts without any key or tap", "result": "PASS", "timing": timing})
    ctx.close()
    return reports


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--autoplay-policy=no-user-gesture-required"])
        try:
            results = run_tests(browser)
        finally:
            browser.close()
    print(json.dumps({"tests": results, "real_api_requests": 0, "external_requests_allowed": 0,
                      "physical_windows_or_mobile_execution": False}, indent=2))
