#!/usr/bin/env python3
"""Offline lounge focus checks for persona samples, shows and reel video."""
import re
from playwright.sync_api import sync_playwright
from ui_helpers import accept_adult_consent
from test_persona_browser import fake_voices
from test_theater_display import APP, PHOTOS, install_fixtures
from test_responsive import make_tiny_video

LOUNGE = "document.querySelector('audio[src*=roastbox-lounge]')"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required'])
    ctx = browser.new_context(viewport={'width': 1024, 'height': 768})
    calls = []
    fake_voices(ctx, calls)
    install_fixtures(ctx)
    video = make_tiny_video()
    ctx.route(re.compile(r'.*/api/roast/[^/]+/reel$'), lambda route: route.fulfill(json={
        'id': 'reel-offline', 'length': 30, 'status': 'done', 'video_url': '/api/test-reel/focus.mp4'}))
    ctx.route('**/api/test-reel/**', lambda route: route.fulfill(body=video, content_type='video/mp4'))
    page = ctx.new_page()
    page.goto(APP, wait_until='domcontentloaded')
    accept_adult_consent(page)
    page.get_by_test_id('lounge-toggle').click()
    page.wait_for_function(f'!{LOUNGE}.paused')
    page.get_by_test_id('preview-login-btn').click()
    page.wait_for_url('**/studio', timeout=20000)

    page.get_by_test_id('persona-info-persona_1').click()
    modal = page.get_by_test_id('persona-detail-modal')
    modal.get_by_test_id('persona-voice-preview-btn').click()
    modal.get_by_text('NOW PLAYING').wait_for(timeout=10000)
    page.wait_for_function(f'{LOUNGE}.paused')
    modal.get_by_test_id('persona-detail-close-btn').click()
    page.wait_for_function(f'!{LOUNGE}.paused')
    assert len(calls) == 1
    print('PASS: lounge pauses for a mocked persona sample and resumes when the profile closes', flush=True)

    page.get_by_test_id('persona-card-persona_1').locator('.persona-card-main').click()
    page.get_by_test_id('image-file-input').set_input_files({'name': 'fixture.jpg', 'mimeType': 'image/jpeg', 'buffer': PHOTOS[0]})
    page.get_by_test_id('generate-roast-btn').click()
    page.get_by_test_id('roast-theater').wait_for(timeout=15000)
    page.wait_for_function(f'{LOUNGE}.paused')
    page.get_by_test_id('theater-close-btn').click()
    page.wait_for_function(f'!{LOUNGE}.paused')
    print('PASS: lounge pauses for a mocked show and resumes when the theater closes', flush=True)

    page.get_by_test_id('reel-30-btn').click()
    page.get_by_test_id('reel-view-btn').click()
    reel = page.get_by_test_id('reel-video')
    reel.wait_for(timeout=10000)
    page.wait_for_function(f"!document.querySelector('[data-testid=reel-video]').paused && {LOUNGE}.paused", timeout=10000)
    reel.evaluate('(v) => v.pause()')
    page.wait_for_function(f'!{LOUNGE}.paused')
    reel.evaluate('(v) => { v.currentTime = 0; return v.play(); }')
    page.wait_for_function(f'{LOUNGE}.paused')
    page.get_by_test_id('reel-close-btn').click()
    page.wait_for_function(f'!{LOUNGE}.paused')
    print('PASS: lounge pauses for reel video and resumes on pause/close, including cleanup', flush=True)
    ctx.close()
    browser.close()
