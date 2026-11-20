#!/usr/bin/env python3
"""Verify splash-sound autoplay handling and the lobby beat + welcome rotation."""
import sys
from playwright.sync_api import sync_playwright, expect

MUTED = [False]  # Run once with a permissive autoplay policy.


def state(page, testid):
    return page.evaluate("""(id) => {
      const el = document.querySelector(`[data-testid="${id}"]`);
      if (!el) return null;
      return { paused: el.paused, src: el.getAttribute('src'), volume: el.volume, loop: el.loop, time: el.currentTime };
    }""", testid)


def run(headless=True):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=[
            "--no-sandbox", "--autoplay-policy=no-user-gesture-required", "--mute-audio"])
        page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="no-preference")
        # Install the fake clock before the app mounts so its timers are controlled.
        page.clock.install()
        page.goto("http://127.0.0.1:3000")
        # The brand splash asks for sound as soon as it mounts.
        expect(page.get_by_test_id("cinematic-intro")).to_be_visible()
        intro = state(page, "intro-sound") if page.get_by_test_id("intro-sound").count() else None
        page.wait_for_timeout(700)
        playing = page.evaluate("""() => Array.from(document.querySelectorAll('audio')).map(a => ({src: a.getAttribute('src'), paused: a.paused}))""")
        assert any(not a["paused"] for a in playing), f"no audio started on the splash: {playing}"
        # Move to the sign-in screen.
        page.get_by_test_id("skip-intro-btn").click()
        page.wait_for_timeout(900)
        beat = state(page, "landing-beat")
        assert beat and beat["loop"], f"beat loop missing: {beat}"
        assert not beat["paused"], "lobby beat is not playing"
        # With the clock fast-forwarded, the welcome call must rotate tracks.
        first = state(page, "landing-welcome")["src"]
        page.clock.fast_forward("00:31")
        page.wait_for_timeout(400)
        second = state(page, "landing-welcome")["src"]
        assert first and second and first != second, f"welcome track did not rotate: {first} -> {second}"
        assert "roastbox-welcome" in (second or ""), second
        # The mute control stops and restarts the soundtrack and is remembered.
        page.get_by_test_id("landing-audio-toggle").click()
        page.wait_for_timeout(300)
        assert state(page, "landing-beat")["paused"], "mute did not pause the beat"
        assert page.get_by_test_id("landing-audio").get_attribute("data-muted") == "true"
        assert page.evaluate("() => window.localStorage.getItem('roastbox.landing-audio')") == "off"
        page.get_by_test_id("landing-audio-toggle").click()
        page.wait_for_timeout(400)
        assert not state(page, "landing-beat")["paused"], "unmute did not resume the beat"
        print("PASS: splash sound starts, lobby beat loops, welcome rotates every 30s, mute works")
        browser.close()


if __name__ == "__main__":
    run()
