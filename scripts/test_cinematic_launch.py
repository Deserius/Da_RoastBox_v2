#!/usr/bin/env python3
"""Offline launch, adult-consent, original-audio and email UI checks.

Uses only bundled media, local preview login, and mocked email endpoints. No
paid AI, Stripe, Google, or actual email provider is contacted.
"""
from __future__ import annotations

import json
import os
from playwright.sync_api import expect, sync_playwright
from ui_helpers import accept_adult_consent

APP = os.environ.get("ROASTBOX_TEST_ORIGIN", "http://127.0.0.1:3000").rstrip("/")


def test_intro_and_gate(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("""(() => {
      window.__introPlays = 0;
      const play = HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play = function (...args) {
        if ((this.currentSrc || this.src).includes('hae-cinematic-swoosh') && ++window.__introPlays <= 1)
          return Promise.reject(new DOMException('Autoplay blocked', 'NotAllowedError'));
        return play.apply(this, args);
      };
    })();""")
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(APP, wait_until='domcontentloaded')
    intro = page.get_by_test_id('cinematic-intro')
    expect(intro).to_be_visible()
    assert page.locator('.hae-logo-fall img').get_attribute('src').endswith('/hae-official-selection.png')
    assert page.get_by_test_id('disclaimer-modal').count() == 0
    page.wait_for_timeout(300)
    if page.get_by_test_id('intro-sound-btn').inner_text().strip() == 'Mute':
        page.get_by_test_id('intro-sound-btn').click()
    page.get_by_test_id('intro-sound-btn').click()
    page.wait_for_timeout(400)
    sync = page.evaluate("""() => {
      const a = document.querySelector('audio[src*="hae-cinematic"]');
      const scene = document.querySelector('.hae-intro-scene');
      return {audio: a.currentTime, paused: a.paused, visual: scene.getAnimations()[0]?.currentTime / 1000};
    }""")
    assert not sync['paused'] and sync['audio'] > 0 and abs(sync['audio'] - sync['visual']) < .35, sync
    page.get_by_test_id('skip-intro-btn').click()
    expect(page.get_by_test_id('inline-disclaimer')).to_be_visible()
    assert page.get_by_test_id('disclaimer-modal').count() == 0
    assert page.get_by_test_id('enter-roast-btn').is_disabled()
    assert page.get_by_test_id('sign-in-dialog').count() == 0
    page.get_by_test_id('disclaimer-checkbox').check()
    assert page.get_by_test_id('enter-roast-btn').is_enabled()
    page.get_by_test_id('disclaimer-checkbox').uncheck()
    assert page.get_by_test_id('enter-roast-btn').is_disabled()
    page.get_by_test_id('disclaimer-checkbox').check()
    assert page.evaluate("sessionStorage.getItem('roastbox_adult_consent_21_v2')") == 'accepted'
    assert page.get_by_test_id('about-author-trigger').count() == 0
    page.reload(wait_until='domcontentloaded')
    expect(page.get_by_test_id('enter-roast-btn')).to_be_enabled()
    assert page.get_by_test_id('cinematic-intro').count() == 0
    assert page.get_by_test_id('disclaimer-modal').count() == 0
    assert not errors, errors
    ctx.close()
    print('PASS: selected logo, synced replay, skippable intro, bottom consent checkbox and tab-session persistence', flush=True)


def test_automatic_intro_and_focus(browser):
    for motion, limit in [('no-preference', 14000), ('reduce', 7000)]:
        ctx = browser.new_context(viewport={'width': 390, 'height': 844}, reduced_motion=motion)
        page = ctx.new_page()
        page.goto(APP, wait_until='domcontentloaded')
        expect(page.get_by_test_id('cinematic-intro')).to_be_visible()
        if motion == 'reduce':
            assert page.locator('.hae-water').count() == 0
        expect(page.get_by_test_id('cinematic-intro')).to_have_count(0, timeout=limit)
        expect(page.get_by_test_id('inline-disclaimer')).to_be_visible()
        assert page.get_by_test_id('disclaimer-modal').count() == 0
        ctx.close()
    print('PASS: full and reduced-motion intros advance automatically; bottom consent panel is visible', flush=True)


def test_direct_route_gating(browser):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(APP, wait_until='domcontentloaded')
    accept_adult_consent(page)
    page.get_by_test_id('preview-login-btn').click()
    page.wait_for_url('**/studio', timeout=20000)
    # A fresh tab shares the login but not its explicit tab-session consent.
    fresh = ctx.new_page()
    fresh.goto(APP + '/studio', wait_until='domcontentloaded')
    expect(fresh.get_by_test_id('inline-disclaimer')).to_be_visible(timeout=15000)
    assert fresh.get_by_test_id('roast-studio').count() == 0
    fresh.get_by_test_id('disclaimer-checkbox').click()
    expect(fresh.get_by_test_id('roast-studio')).to_be_visible(timeout=15000)
    # Shared roast content is also never mounted/fetched before the gate.
    calls = []
    third = ctx.new_page()
    third.on('request', lambda request: calls.append(request.url) if '/api/share/' in request.url else None)
    third.goto(APP + '/r/not-a-real-share', wait_until='domcontentloaded')
    expect(third.get_by_test_id('inline-disclaimer')).to_be_visible()
    assert not calls
    ctx.close()
    print('PASS: authenticated deep links and public shares are gated before their content mounts', flush=True)


def test_responsive_consent(browser):
    for width, height in [(240, 568), (320, 568), (390, 844), (568, 320), (1024, 768), (1440, 900)]:
        ctx = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='reduce')
        page = ctx.new_page()
        page.goto(APP, wait_until='domcontentloaded')
        # Reduced motion automatically moves on quickly, still with a skip control.
        page.get_by_test_id('skip-intro-btn').click()
        disclaimer = page.get_by_test_id('inline-disclaimer')
        disclaimer.wait_for()
        bounds = disclaimer.bounding_box()
        assert bounds and bounds['x'] >= -1 and bounds['x'] + bounds['width'] <= width + 1, (width, height, bounds)
        assert page.evaluate('document.documentElement.scrollWidth') <= width + 1
        page.get_by_test_id('disclaimer-checkbox').check()
        assert page.get_by_test_id('enter-roast-btn').is_enabled()
        page.get_by_test_id('enter-roast-btn').click()
        assert page.get_by_test_id('splash-login-btn').is_enabled()
        ctx.close()
        print(f'PASS: accessible consent layout {width}×{height}', flush=True)


