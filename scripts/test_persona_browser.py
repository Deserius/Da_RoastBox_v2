#!/usr/bin/env python3
"""Browser tests for persona favorites, discovery, dialogs and audio.

Requires the preview frontend/API. All voice preview requests are intercepted;
no paid AI or voice provider is called.
"""
from __future__ import annotations

from ui_helpers import accept_adult_consent, accept_adult_consent_async

import io
import math
import os
import re
import struct
import wave
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

APP = os.environ.get("ROASTBOX_TEST_ORIGIN", "http://127.0.0.1:3000").rstrip("/")
OUT = Path("/home/user/.cache/da-roastbox")
OUT.mkdir(parents=True, exist_ok=True)


def tone(seconds=5):
    data = io.BytesIO()
    with wave.open(data, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"".join(struct.pack("<h", int(800 * math.sin(2 * math.pi * 260 * i / 16000)))
                                 for i in range(int(16000 * seconds))))
    return data.getvalue()


VOICE = tone()


def fake_voices(context, calls, fail_first=False):
    def preview(route):
        parsed = urlparse(route.request.url)
        sample = int(parse_qs(parsed.query).get("sample", [0])[0])
        calls.append((parsed.path, sample))
        if fail_first and len(calls) == 1:
            route.fulfill(status=429, json={"detail": "Preview voice limit reached. Try again later."})
        else:
            route.fulfill(json={"audio_url": f"/api/test-voice/sample-{sample}", "sample": sample})
    context.route(re.compile(r".*/api/personas/[^/]+/voice-preview(?:\?.*)?$"), preview)
    context.route("**/api/test-voice/**", lambda route: route.fulfill(body=VOICE, content_type="audio/wav"))


def login(page):
    page.goto(APP, wait_until="domcontentloaded")
    accept_adult_consent(page)
    page.get_by_test_id("preview-login-btn").click()
    page.wait_for_url("**/studio", timeout=20000)
    page.get_by_test_id("persona-card-persona_1").wait_for(timeout=20000)
    expect(page.get_by_test_id("persona-favorite-persona_1")).to_be_enabled(timeout=15000)


def open_info(page, persona="persona_1"):
    page.get_by_test_id(f"persona-info-{persona}").click()
    page.get_by_test_id("persona-detail-modal").wait_for()


