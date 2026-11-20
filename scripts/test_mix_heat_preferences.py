#!/usr/bin/env python3
"""Offline browser checks for saved heat and theater crowd preferences."""
from playwright.sync_api import sync_playwright
from test_theater_display import APP, install_fixtures, login, start_studio


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'])
        context = browser.new_context()
        install_fixtures(context)
        page = context.new_page()
        login(page)
        user = page.evaluate("async () => (await fetch('/api/auth/me', {credentials: 'include'})).json()")
        expected = 'Inferno' if user.get('nsfw_edgier_unlocked') or user.get('lifetime_founder') else 'Fire'
        assert expected in page.get_by_test_id('heat-value').inner_text()
        page.get_by_test_id('heat-mild-btn').click()
        page.reload(wait_until='domcontentloaded')
        page.get_by_test_id('persona-card-persona_1').wait_for()
        assert 'Mild' in page.get_by_test_id('heat-value').inner_text()
        start_studio(page)
        page.get_by_test_id('theater-mix-toggle').click()
        slider = page.get_by_test_id('theater-crowd-volume')
        slider.fill('0.25')
        assert page.evaluate("JSON.parse(localStorage.getItem('rb_crowd_volume'))") == 0.25
        page.get_by_test_id('theater-close-btn').click()
        page.get_by_test_id('watch-theater-btn').click()
        page.get_by_test_id('theater-mix-toggle').click()
        assert page.get_by_test_id('theater-crowd-volume').input_value() == '0.25'
        browser.close()
    print('PASS: fresh heat default, saved heat and crowd volume persist across reload/replay')


if __name__ == '__main__':
    main()
