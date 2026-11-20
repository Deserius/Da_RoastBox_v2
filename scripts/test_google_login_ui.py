#!/usr/bin/env python3
"""Browser checks for managed Google sign-in without using a real Google account.

Start the app on localhost:3000, install Python Playwright and its Chromium
browser, then run this script. It mocks the identity exchange and verifies both
regular redirect and embedded-popup paths, including rejected forged states.
Set LIVE_GOOGLE_SMOKE=1 to additionally follow the actual provider to Google's
sign-in screen; no credentials or consent are entered by this script.
"""
from __future__ import annotations

from ui_helpers import accept_adult_consent, accept_adult_consent_async

import json
import os
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.sync_api import sync_playwright

APP = os.environ.get("ROASTBOX_TEST_ORIGIN", "http://127.0.0.1:3000").rstrip("/")
PROVIDER_START = "https://demobackend.emergentagent.com/auth/v1/env/oauth"
USER = {"id": "ui-google-test", "email": "user@example.invalid", "name": "Test User", "credits": 5}
TOKEN = "ui-test-app-session-not-a-real-token"


def make_context(browser, exchange_status=200, **context_options):
    context = browser.new_context(**context_options)
    calls = []

    def fake_provider(route):
        route.fulfill(status=200, content_type="text/html", body="<h1>Offline provider</h1>")

    def fake_exchange(route):
        calls.append(("session", route.request.post_data_json))
        if exchange_status == 200:
            body = {"session_token": TOKEN, "user": USER}
        else:
            body = {"detail": "The provider rejected the session"}
        route.fulfill(status=exchange_status, content_type="application/json", body=json.dumps(body))

    def fake_me(route):
        bearer = route.request.headers.get("authorization")
        calls.append(("me", bearer))
        if bearer == f"Bearer {TOKEN}":
            route.fulfill(status=200, content_type="application/json", body=json.dumps(USER))
        else:
            route.fulfill(status=401, content_type="application/json", body='{"detail":"Not authenticated"}')

    context.route(PROVIDER_START + "**", fake_provider)
    context.route("**/api/auth/session", fake_exchange)
    context.route("**/api/auth/me", fake_me)
    return context, calls


def callback_for(provider_url):
    query = parse_qs(urlparse(provider_url).query)
    callback = query["redirect"][0]
    parsed = urlparse(callback)
    params = parse_qs(parsed.query)
    assert parsed.path == "/auth-complete.html"
    assert len(params["state"][0]) >= 64
    return callback, params


def replace_state(callback, new_state):
    parsed = urlparse(callback)
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    params["state"] = new_state
    return urlunparse(parsed._replace(query=urlencode(params)))


def enter(page_or_frame):
    accept_adult_consent(page_or_frame)
    page_or_frame.get_by_test_id("splash-login-btn").click()


def direct_success(browser):
    context, calls = make_context(browser)
    page = context.new_page()
    page.goto(APP, wait_until="domcontentloaded")
    enter(page)
    page.wait_for_url(PROVIDER_START + "**")
    callback, params = callback_for(page.url)
    assert params["mode"] == ["redirect"]
    page.goto(callback + "#session_id=direct-offline-id")
    page.wait_for_url("**/studio", timeout=20000)
    assert [(k, v) for k, v in calls if k == "session"] == [("session", {"session_id": "direct-offline-id"})]
    assert calls[-1] == ("me", f"Bearer {TOKEN}")
    assert page.evaluate("localStorage.getItem('roastbox_token')") == TOKEN
    assert page.evaluate("location.hash") == ""
    context.close()
    print("PASS: regular redirect, one exchange, saved session, and studio navigation")