def test_catalog_and_favorites(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    calls = []
    fake_voices(ctx, calls)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    login(page)
    favorite1 = page.get_by_test_id("persona-favorite-persona_1")
    favorite2 = page.get_by_test_id("persona-favorite-persona_2")
    expect(favorite1).to_have_attribute("aria-pressed", "false")
    assert page.get_by_test_id("persona-card-persona_1").locator(".persona-card-main").get_attribute("aria-pressed") == "false"
    # The info icon and favorite star must not select a roaster.
    open_info(page)
    assert page.get_by_test_id("persona-detail-name").inner_text() == "Big Sun-K"
    modal = page.get_by_test_id("persona-detail-modal")
    assert modal.get_by_text("THE BIO").is_visible()
    assert modal.get_by_text("TOPICS THEY HIT").is_visible()
    assert modal.get_by_text("SIGNATURE LINGO").is_visible()
    assert modal.get_by_test_id("persona-sample-0").is_visible()
    assert modal.get_by_test_id("persona-sample-1").is_visible()
    assert calls == [], "Opening a profile must not call the paid voice provider"
    page.screenshot(path=str(OUT / "persona-dialog-desktop.png"))
    modal.get_by_test_id("persona-voice-preview-btn").click()
    expect(modal.get_by_text("NOW PLAYING")).to_be_visible(timeout=10000)
    assert calls == [("/api/personas/persona_1/voice-preview", 0)], calls
    modal.get_by_test_id("persona-voice-preview-1").click()
    expect(modal.get_by_test_id("persona-sample-1").get_by_text("NOW PLAYING")).to_be_visible(timeout=10000)
    assert calls[-1] == ("/api/personas/persona_1/voice-preview", 1)
    modal.get_by_test_id("persona-voice-preview-1").click()
    expect(modal.get_by_test_id("persona-sample-1").get_by_text("SAMPLE 2")).to_be_visible()
    page.keyboard.press("Escape")
    expect(modal).not_to_be_visible()
    expect(page.get_by_test_id("persona-info-persona_1")).to_be_focused()
    assert page.get_by_test_id("persona-card-persona_1").locator(".persona-card-main").get_attribute("aria-pressed") == "false"

    favorite1.click()
    expect(favorite1).to_have_attribute("aria-pressed", "true")
    expect(favorite1).to_be_enabled()
    favorite2.click()
    expect(favorite2).to_have_attribute("aria-pressed", "true")
    expect(favorite2).to_be_enabled()
    assert page.get_by_test_id("persona-card-persona_1").locator(".persona-card-main").get_attribute("aria-pressed") == "false"
    page.get_by_test_id("nav-roasters-btn").click()
    page.get_by_test_id("roasters-page").wait_for()
    expect(page.get_by_test_id("persona-favorite-persona_1")).to_have_attribute("aria-pressed", "true")
    page.screenshot(path=str(OUT / "persona-gallery-desktop.png"), full_page=False)
    page.get_by_test_id("persona-tab-favorites").click()
    expect(page.locator('[data-testid^="roaster-card-"]')).to_have_count(2)
    page.reload(wait_until="domcontentloaded")
    page.get_by_test_id("persona-tab-favorites").click()
    expect(page.locator('[data-testid^="roaster-card-"]')).to_have_count(2, timeout=15000)
    page.get_by_test_id("persona-favorite-persona_1").click()
    expect(page.locator('[data-testid^="roaster-card-"]')).to_have_count(1)
    page.get_by_test_id("persona-tab-all").click()
    page.get_by_test_id("persona-search").fill("dating disasters")
    expect(page.get_by_test_id("roaster-card-persona_1")).to_be_visible()
    page.get_by_test_id("persona-search").fill("zzzzno_such_roaster")
    expect(page.get_by_test_id("persona-empty")).to_contain_text("No roasters found")
    page.get_by_role("button", name="See all roasters").click()
    page.get_by_test_id("persona-tab-premium").click()
    expect(page.locator('[data-testid^="roaster-card-"]')).to_have_count(15)
    page.get_by_test_id("persona-access-filter").select_option("locked")
    expect(page.get_by_test_id("persona-empty")).to_contain_text("No roasters found")
    page.get_by_role("button", name="See all roasters").click()
    page.get_by_test_id("persona-access-filter").select_option("gender:female")
    expect(page.get_by_test_id("roaster-card-persona_2")).to_be_visible()
    expect(page.get_by_test_id("roaster-card-persona_1")).to_have_count(0)
    page.get_by_test_id("persona-access-filter").select_option("all")
    page.get_by_test_id("persona-tab-all").focus()
    page.keyboard.press("ArrowRight")
    expect(page.get_by_test_id("persona-tab-free")).to_have_attribute("aria-selected", "true")
    page.get_by_test_id("persona-tab-all").click()
    page.get_by_test_id("persona-sort").select_option("name")
    names = page.locator('.persona-grid .persona-card .name').all_text_contents()
    assert names == sorted(names, key=str.casefold), names
    page.get_by_test_id("brand-link").click()
    page.get_by_test_id("persona-tab-favorites").click()
    expect(page.locator('[data-testid^="persona-card-persona_"]')).to_have_count(1)
    page.get_by_test_id("persona-card-persona_2").locator(".persona-card-main").click()
    expect(page.get_by_test_id("persona-card-persona_2").locator(".persona-card-main")).to_have_attribute("aria-pressed", "true")
    page.get_by_test_id("nav-battle-btn").click()
    page.get_by_test_id("battle-persona-persona_2").wait_for()
    expect(page.get_by_test_id("persona-favorite-persona_2")).to_have_attribute("aria-pressed", "true")
    open_info(page, "persona_2")
    page.get_by_test_id("persona-detail-pick-btn").click()
    expect(page.get_by_test_id("battle-persona-persona_2").locator(".persona-card-main")).to_have_attribute("aria-pressed", "true")
    assert not errors, errors
    ctx.close()
    print("PASS: account-saved favorites, search/tabs/filters, two voice samples, modal actions and Studio/Battle/Roasters")


def test_isolation_and_errors(browser):
    ctx = browser.new_context(viewport={"width": 1100, "height": 850})
    calls = []
    fake_voices(ctx, calls, fail_first=True)
    page = ctx.new_page()
    login(page)
    page.get_by_test_id("persona-tab-favorites").click()
    expect(page.get_by_test_id("persona-empty")).to_contain_text("No favorites yet")
    page.get_by_role("button", name="See all roasters").click()
    assert page.get_by_test_id("persona-favorite-persona_1").get_attribute("aria-pressed") == "false"
    open_info(page)
    page.get_by_test_id("persona-voice-preview-btn").click()
    expect(page.get_by_test_id("persona-detail-modal").get_by_role("alert")).to_contain_text("voice limit reached")
    expect(page.get_by_test_id("persona-voice-preview-btn")).to_be_enabled()
    page.get_by_test_id("persona-voice-preview-btn").click()
    expect(page.get_by_text("NOW PLAYING")).to_be_visible(timeout=10000)
    page.get_by_test_id("persona-detail-close-btn").click()
    ctx.route("**/api/personas/favorites/persona_1", lambda route: route.fulfill(status=503, json={"detail": "offline"}))
    favorite = page.get_by_test_id("persona-favorite-persona_1")
    favorite.click()
    expect(page.get_by_test_id("toast-error")).to_contain_text("Couldn't save that favorite")
    expect(favorite).to_have_attribute("aria-pressed", "false")
    ctx.close()
    print("PASS: separate preview accounts have separate favorites; save and voice errors recover visibly")


def test_mobile(browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, device_scale_factor=1)
    calls = []
    fake_voices(ctx, calls)
    page = ctx.new_page()
    login(page)
    page.get_by_test_id("nav-roasters-btn").click()
    page.get_by_test_id("roaster-card-persona_1").wait_for()
    info = page.get_by_test_id("persona-info-persona_1")
    star = page.get_by_test_id("persona-favorite-persona_1")
    assert info.is_visible() and star.is_visible()
    info.click()
    modal = page.get_by_test_id("persona-detail-modal")
    modal.wait_for()
    box = modal.bounding_box()
    assert box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= 390.5 and box["y"] + box["height"] <= 844.5, box
    page.screenshot(path=str(OUT / "persona-dialog-mobile.png"))
    modal.get_by_test_id("persona-voice-preview-1").scroll_into_view_if_needed()
    modal.get_by_test_id("persona-voice-preview-1").click()
    expect(modal.get_by_test_id("persona-sample-1").get_by_text("NOW PLAYING")).to_be_visible(timeout=10000)
    modal.get_by_test_id("persona-detail-close-btn").click()
    expect(modal).not_to_be_visible()
    star.click()
    expect(star).to_have_attribute("aria-pressed", "true")
    page.get_by_test_id("persona-tab-favorites").click()
    expect(page.locator('[data-testid^="roaster-card-"]')).to_have_count(1)
    ctx.close()
    print("PASS: mobile card controls, responsive profile, sample playback and favorites")


def test_stripped_auth(browser):
    ctx = browser.new_context()
    dispatches = []
    def strip(route):
        headers = dict(route.request.all_headers())
        headers.pop("authorization", None)
        headers.pop("x-roastbox-session", None)
        headers["cookie"] = ""
        if "/api/session/dispatch" in route.request.url:
            dispatches.append(True)
        route.fulfill(response=route.fetch(headers=headers))
    ctx.route("**/api/**", strip)
    page = ctx.new_page()
    login(page)
    favorite = page.get_by_test_id("persona-favorite-persona_1")
    favorite.click()
    expect(favorite).to_have_attribute("aria-pressed", "true")
    expect(favorite).to_be_enabled()
    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_test_id("persona-favorite-persona_1")).to_have_attribute("aria-pressed", "true", timeout=15000)
    assert len(dispatches) >= 4
    ctx.close()
    print("PASS: favorites persist when the preview proxy strips all session headers and cookies")


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
        try:
            test_catalog_and_favorites(browser)
            test_isolation_and_errors(browser)
            test_mobile(browser)
            test_stripped_auth(browser)
        finally:
            browser.close()
