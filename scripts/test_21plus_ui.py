#!/usr/bin/env python3
"""No-paid-call browser checks for the explicit 21+ gate and generator payloads."""
import io
import os
from PIL import Image
from playwright.sync_api import sync_playwright, expect
from ui_helpers import accept_adult_consent

APP = os.environ.get("ROASTBOX_TEST_ORIGIN", "http://127.0.0.1:3000").rstrip("/")
photo = io.BytesIO()
Image.new("RGB", (32, 32), "#c36a38").save(photo, "JPEG")


def run(browser, size):
    context = browser.new_context(viewport=size)
    # An older 18+ choice must not silently become a 21+ agreement.
    context.add_init_script("sessionStorage.setItem('roastbox_adult_consent_v1', 'accepted')")
    sent, errors = [], []
    def offline(route):
        sent.append((route.request.url, (route.request.post_data_buffer or b"").decode("utf-8", "replace")))
        route.fulfill(status=422, json={"detail": "Offline 21+ test: no AI or voice provider contacted."})
    context.route("**/api/roast/generate", offline)
    context.route("**/api/battle/generate", offline)
    context.route("**/api/personas/*/voice-preview*", lambda route: route.fulfill(status=403, json={"detail": "Offline"}))
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(APP, wait_until="domcontentloaded")
    skip = page.get_by_test_id("skip-intro-btn")
    if skip.count() and skip.is_visible(): skip.click()
    disclaimer = page.get_by_test_id("inline-disclaimer")
    expect(disclaimer).to_be_visible()
    expect(disclaimer).to_contain_text("21+")
    expect(page.get_by_test_id("disclaimer-checkbox")).not_to_be_checked()
    expect(page.get_by_test_id("enter-roast-btn")).to_be_disabled()
    accept_adult_consent(page)
    assert page.evaluate("sessionStorage.getItem('roastbox_adult_consent_21_v2')") == "accepted"
    page.get_by_test_id("preview-login-btn").click()
    page.wait_for_url("**/studio", timeout=20000)
    expect(page.get_by_test_id("adult-language-row")).to_contain_text("21+")
    page.get_by_test_id("persona-card-persona_1").locator(".persona-card-main").click()
    page.get_by_test_id("image-file-input").set_input_files({"name": "synthetic-adult-test.jpg", "mimeType": "image/jpeg", "buffer": photo.getvalue()})
    page.get_by_test_id("generate-roast-btn").click()
    expect(page.get_by_test_id("generate-roast-btn")).to_be_enabled(timeout=10000)
    assert len(sent) == 1
    body = sent[0][1]
    assert 'name="adult_subjects_confirmed"\r\n\r\ntrue' in body
    assert 'name="adult_language"\r\n\r\ntrue' in body
    page.get_by_test_id("adult-language-row").click()
    expect(page.get_by_test_id("adult-language-toggle")).not_to_be_checked()
    page.get_by_test_id("heat-mild-btn").click()
    page.get_by_test_id("generate-roast-btn").click()
    expect(page.get_by_test_id("generate-roast-btn")).to_be_enabled(timeout=10000)
    assert len(sent) == 2
    assert 'name="adult_language"\r\n\r\nfalse' in sent[1][1]
    assert 'name="heat"\r\n\r\nmild' in sent[1][1]
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    # A direct protected link in a new tab retains auth but requires its own explicit 21+ choice.
    fresh = context.new_page()
    fresh.goto(APP + "/studio", wait_until="domcontentloaded")
    expect(fresh.get_by_test_id("inline-disclaimer")).to_be_visible(timeout=15000)
    assert not fresh.get_by_test_id("roast-studio").count()
    fresh.close()
    page.goto(APP + "/battle", wait_until="domcontentloaded")
    expect(page.get_by_test_id("battle-page")).to_be_visible(timeout=15000)
    # Preview has battle entitlements; pick two different fictional adults.
    for pid in ("persona_1", "persona_2"):
        page.get_by_test_id("battle-persona-" + pid).locator(".persona-card-main").click()
    if not page.get_by_test_id("adult-language-toggle").is_checked():
        page.get_by_test_id("adult-language-row").click()
    expect(page.get_by_test_id("adult-language-toggle")).to_be_checked()
    page.get_by_test_id("battle-fight-btn").click()
    expect(page.get_by_test_id("battle-fight-btn")).to_be_enabled(timeout=10000)
    assert len(sent) == 3 and "/battle/generate" in sent[-1][0]
    assert 'name="adult_subjects_confirmed"\r\n\r\ntrue' in sent[-1][1]
    assert not errors, errors
    context.close()
    print(f"PASS: {size['width']}x{size['height']} 21+ renewal, explicit consent, roast/battle payload, clean/heat controls and tab isolation; all generation mocked", flush=True)


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            for size in ({"width": 1440, "height": 900}, {"width": 390, "height": 844}):
                run(browser, size)
        finally:
            browser.close()
