#!/usr/bin/env python3
"""Verify preview login and navigation with a real local API and MongoDB.

The app must be running at ROASTBOX_TEST_ORIGIN (default localhost:3000).
Requires Python Playwright and Chromium. No real providers or purchases are used.
"""
from __future__ import annotations

from ui_helpers import accept_adult_consent, accept_adult_consent_async

import asyncio
import os
import re

from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright

APP = os.environ.get("ROASTBOX_TEST_ORIGIN", "http://127.0.0.1:3000").rstrip("/")


def embedded(context, width=1100, height=650):
    page = context.new_page()
    page.set_content(f'<iframe src="{APP}/" style="width:{width}px;height:{height}px"></iframe>')
    frame = page.frame(url=re.compile("^" + re.escape(APP)))
    if frame is None:
        page.wait_for_timeout(500)
        frame = page.frame(url=re.compile("^" + re.escape(APP)))
    assert frame is not None
    frame.get_by_test_id("splash-screen").wait_for(timeout=20000)
    return page, frame


def test_agreement_and_navigation(browser):
    context = browser.new_context()
    calls = []

    def observe(request):
        if "/api/auth/preview-login" in request.url:
            calls.append(request.url)

    page, frame = embedded(context)
    page.on("request", observe)
    frame.get_by_test_id("skip-intro-btn").click()
    frame.get_by_test_id("inline-disclaimer").wait_for()
    assert frame.get_by_test_id("enter-roast-btn").is_disabled()
    assert not calls, "Age agreement must gate preview login"
    accept_adult_consent(frame)
    frame.get_by_test_id("preview-login-btn").click()
    frame.wait_for_url("**/studio", timeout=20000)
    frame.get_by_test_id("roast-studio").wait_for()
    assert "Preview" in frame.get_by_test_id("credit-pill").inner_text()
    for button, test_id, path in [
        ("nav-roasters-btn", "roasters-page", "/roasters"),
        ("nav-battle-btn", "battle-page", "/battle"),
        ("nav-credits-btn", "credits-page", "/credits"),
        ("nav-settings-btn", "settings-page", "/settings"),
        ("brand-link", "roast-studio", "/studio"),
    ]:
        frame.get_by_test_id(button).click()
        frame.wait_for_url("**" + path, timeout=15000)
        frame.get_by_test_id(test_id).wait_for(timeout=15000)
    frame.goto(APP + "/credits/success", wait_until="domcontentloaded")
    frame.get_by_test_id("checkout-success").get_by_role("alert").wait_for()
    assert "No checkout session" in frame.get_by_test_id("checkout-success").get_by_role("alert").inner_text()
    frame.get_by_role("button", name="Back to Packs").click()
    frame.get_by_test_id("credits-page").wait_for()
    frame.get_by_test_id("logout-btn").click()
    frame.wait_for_url(APP + "/", timeout=10000)
    frame.get_by_test_id("splash-screen").wait_for()
    context.close()
    print("PASS: agreement gate, preview entry, main navigation, checkout return and logout")


def test_proxy_strips_bearer_and_cookie(browser):
    context = browser.new_context()
    sent_app_header = []

    def strip(route):
        headers = dict(route.request.all_headers())
        headers.pop("authorization", None)
        headers["cookie"] = ""
        if "/api/auth/me" in route.request.url and headers.get("x-roastbox-session"):
            sent_app_header.append(True)
        route.fulfill(response=route.fetch(headers=headers))

    context.route("**/api/**", strip)
    page, frame = embedded(context)
    accept_adult_consent(frame)
    frame.get_by_test_id("preview-login-btn").click()
    frame.wait_for_url("**/studio", timeout=20000)
    frame.get_by_test_id("roast-studio").wait_for()
    assert sent_app_header, "Expected app session header through the proxy"
    frame.get_by_test_id("nav-battle-btn").click()
    frame.get_by_test_id("battle-page").wait_for()
    frame.get_by_test_id("nav-settings-btn").click()
    frame.get_by_test_id("settings-page").wait_for()
    frame.get_by_test_id("logout-btn").click()
    frame.get_by_test_id("splash-screen").wait_for()
    context.unroute_all(behavior="wait")
    context.close()
    print("PASS: embedded preview works when the proxy strips Authorization and cookies")