def test_audio_focus_and_menu(browser):
    ctx = browser.new_context(viewport={'width': 412, 'height': 839}, is_mobile=True, has_touch=True)
    ctx.add_init_script("""(() => { const Native = window.Audio; window.__narration = [];
      window.Audio = function (...args) { const a = new Native(...args); window.__narration.push(a); return a; };
    })();""")
    page = ctx.new_page()
    page.goto(APP, wait_until='domcontentloaded')
    accept_adult_consent(page)
    assert page.get_by_test_id('lounge-toggle').count() == 0
    page.get_by_test_id('preview-login-btn').click()
    page.wait_for_url('**/studio', timeout=20000)
    assert page.get_by_test_id('nav-about-author-btn').count() == 0
    assert page.get_by_test_id('about-author-trigger').count() == 0
    page.get_by_test_id('menu-toggle').click()
    page.get_by_test_id('lounge-toggle').click()
    page.wait_for_function("!document.querySelector('audio[src*=roastbox-lounge]').paused", timeout=10000)
    expect(page.get_by_test_id('menu-about-developer-btn')).to_have_text('About Developer')
    page.get_by_test_id('menu-about-developer-btn').click()
    page.get_by_test_id('author-start-reading').click()
    page.get_by_test_id('author-play').click()
    page.wait_for_function("window.__narration.length && !window.__narration.at(-1).paused && document.querySelector('audio[src*=roastbox-lounge]').paused", timeout=15000)
    page.get_by_test_id('author-close').click()
    page.wait_for_function("!document.querySelector('audio[src*=roastbox-lounge]').paused", timeout=10000)
    page.get_by_test_id('lounge-toggle').click()
    page.wait_for_function("document.querySelector('audio[src*=roastbox-lounge]').paused")
    ctx.close()
    print('PASS: menu-only About Developer; opted-in lounge pauses for narration and resumes without overlap', flush=True)


