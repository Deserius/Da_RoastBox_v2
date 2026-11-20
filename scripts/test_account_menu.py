#!/usr/bin/env python3
"""Offline account-menu checks against the running Da RoastBox preview.

Local preview login and mock account-history fixtures only: no AI, Stripe,
Google or social-media requests are made. Phone layouts are emulated.
"""
from __future__ import annotations

from ui_helpers import accept_adult_consent, accept_adult_consent_async

import json
import os
from playwright.sync_api import expect, sync_playwright

APP = os.environ.get("ROASTBOX_TEST_ORIGIN", "http://127.0.0.1:3000").rstrip("/")


def enter(page):
    page.goto(APP, wait_until="domcontentloaded")
    accept_adult_consent(page)
    page.get_by_test_id("preview-login-btn").click()
    page.wait_for_url("**/studio", timeout=20000)
    page.get_by_test_id("persona-card-persona_1").wait_for(timeout=15000)
    page.evaluate("window.scrollTo(0, 0)")


def test_layouts(browser):
    cases = [(200, 400), (240, 568), (280, 653), (320, 568), (412, 839), (568, 320),
             (844, 390), (768, 1024), (1024, 768), (1440, 900), (2560, 1440)]
    for width, height in cases:
        touch = width < 1100
        ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=touch, has_touch=touch,
                                  reduced_motion="reduce")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        enter(page)
        toggle = page.get_by_test_id("menu-toggle")
        box = toggle.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1 and box["y"] >= 0, (width, height, box)
        assert box["width"] >= 44 and box["height"] >= 44
        # The storybook must have exactly one navigation entry: inside the drawer.
        assert page.get_by_test_id("nav-about-author-btn").count() == 0
        assert page.get_by_test_id("about-author-trigger").count() == 0
        toggle.click()
        drawer = page.get_by_test_id("account-menu")
        drawer.wait_for()
        bounds = drawer.evaluate("""e => { const r=e.getBoundingClientRect(), close=e.querySelector('[data-testid=menu-close]').getBoundingClientRect();
          return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,scroll:e.scrollWidth,client:e.clientWidth,
                  closeTop:close.top,closeBottom:close.bottom,closeRight:close.right,viewport:innerWidth}; }""")
        assert bounds["left"] >= -1 and bounds["right"] <= width + 1 and bounds["top"] >= -1 and bounds["bottom"] <= height + 1, (width, height, bounds)
        assert bounds["scroll"] <= bounds["client"] + 1 and bounds["viewport"] == width, (width, height, bounds)
        assert bounds["closeTop"] >= 0 and bounds["closeBottom"] <= height + 1 and bounds["closeRight"] <= width + 1, (width, height, bounds)
        expect(page.get_by_test_id("menu-profile-name")).to_have_text("Preview Guest")
        for testid in ["menu-nav-studio", "menu-nav-roasters", "menu-nav-battle", "menu-nav-credits", "menu-nav-settings", "menu-about-developer-btn", "menu-logout"]:
            assert page.get_by_test_id(testid).count() == 1, (width, testid)
        # Close remains reachable even after scrolling deep into the panel.
        drawer.evaluate("e => e.scrollTop = e.scrollHeight")
        close = page.get_by_test_id("menu-close").bounding_box()
        assert close and close["y"] >= 0 and close["y"] + close["height"] <= height + 1, (width, height, close)
        page.get_by_test_id("menu-close").click()
        expect(drawer).to_have_count(0)
        assert not errors, (width, height, errors)
        ctx.close()
        print(f"PASS: top-right menu and responsive drawer {width}×{height}", flush=True)


