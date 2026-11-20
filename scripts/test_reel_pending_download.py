#!/usr/bin/env python3
"""One click while MP4 is loading still saves it, even after closing the player."""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roastbox_session import client, token

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:3000"


async def main():
    with client() as api:
        history = api.get("/roast/history").json()["history"]
        show = next(item for item in history if item.get("transcript")
                    and any(reel["status"] == "done" for reel in api.get(f"/roast/{item['id']}/reels").json()["reels"]))
    with client() as api:
        reel = next(item for item in api.get(f"/roast/{show['id']}/reels").json()["reels"] if item["status"] == "done")
        expected = hashlib.sha256(api.get(reel["video_url"][4:]).content).hexdigest()
    playback_started = asyncio.Event()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--mute-audio", "--disable-dev-shm-usage"])
        context = await browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
        await context.add_init_script(f"localStorage.setItem('roastbox_token', {json.dumps(token())});")
        async def delayed_file(route):
            if "download=true" in route.request.url:
                await route.continue_()
                return
            playback_started.set()
            await asyncio.sleep(3)
            try:
                await route.continue_()
            except Exception:
                pass  # Closing the player intentionally aborts its range request.
        await context.route("**/api/reels/*/file.mp4?*", delayed_file)
        page = await context.new_page()
        try:
            await page.goto(BASE + "/studio")
            await page.get_by_test_id("skip-intro-btn").click()
            await page.get_by_test_id("disclaimer-checkbox").click()
            await page.get_by_test_id("roast-studio").wait_for()
            await page.get_by_test_id("recent-shows").locator("summary").click()
            await page.get_by_test_id(f"recent-reels-{show['id']}").click()
            await page.get_by_test_id("reel-ready").wait_for()
            await asyncio.wait_for(playback_started.wait(), timeout=15)
            assert await page.get_by_test_id("reel-video").evaluate("v => v.readyState") < 2, "Playback should still be loading"
            async with page.expect_download(timeout=30000) as pending:
                await page.get_by_test_id("reel-download-btn").click()
                await page.get_by_test_id("reel-close-btn").click()
            download = await pending.value
            assert await download.failure() is None
            destination = ROOT / ".cache" / "pending-download.mp4"
            await download.save_as(destination)
            assert hashlib.sha256(destination.read_bytes()).hexdigest() == expected
            assert len(context.pages) == 1
            assert download.suggested_filename.endswith(".mp4")
            print("PASS: one Download click while native playback is delayed, close dialog, automatic complete MP4 save (no second click or new tab)")
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