def test_email_ui(browser):
    # The real preview has no SMTP setup and must not pretend otherwise.
    ctx = browser.new_context(viewport={'width': 390, 'height': 844})
    page = ctx.new_page()
    page.goto(APP, wait_until='domcontentloaded'); accept_adult_consent(page)
    page.get_by_test_id('email-auth-open').click()
    expect(page.get_by_test_id('email-auth-dialog')).to_contain_text('not been configured', timeout=10000)
    ctx.close()

    # Test complete UI interactions with fixtures only; not real email delivery.
    ctx = browser.new_context(viewport={'width': 390, 'height': 844})
    calls = []
    user = {'id': 'email-ui-user', 'email': 'user@example.com', 'name': 'User', 'credits': 5}
    token = 'email-ui-token-not-a-real-session'
    ctx.route('**/api/auth/email/status', lambda route: route.fulfill(json={'login_available': True, 'registration_available': True, 'recovery_available': True}))
    def register(route):
        calls.append(('register', route.request.post_data_json))
        route.fulfill(status=202, json={'message': 'If the address can be used, an email with next steps will arrive shortly.'})
    def forgot(route):
        calls.append(('forgot', route.request.post_data_json))
        route.fulfill(status=202, json={'message': 'If the address can be used, an email with next steps will arrive shortly.'})
    def login(route):
        calls.append(('login', route.request.post_data_json))
        route.fulfill(json={'session_token': token, 'user': user})
    def me(route):
        if route.request.headers.get('x-roastbox-session') == token:
            route.fulfill(json=user)
        else:
            route.fulfill(status=401, json={'detail': 'Not authenticated'})
    ctx.route('**/api/auth/email/register', register)
    ctx.route('**/api/auth/email/forgot', forgot)
    ctx.route('**/api/auth/email/login', login)
    ctx.route('**/api/auth/me', me)
    page = ctx.new_page(); page.goto(APP, wait_until='domcontentloaded'); accept_adult_consent(page)
    page.get_by_test_id('email-auth-open').click()
    page.get_by_test_id('email-create-account').click()
    page.get_by_test_id('email-address').fill('user@example.com')
    page.get_by_test_id('email-auth-submit').click()
    expect(page.get_by_test_id('email-auth-dialog')).to_contain_text('Check your inbox.')
    assert calls[-1] == ('register', {'email': 'user@example.com'})
    page.get_by_role('button', name='Back to sign in').first.click()
    page.get_by_test_id('email-forgot-password').click()
    page.get_by_test_id('email-auth-submit').click()
    expect(page.get_by_test_id('email-auth-dialog')).to_contain_text('Check your inbox.')
    assert calls[-1] == ('forgot', {'email': 'user@example.com'})
    page.get_by_role('button', name='Back to sign in').first.click()
    page.get_by_test_id('email-password').fill('an appropriately long passphrase')
    page.get_by_test_id('email-auth-submit').click()
    page.wait_for_url('**/studio', timeout=20000)
    assert calls[-1][0] == 'login'
    ctx.close()

    ctx = browser.new_context()
    calls = []
    def verify(route):
        calls.append(route.request.post_data_json)
        route.fulfill(json={'message': 'Email verified.'})
    ctx.route('**/api/auth/email/verify', verify)
    page = ctx.new_page()
    opaque = 'a' * 43
    page.goto(APP + '/auth/verify#token=' + opaque, wait_until='domcontentloaded')
    page.get_by_test_id('email-token-page').wait_for()
    assert page.evaluate('location.hash') == ''
    assert not page.evaluate("JSON.stringify(localStorage).includes('" + opaque + "')")
    page.get_by_test_id('email-new-password').fill('this is a new secure passphrase')
    page.get_by_test_id('email-confirm-password').fill('this is a new secure passphrase')
    page.get_by_test_id('email-token-submit').click()
    expect(page.get_by_test_id('email-token-page')).to_contain_text("You're all set.")
    assert calls and calls[0]['token'] == opaque
    ctx.close()

    ctx = browser.new_context()
    calls = []
    def reset(route):
        calls.append(route.request.post_data_json)
        route.fulfill(json={'message': 'Password reset.'})
    ctx.route('**/api/auth/email/reset', reset)
    page = ctx.new_page()
    opaque = 'b' * 43
    page.goto(APP + '/auth/reset#token=' + opaque, wait_until='domcontentloaded')
    page.get_by_test_id('email-token-page').wait_for()
    assert page.evaluate('location.hash') == ''
    page.get_by_test_id('email-new-password').fill('a different secure passphrase')
    page.get_by_test_id('email-confirm-password').fill('not the same passphrase')
    page.get_by_test_id('email-token-submit').click()
    expect(page.get_by_test_id('email-token-page')).to_contain_text("don't match")
    assert calls == []
    page.get_by_test_id('email-confirm-password').fill('a different secure passphrase')
    page.get_by_test_id('email-token-submit').click()
    expect(page.get_by_test_id('email-token-page')).to_contain_text("You're all set.")
    assert calls and calls[0]['token'] == opaque
    ctx.close()
    print('PASS: truthful unconfigured state, mocked signup/recovery/login, and scrubbed verification/reset fragments', flush=True)


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required'])
        try:
            test_intro_and_gate(browser)
            test_automatic_intro_and_focus(browser)
            test_direct_route_gating(browser)
            test_responsive_consent(browser)
            test_audio_focus_and_menu(browser)
            test_email_ui(browser)
        finally:
            browser.close()
    print('Cinematic launch offline checks completed successfully.')
