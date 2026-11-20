#!/usr/bin/env python3
"""Offline browser integration: voice-first timing, cleanup, battle boundaries.

Requires the local preview/API. Roast, battle, images and voices are intercepted
fixtures; it does not call any paid AI provider.
"""
from playwright.sync_api import sync_playwright
from test_theater_display import APP, PHOTOS, RESULT, install_fixtures, login


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
        ctx = browser.new_context(viewport={"width": 1100, "height": 800})
        install_fixtures(ctx)
        beats = [
            {"persona_id": f"persona_{1 + i % 2}", "text": f"Offline punchline {i + 1} about a plastic trophy.",
             "audio_url": f"/api/testmedia/voice-{i + 1}", "image_index": 0,
             "type": "punchline", "laugh_after": "explosive", "reaction": "laugh", "rapid_fire": True}
            for i in range(2)
        ]
        ctx.route("**/api/roast/generate", lambda route: route.fulfill(json={**RESULT, "transcript": beats}))
        sent_battle = []
        def battle_fixture(route):
            sent_battle.append(route.request.post_data or "")
            route.fulfill(json={**RESULT, "transcript": beats,
                                "battle": {"winner": "persona_1", "scores": {"persona_1": 2, "persona_2": 1}}})
        ctx.route("**/api/battle/generate", battle_fixture)
        ctx.add_init_script("""(() => {
          window.__mixEvents = [];
          const ramp = AudioParam.prototype.linearRampToValueAtTime;
          AudioParam.prototype.linearRampToValueAtTime = function(value, at) {
            if (value === 0.08 || value === 1) window.__mixEvents.push({kind:'gain', value, time:performance.now()});
            return ramp.call(this, value, at);
          };
          const play = HTMLMediaElement.prototype.play;
          HTMLMediaElement.prototype.play = function(...args) {
            if ((this.currentSrc || this.src || '').startsWith('blob:')) {
              window.__mixEvents.push({kind:'voice-play', time:performance.now()});
              this.addEventListener('ended', () => window.__mixEvents.push({kind:'voice-end', time:performance.now()}), {once:true});
            }
            return play.apply(this, args);
          };
        })();""")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        login(page)
        page.get_by_test_id("persona-card-persona_1").click()
        page.get_by_test_id("persona-card-persona_2").click()
        page.get_by_test_id("image-file-input").set_input_files({"name": "test.jpg", "mimeType": "image/jpeg", "buffer": PHOTOS[0]})
        page.get_by_test_id("generate-roast-btn").click()
        page.get_by_test_id("roast-theater").wait_for(timeout=10000)
        page.wait_for_function("window.__mixEvents.filter(e => e.kind === 'voice-play').length >= 2", timeout=30000)
        events = page.evaluate("window.__mixEvents")
        plays = [i for i, e in enumerate(events) if e["kind"] == "voice-play"]
        p1, p2 = plays[:2]
        e1 = next(i for i in range(p1 + 1, p2) if events[i]["kind"] == "voice-end")
        duck1 = max(i for i in range(p1) if events[i].get("value") == 0.08)
        release = next(i for i in range(p1 + 1, p2) if events[i].get("value") == 1)
        duck2 = next(i for i in range(release + 1, p2) if events[i].get("value") == 0.08)
        # The hook's onended handler can resolve and release a fraction of a
        # millisecond before our later-added ended listener records the event.
        assert duck1 < p1 < release < duck2 < p2, events
        assert abs(events[release]["time"] - events[e1]["time"]) < 50, events
        assert events[p1]["time"] - events[duck1]["time"] >= 55, events
        assert events[p2]["time"] - events[duck2]["time"] >= 55, events
        assert events[release]["time"] - events[p1]["time"] > 2000, events
        page.get_by_test_id("theater-close-btn").click()
        page.wait_for_function("window.__mixEvents.at(-1)?.value === 1", timeout=5000)
        # Reopening a stopped show must be playable and does not regenerate it.
        page.get_by_test_id("watch-theater-btn").click()
        page.wait_for_function("window.__mixEvents.filter(e => e.kind === 'voice-play').length >= 3", timeout=25000)
        page.get_by_test_id("theater-close-btn").click()
        print("PASS: theater ducks before each voice, restores after speech, and resets cleanly on stop/replay", flush=True)

        page.get_by_test_id("nav-battle-btn").click()
        page.get_by_test_id("battle-persona-persona_1").click()
        page.get_by_test_id("battle-persona-persona_2").click()
        page.get_by_test_id("battle-off-limits-input").fill("family stories, health")
        page.get_by_test_id("battle-fight-btn").click()
        page.get_by_test_id("roast-theater").wait_for(timeout=10000)
        assert sent_battle and 'name="off_limits"' in sent_battle[-1] and "family stories, health" in sent_battle[-1]
        page.get_by_test_id("theater-close-btn").click()
        assert not errors, errors
        print("PASS: battle off-limits control submits the selected boundaries", flush=True)
        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
