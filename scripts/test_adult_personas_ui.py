#!/usr/bin/env python3
"""Browser checks for adult profile cards, strongest defaults and explicit overrides.

Use an isolated preview via ROASTBOX_TEST_ORIGIN. All generation/voice calls are
intercepted; no roast or voice provider is contacted.
"""
import io
import json
import os
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright, expect
from ui_helpers import accept_adult_consent

APP = os.environ.get("ROASTBOX_TEST_ORIGIN", "http://127.0.0.1:3000").rstrip("/")
PEOPLE = {p["id"]: p for p in json.loads((Path(__file__).resolve().parents[1] / "backend/data/personas.json").read_text())}
image=io.BytesIO();Image.new("RGB", (32,32), "#a06a36").save(image, "JPEG")


def run(browser, size, inferno):
    context=browser.new_context(viewport=size)
    sent, voices, errors = [], [], []
    def generation(route):
        sent.append((route.request.url, (route.request.post_data_buffer or b"").decode("utf-8", "replace")))
        route.fulfill(status=422, json={"detail": "Offline adult-persona regression; no paid generation."})
    context.route("**/api/roast/generate", generation)
    context.route("**/api/battle/generate", generation)
    def voice(route):
        voices.append(route.request.url)
        route.fulfill(status=403, json={"detail": "Offline voice interception"})
    context.route("**/api/personas/*/voice-preview*", voice)
    if not inferno:
        # Simulate a front-end account without Brutality+. Do not mutate its DB
        # entitlements; the offline Python suite tests actual server enforcement.
        def basic_profile(route):
            response=route.fetch();data=response.json()
            if response.status==200:
                user=data.get("user", data)
                user["nsfw_edgier_unlocked"]=False
                user["lifetime_founder"]=False
            route.fulfill(response=response, json=data)
        context.route("**/api/auth/me", basic_profile)
        context.route("**/api/auth/preview-login", basic_profile)
    page=context.new_page();page.on("pageerror", lambda e:errors.append(str(e)))
    page.goto(APP, wait_until="domcontentloaded")
    skip=page.get_by_test_id("skip-intro-btn")
    if skip.count() and skip.is_visible():skip.click()
    accept_adult_consent(page)
    page.get_by_test_id("preview-login-btn").click()
    page.wait_for_url("**/studio", timeout=20000)
    expected_heat="Inferno" if inferno else "Fire"
    expect(page.get_by_test_id("heat-value")).to_contain_text(expected_heat)
    expect(page.get_by_test_id("adult-language-toggle")).to_be_checked()
    expect(page.get_by_test_id("adult-language-row")).to_contain_text("drug references")
    engines=[]
    for pid in ("persona_1", "persona_2", "persona_11"):
        p=PEOPLE[pid]
        page.get_by_test_id("persona-search").fill(p["displayName"])
        page.get_by_test_id("persona-info-"+pid).click()
        modal=page.get_by_test_id("persona-detail-modal")
        expect(modal).to_be_visible()
        expect(modal.get_by_test_id("persona-adult-style")).to_contain_text(p["comedy_profile"]["comic_engine"])
        expect(modal).to_contain_text("21+ ORIGINAL ROASTER")
        expect(modal.get_by_test_id("persona-sample-2")).to_contain_text(p["punchlines"][2])
        engines.append(modal.get_by_test_id("persona-adult-style").inner_text())
        box=modal.bounding_box()
        assert box["y"]>=-1 and box["y"]+box["height"]<=size["height"]+1,box
        page.keyboard.press("Escape")
        expect(modal).not_to_be_visible()
    assert len(set(engines))==3 and not voices
    page.get_by_test_id("persona-search").fill("Big Sun-K")
    page.get_by_test_id("persona-card-persona_1").locator(".persona-card-main").click()
    page.get_by_test_id("image-file-input").set_input_files({"name":"synthetic-adult-target.jpg","mimeType":"image/jpeg","buffer":image.getvalue()})
    page.get_by_test_id("generate-roast-btn").click()
    expect(page.get_by_test_id("generate-roast-btn")).to_be_enabled(timeout=15000)
    assert len(sent)==1
    assert 'name="heat"\r\n\r\n'+expected_heat.lower() in sent[0][1]
    assert 'name="adult_language"\r\n\r\ntrue' in sent[0][1]
    assert 'name="adult_subjects_confirmed"\r\n\r\ntrue' in sent[0][1]
    # The stronger default must never reset an explicit lower/clean choice.
    page.get_by_test_id("heat-mild-btn").click()
    page.get_by_test_id("adult-language-row").click()
    expect(page.get_by_test_id("adult-language-toggle")).not_to_be_checked()
    page.get_by_test_id("generate-roast-btn").click()
    expect(page.get_by_test_id("generate-roast-btn")).to_be_enabled(timeout=15000)
    assert len(sent)==2 and 'name="heat"\r\n\r\nmild' in sent[1][1]
    assert 'name="adult_language"\r\n\r\nfalse' in sent[1][1]
    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_test_id("heat-value")).to_contain_text("Mild", timeout=20000)
    expect(page.get_by_test_id("adult-language-toggle")).not_to_be_checked()
    page.goto(APP+"/battle", wait_until="domcontentloaded")
    expect(page.get_by_test_id("heat-value")).to_contain_text("Mild", timeout=20000)
    expect(page.get_by_test_id("adult-language-toggle")).not_to_be_checked()
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    assert not voices and not errors,(voices,errors)
    context.close()
    print(f"PASS: {size['width']}x{size['height']} {expected_heat.upper()} adult defaults; 3 distinct 21+ profiles/3 samples; explicit clean/mild survives reload and Battle; no paid calls",flush=True)


if __name__=="__main__":
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
        try:
            for size in ({"width":1440,"height":900},{"width":390,"height":844}):
                for inferno in (True,False):run(browser,size,inferno)
        finally:browser.close()