def direct_wrong_state(browser):
    context, calls = make_context(browser)
    page = context.new_page()
    page.goto(APP, wait_until="domcontentloaded")
    enter(page)
    page.wait_for_url(PROVIDER_START + "**")
    callback, _ = callback_for(page.url)
    page.goto(replace_state(callback, "forged-state") + "#session_id=attacker-id")
    page.get_by_test_id("google-login-error").wait_for(timeout=15000)
    assert not [x for x in calls if x[0] == "session"], calls
    assert not page.evaluate("localStorage.getItem('roastbox_token')")
    assert "verified" in page.get_by_test_id("google-login-error").inner_text()
    context.close()
    print("PASS: regular redirect rejects a forged OAuth state without exchanging it")


def direct_provider_failure(browser):
    context, calls = make_context(browser, exchange_status=401)
    page = context.new_page()
    page.goto(APP, wait_until="domcontentloaded")
    enter(page)
    page.wait_for_url(PROVIDER_START + "**")
    callback, _ = callback_for(page.url)
    page.goto(callback + "#session_id=expired-id")
    page.get_by_test_id("google-login-error").wait_for(timeout=15000)
    assert "expired" in page.get_by_test_id("google-login-error").inner_text()
    assert len([x for x in calls if x[0] == "session"]) == 1
    assert not page.evaluate("localStorage.getItem('roastbox_token')")
    context.close()
    print("PASS: a rejected provider session shows an error and does not sign in")


def callback_fragment_scrubbed(browser):
    context, _ = make_context(browser)
    page = context.new_page()
    page.goto(APP + "/auth-complete.html?mode=bad&state=discard#session_id=do-not-leak")
    assert page.url == APP + "/auth-complete.html"
    assert "invalid or expired" in page.locator("body").inner_text()
    context.close()
    print("PASS: callback removes the provider fragment and state from the URL")


def iframe_page(context):
    page = context.new_page()
    page.set_content(f'<iframe src="{APP}/" style="width:1000px;height:650px"></iframe>')
    frame = page.frame(url=re.compile(r"^" + re.escape(APP)))
    if frame is None:
        page.wait_for_timeout(1000)
        frame = page.frame(url=re.compile(r"^" + re.escape(APP)))
    assert frame is not None
    frame.get_by_test_id("splash-screen").wait_for()
    return page, frame


def popup_success_and_spoof(browser):
    context, calls = make_context(browser)
    page, frame = iframe_page(context)
    accept_adult_consent(frame)
    with page.expect_popup() as opened:
        frame.get_by_test_id("splash-login-btn").click()
    popup = opened.value
    popup.wait_for_url(PROVIDER_START + "**")
    callback, params = callback_for(popup.url)
    assert params["mode"] == ["popup"]
    state = params["state"][0]
    frame.evaluate("""state => window.postMessage({type: 'roastbox-google-auth-result', state,
        sessionId: 'forged-by-a-different-window'}, location.origin)""", state)
    page.wait_for_timeout(500)
    assert not [x for x in calls if x[0] == "session"], calls
    # Simulate the provider's script-driven return. A Playwright browser-initiated
    # popup.goto() can sever window.opener and does not match an OAuth redirect.
    popup.evaluate("url => { window.location.href = url; }", callback + "#session_id=popup-offline-id")
    frame.wait_for_url("**/studio", timeout=20000)
    assert [(k, v) for k, v in calls if k == "session"] == [("session", {"session_id": "popup-offline-id"})]
    assert calls[-1] == ("me", f"Bearer {TOKEN}")
    assert frame.evaluate("localStorage.getItem('roastbox_token')") == TOKEN
    context.close()
    print("PASS: embedded popup works and ignores a forged message from another window")


def popup_wrong_state(browser):
    context, calls = make_context(browser)
    page, frame = iframe_page(context)
    accept_adult_consent(frame)
    with page.expect_popup() as opened:
        frame.get_by_test_id("splash-login-btn").click()
    popup = opened.value
    popup.wait_for_url(PROVIDER_START + "**")
    callback, _ = callback_for(popup.url)
    popup.evaluate("url => { window.location.href = url; }", replace_state(callback, "wrong-popup-state") + "#session_id=attacker-id")
    frame.get_by_test_id("google-login-error").wait_for(timeout=15000)
    assert "verified" in frame.get_by_test_id("google-login-error").inner_text()
    assert not [x for x in calls if x[0] == "session"], calls
    context.close()
    print("PASS: embedded callback rejects a forged state")