def test_proxy_strips_all_session_transports(browser):
    context = browser.new_context()
    dispatches = []
    def strip_all(route):
        headers = dict(route.request.all_headers())
        headers.pop("authorization", None)
        headers.pop("x-roastbox-session", None)
        headers["cookie"] = ""
        if "/api/session/dispatch" in route.request.url:
            dispatches.append(route.request.method)
        route.fulfill(response=route.fetch(headers=headers))
    context.route("**/api/**", strip_all)
    page, frame = embedded(context)
    accept_adult_consent(frame)
    frame.get_by_test_id("preview-login-btn").click()
    frame.wait_for_url("**/studio", timeout=20000)
    frame.get_by_test_id("persona-card-persona_1").wait_for()
    frame.get_by_test_id("nav-battle-btn").click()
    frame.get_by_test_id("battle-persona-persona_1").wait_for()
    frame.get_by_test_id("nav-credits-btn").click()
    frame.get_by_test_id("pack-credits_starter").wait_for()
    frame.get_by_test_id("nav-settings-btn").click()
    frame.get_by_test_id("openai-key-input").fill("sk-offline-browser-test")
    frame.get_by_test_id("save-keys-btn").click()
    frame.get_by_text("Keys saved (encrypted at rest)").wait_for()
    frame.get_by_test_id("clear-keys-btn").click()
    frame.get_by_text("BYOK keys cleared. Using app defaults.").wait_for()
    frame.get_by_test_id("logout-btn").click()
    frame.get_by_test_id("splash-screen").wait_for()
    assert len(dispatches) >= 6 and set(dispatches) == {"POST"}, dispatches
    context.unroute_all(behavior="wait")
    context.close()
    print("PASS: preview navigation and authenticated writes work when every session header and cookie is stripped")


def test_no_browser_storage(browser):
    context = browser.new_context()
    context.add_init_script("""Object.defineProperty(window, 'localStorage', {
      configurable: true, get() { throw new DOMException('Blocked by browser', 'SecurityError'); }
    });""")
    page, frame = embedded(context)
    accept_adult_consent(frame)
    frame.get_by_test_id("preview-login-btn").click()
    frame.wait_for_url("**/studio", timeout=20000)
    frame.get_by_test_id("nav-roasters-btn").click()
    frame.get_by_test_id("roasters-page").wait_for()
    frame.get_by_test_id("nav-settings-btn").click()
    frame.get_by_test_id("settings-page").wait_for()
    frame.get_by_test_id("logout-btn").click()
    frame.get_by_test_id("splash-screen").wait_for()
    context.close()
    print("PASS: in-memory session supports navigation when localStorage is blocked")


def test_visible_failed_session(browser):
    context = browser.new_context()
    context.route("**/api/auth/me", lambda route: route.fulfill(status=401, content_type="application/json", body='{"detail":"Not authenticated"}'))
    context.route("**/api/session/dispatch", lambda route: route.fulfill(status=401, content_type="application/json", body='{"detail":"Not authenticated"}'))
    page, frame = embedded(context)
    accept_adult_consent(frame)
    frame.get_by_test_id("preview-login-btn").click()
    frame.get_by_test_id("preview-login-error").wait_for(timeout=15000)
    assert "couldn't be verified" in frame.get_by_test_id("preview-login-error").inner_text()
    assert frame.get_by_test_id("preview-login-btn").is_enabled()
    context.close()
    print("PASS: failed preview session shows an actionable error instead of silently staying on splash")