def test_menu_history_help_and_navigation(browser):
    ctx = browser.new_context(viewport={"width": 412, "height": 839}, is_mobile=True, has_touch=True,
                              reduced_motion="reduce")
    calls = []
    fixture = {"limit": 20,
               "payments": [{"id": "purchase-1", "product_name": "Starter Pack", "amount_usd": 4.99,
                             "payment_status": "paid", "created_at": "2026-01-02T12:00:00+00:00"}],
               "shows": [{"id": "show-1", "mode": "roast", "subject_name": "Test Guest", "credits_spent": 5,
                          "was_free_roast": False, "created_at": "2026-01-02T12:00:00+00:00"}],
               "credit_activity": [{"id": "ledger-1", "amount": -5, "type": "spend", "description": "Standard Roast",
                                    "created_at": "2026-01-02T12:00:00+00:00"}]}
    def intercept(route):
        calls.append(route.request.url)
        if len(calls) == 1: route.fulfill(status=503, content_type="application/json", body='{"detail":"Offline fixture"}')
        else: route.fulfill(status=200, content_type="application/json", body=json.dumps(fixture))
    ctx.route("**/api/payments/activity", intercept)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    enter(page)
    page.get_by_test_id("subject-name-input").fill("Draft survives")
    page.get_by_test_id("menu-toggle").tap()
    page.get_by_test_id("menu-about-developer-btn").tap()
    expect(page.get_by_test_id("author-cover")).to_be_visible()
    page.get_by_test_id("author-close").tap()
    page.get_by_test_id("menu-close").tap()
    assert page.get_by_test_id("subject-name-input").input_value() == "Draft survives"

    page.get_by_test_id("menu-toggle").tap()
    assert calls == [], "History must load on demand rather than whenever the menu opens"
    page.get_by_test_id("payment-history-section").locator("summary").tap()
    expect(page.get_by_test_id("payment-history")).to_contain_text("Couldn't load history")
    page.get_by_test_id("payment-history").get_by_role("button", name="Try again").tap()
    expect(page.get_by_test_id("payment-history")).to_contain_text("Starter Pack")
    expect(page.get_by_test_id("payment-history")).to_contain_text("$4.99")
    expect(page.get_by_test_id("payment-history")).to_contain_text("Paid")
    page.get_by_test_id("usage-history-section").locator("summary").tap()
    expect(page.get_by_test_id("usage-history")).to_contain_text("Test Guest")
    expect(page.get_by_test_id("usage-history")).to_contain_text("Standard Roast")
    expect(page.get_by_test_id("usage-history")).to_contain_text("-5 cr")
    assert len(calls) == 2, "One retry should serve both histories without another request"
    page.get_by_test_id("help-section").locator("summary").tap()
    expect(page.get_by_test_id("help-section")).to_contain_text("contact details haven't been set up")
    socials = page.locator(".account-social-row a")
    assert socials.count() == 4
    assert socials.nth(0).get_attribute("href") == "https://www.instagram.com/"
    assert all(socials.nth(i).get_attribute("target") == "_blank" for i in range(4))
    assert all("not an official profile" in socials.nth(i).get_attribute("aria-label") for i in range(4))
    expect(page.locator(".account-socials")).to_contain_text("not official Da RoastBox profiles")
    # Opening the nested book returns to the drawer; neither action resets the draft.
    page.get_by_test_id("menu-about-developer-btn").tap()
    expect(page.get_by_test_id("author-cover")).to_be_visible()
    page.get_by_test_id("author-close").tap()
    expect(page.get_by_test_id("account-menu")).to_be_visible()
    page.get_by_test_id("menu-close").tap()
    assert page.get_by_test_id("subject-name-input").input_value() == "Draft survives"
    assert not errors, errors
    ctx.close()
    print("PASS: menu-only About Developer link, on-demand payment/usage history, retry, help, social labels and preserved draft", flush=True)

    ctx = browser.new_context(viewport={"width": 412, "height": 839}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    enter(page)
    for name, path, testid in [("battle", "battle", "battle-page"), ("credits", "credits", "credits-page"),
                               ("settings", "settings", "settings-page"), ("roasters", "roasters", "roasters-page"),
                               ("studio", "studio", "roast-studio")]:
        page.get_by_test_id("menu-toggle").tap()
        page.get_by_test_id(f"menu-nav-{name}").tap()
        page.wait_for_url(f"**/{path}", timeout=15000)
        page.get_by_test_id(testid).wait_for(timeout=15000)
        expect(page.get_by_test_id("account-menu")).to_have_count(0)
    page.get_by_test_id("menu-toggle").tap()
    page.get_by_test_id("menu-logout").tap()
    page.wait_for_url(f"{APP}/", timeout=15000)
    expect(page.get_by_test_id("splash-screen")).to_be_visible()
    ctx.close()
    print("PASS: all menu routes and logout work", flush=True)


def test_keyboard_and_empty_history(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    enter(page)
    page.get_by_test_id("menu-toggle").click()
    for _ in range(12):
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.closest('[data-testid=account-menu]') !== null")
    page.keyboard.press("Escape")
    expect(page.get_by_test_id("account-menu")).to_have_count(0)
    expect(page.get_by_test_id("menu-toggle")).to_be_focused()
    page.get_by_test_id("menu-toggle").click()
    page.get_by_test_id("payment-history-section").locator("summary").click()
    expect(page.get_by_test_id("payment-history")).to_contain_text("No payment history yet")
    page.get_by_test_id("usage-history-section").locator("summary").click()
    expect(page.get_by_test_id("usage-history")).to_contain_text("No usage history yet")
    page.get_by_test_id("menu-close").click()
    ctx.close()
    print("PASS: keyboard focus/Escape and real empty preview-account history", flush=True)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            test_layouts(browser)
            test_menu_history_help_and_navigation(browser)
            test_keyboard_and_empty_history(browser)
        finally:
            browser.close()
    print("Account menu offline checks completed successfully.")


if __name__ == "__main__":
    main()