def popup_blocked(browser):
    context, calls = make_context(browser)
    page, frame = iframe_page(context)
    frame.evaluate("window.open = () => null")
    enter(frame)
    frame.get_by_test_id("google-login-error").wait_for()
    assert "blocked" in frame.get_by_test_id("google-login-error").inner_text()
    assert not [x for x in calls if x[0] == "session"]
    context.close()
    print("PASS: blocked popups produce actionable feedback")


def top_level_without_session_storage(browser):
    context, calls = make_context(browser)
    context.add_init_script("""Object.defineProperty(window, 'sessionStorage', {
      configurable: true, get() { throw new DOMException('Blocked by browser', 'SecurityError'); }
    });""")
    page = context.new_page()
    page.goto(APP, wait_until="domcontentloaded")
    accept_adult_consent(page)
    with page.expect_popup() as opened:
        page.get_by_test_id("splash-login-btn").click()
    popup = opened.value
    popup.wait_for_url(PROVIDER_START + "**")
    callback, params = callback_for(popup.url)
    assert params["mode"] == ["popup"]
    popup.evaluate("url => { window.location.href = url; }", callback + "#session_id=no-session-storage")
    page.wait_for_url("**/studio", timeout=20000)
    assert [(k, v) for k, v in calls if k == "session"] == [("session", {"session_id": "no-session-storage"})]
    context.close()
    print("PASS: Google sign-in falls back to a popup when sessionStorage is blocked")


def popup_closed(browser):
    context, calls = make_context(browser)
    page, frame = iframe_page(context)
    accept_adult_consent(frame)
    with page.expect_popup() as opened:
        frame.get_by_test_id("splash-login-btn").click()
    popup = opened.value
    popup.wait_for_url(PROVIDER_START + "**")
    popup.close()
    frame.get_by_test_id("google-login-error").wait_for(timeout=5000)
    assert "closed" in frame.get_by_test_id("google-login-error").inner_text()
    assert frame.get_by_test_id("splash-login-btn").is_enabled()
    assert not [x for x in calls if x[0] == "session"]
    context.close()
    print("PASS: closing the sign-in window allows a clear retry")


def live_google_smoke(browser):
    context = browser.new_context(ignore_https_errors=True)
    page, frame = iframe_page(context)
    accept_adult_consent(frame)
    with page.expect_popup() as opened:
        frame.get_by_test_id("splash-login-btn").click()
    popup = opened.value
    popup.wait_for_url(re.compile(r"^https://accounts\.google\.com/"), timeout=45000)
    assert "Sign in" in popup.title()
    assert popup.evaluate("Boolean(window.opener)")
    cookies = {item["name"]: item["value"] for item in context.cookies("https://demobackend.emergentagent.com")}
    redirect_cookie = cookies.get("oauth_redirect", "").strip('"')
    redirect_params = parse_qs(urlparse(redirect_cookie).query)
    assert cookies.get("oauth_state") and redirect_cookie.startswith(APP + "/auth-complete.html?")
    assert redirect_params.get("mode") == ["popup"] and len(redirect_params.get("state", [""])[0]) >= 64
    print("PASS: live managed provider preserves the callback state and reaches Google's sign-in screen in a popup")
    print("NOTE: no Google credentials or consent were provided; a real account login remains unverified")
    context.close()


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        direct_success(browser)
        direct_wrong_state(browser)
        direct_provider_failure(browser)
        callback_fragment_scrubbed(browser)
        popup_success_and_spoof(browser)
        popup_wrong_state(browser)
        popup_blocked(browser)
        top_level_without_session_storage(browser)
        popup_closed(browser)
        if os.environ.get("LIVE_GOOGLE_SMOKE") == "1":
            live_google_smoke(browser)
        browser.close()