def test_api_errors_and_retry(browser):
    context = browser.new_context()
    failed = {"personas": True, "quote": False, "battle": False, "packs": False}

    def maybe_fail(route):
        url = route.request.url
        kind = ("personas" if "/api/personas" in url else "quote" if "/api/roast/cost-quote" in url
                else "battle" if "/api/battle/access" in url else "packs" if "/api/payments/packs" in url else "")
        if kind and failed[kind]:
            route.fulfill(status=503, content_type="application/json", body='{"detail":"offline-test"}')
        else:
            route.continue_()

    context.route("**/api/**", maybe_fail)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(APP, wait_until="domcontentloaded")
    accept_adult_consent(page)
    page.get_by_test_id("preview-login-btn").click()
    page.wait_for_url("**/studio", timeout=20000)
    page.get_by_test_id("api-load-error").wait_for()
    failed["personas"] = False
    page.get_by_test_id("api-load-error").get_by_role("button", name="Retry").click()
    page.get_by_test_id("persona-card-persona_1").wait_for()

    failed["quote"] = True
    page.get_by_test_id("tier-premium-btn").click()
    page.get_by_test_id("api-load-error").wait_for()
    assert page.get_by_test_id("generate-roast-btn").is_disabled()
    failed["quote"] = False
    page.get_by_test_id("api-load-error").get_by_role("button", name="Retry").click()
    page.get_by_test_id("generate-roast-btn").wait_for(state="visible")
    page.wait_for_function("!document.querySelector('[data-testid=generate-roast-btn]').disabled")

    failed["personas"] = True
    page.get_by_test_id("nav-roasters-btn").click()
    page.get_by_test_id("api-load-error").wait_for()
    failed["personas"] = False
    page.get_by_test_id("api-load-error").get_by_role("button", name="Retry").click()
    page.get_by_test_id("roaster-grid").locator(".persona-card").first.wait_for()

    failed["battle"] = True
    page.get_by_test_id("nav-battle-btn").click()
    page.get_by_test_id("api-load-error").wait_for()
    failed["battle"] = False
    page.get_by_test_id("api-load-error").get_by_role("button", name="Retry").click()
    page.get_by_test_id("battle-persona-persona_1").wait_for()

    failed["packs"] = True
    page.get_by_test_id("nav-credits-btn").click()
    page.get_by_test_id("api-load-error").wait_for()
    failed["packs"] = False
    page.get_by_test_id("api-load-error").get_by_role("button", name="Retry").click()
    page.get_by_test_id("pack-credits_starter").wait_for()
    assert not errors, errors
    context.unroute_all(behavior="wait")
    context.close()
    print("PASS: roster, quote, battle and catalog errors show retry UI and recover")


def test_mobile(browser):
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.goto(APP, wait_until="domcontentloaded")
    accept_adult_consent(page)
    page.get_by_test_id("preview-login-btn").click()
    page.wait_for_url("**/studio", timeout=20000)
    page.get_by_test_id("nav-roasters-btn").click()
    page.get_by_test_id("roasters-page").wait_for()
    dims = page.evaluate("({width:document.documentElement.clientWidth, scroll:document.documentElement.scrollWidth})")
    assert dims["scroll"] <= dims["width"] + 1, dims
    context.close()
    print("PASS: mobile preview login and navigation without horizontal overflow")


async def test_late_anonymous_response():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        anonymous_started = asyncio.Event()

        async def delay_initial(route):
            headers = await route.request.all_headers()
            if not headers.get("x-roastbox-session"):
                anonymous_started.set()
                await asyncio.sleep(2.5)
                await route.fulfill(status=401, content_type="application/json", body='{"detail":"Not authenticated"}')
            else:
                await route.continue_()

        await context.route("**/api/auth/me", delay_initial)
        page = await context.new_page()
        await page.goto(APP, wait_until="domcontentloaded")
        await asyncio.wait_for(anonymous_started.wait(), timeout=15)
        await accept_adult_consent_async(page)
        await page.get_by_test_id("preview-login-btn").click()
        await page.wait_for_url("**/studio", timeout=20000)
        await asyncio.sleep(3)
        assert page.url.endswith("/studio"), page.url
        await page.get_by_test_id("roast-studio").wait_for()
        await context.unroute_all(behavior="wait")
        await context.close()
        await browser.close()
    print("PASS: a late anonymous session response cannot overwrite a successful login")


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        test_agreement_and_navigation(browser)
        test_proxy_strips_bearer_and_cookie(browser)
        test_proxy_strips_all_session_transports(browser)
        test_no_browser_storage(browser)
        test_visible_failed_session(browser)
        test_api_errors_and_retry(browser)
        test_mobile(browser)
        browser.close()
    asyncio.run(test_late_anonymous_response())
