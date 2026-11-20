#!/usr/bin/env python3
"""Offline Chromium/Web Audio regression for the actual theater crowd engine.

Uses synthesized tones and OfflineAudioContext, no provider calls, app server,
user media or speakers required. Measures both a tail that existed before speech
and a second crowd layer scheduled while speech is already in progress.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "frontend/src/lib/crowdEngine.js").read_text().replace(
    "export const crowd = new CrowdEngine();", "window.testCrowd = new CrowdEngine();"
)
assert "window.testCrowd" in SOURCE and "export const crowd" not in SOURCE


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page()
        page.goto("about:blank")
        page.add_script_tag(content=SOURCE)
        result = page.evaluate("""async () => {
          const sampleRate = 48000;
          const offline = new OfflineAudioContext(2, sampleRate * 4, sampleRate);
          // unlock() sets up the production graph. Keep this offline context
          // from attempting resume() before startRendering().
          Object.defineProperty(offline, 'state', { get: () => 'running' });
          window.AudioContext = function() { return offline; };
          Math.random = () => 0.5; // centered pan, playback rate 1, stable buffers
          const c = window.testCrowd;
          c.loading = Promise.resolve(); // synthesized local buffers, no fetch
          await c.unlock();
          function tone(hz) {
            const b = offline.createBuffer(1, sampleRate * 4, sampleRate);
            const a = b.getChannelData(0);
            for (let i = 0; i < a.length; i++) a[i] = 0.12 * Math.sin(2 * Math.PI * hz * i / sampleRate);
            return b;
          }
          c.buffers.laugh_big_1 = c.buffers.laugh_big_2 = tone(220);
          c.buffers.laugh_med_1 = c.buffers.laugh_med_2 = tone(440);
          c.play('big', { gain: 0.9, fadeIn: 0.01 });

          // The separate persona voice bypasses the crowd bus, just as the app's
          // HTML Audio does. Use a distinct frequency to measure each component.
          const voice = offline.createOscillator();
          const voiceGain = offline.createGain();
          voice.frequency.value = 880;
          voiceGain.gain.value = 0.12;
          voice.connect(voiceGain).connect(offline.destination);
          voice.start(1.0); voice.stop(2.0);

          const waits = [
            offline.suspend(0.90).then(() => { c.duck(); return offline.resume(); }),
            offline.suspend(1.10).then(() => { c.play('medium', { gain: 0.45, delay: 100 }); return offline.resume(); }),
            offline.suspend(2.00).then(() => { c.releaseDuck(); return offline.resume(); }),
          ];
          const rendered = await offline.startRendering();
          await Promise.all(waits);
          const a = rendered.getChannelData(0);
          function amplitude(hz, from, to) {
            let re = 0, im = 0, n = 0;
            for (let i = Math.floor(from * sampleRate); i < Math.floor(to * sampleRate); i++) {
              const phase = 2 * Math.PI * hz * i / sampleRate;
              re += a[i] * Math.cos(phase); im += a[i] * Math.sin(phase); n++;
            }
            return 2 * Math.hypot(re, im) / n;
          }
          return {
            master: c.master.gain.value,
            existingNormal: amplitude(220, .3, .7), existingDuring: amplitude(220, 1.4, 1.8),
            existingAfter: amplitude(220, 3.1, 3.5),
            delayedDuring: amplitude(440, 1.4, 1.8), delayedAfter: amplitude(440, 3.1, 3.5),
            voiceDuring: amplitude(880, 1.4, 1.8),
          };
        }""")
        browser.close()
    assert abs(result["master"] - 0.45) < 0.001, result
    existing_ratio = result["existingDuring"] / result["existingNormal"]
    delayed_ratio = result["delayedDuring"] / result["delayedAfter"]
    recovery = result["existingAfter"] / result["existingNormal"]
    assert 0.06 < existing_ratio < 0.10, result
    assert 0.06 < delayed_ratio < 0.10, result
    assert 0.95 < recovery < 1.05, result
    assert result["voiceDuring"] > result["existingDuring"] * 8, result
    print(f"PASS: real Web Audio mix: existing crowd={existing_ratio:.2f}×, "
          f"new delayed layer={delayed_ratio:.2f}× during speech, recovery={recovery:.2f}×")


if __name__ == "__main__":
    main()
