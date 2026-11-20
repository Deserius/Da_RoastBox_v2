#!/usr/bin/env python3
"""Compact glass splash: layout, optional full notice and explicit 21+ consent.

All API traffic is intercepted; no real login, DB writes or paid providers.
Set ROASTBOX_TEST_ORIGIN to a staged or published local app.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
APP = os.environ.get('ROASTBOX_TEST_ORIGIN','http://127.0.0.1:3000').rstrip('/')
OUT = ROOT / '.cache' / 'compact-splash-checks'
OUT.mkdir(parents=True,exist_ok=True)


def safe_routes(context, signed_in=False):
    writes=[];calls=[]
    def route(r):
        path=urlsplit(r.request.url).path;calls.append(path)
        if r.request.method!='GET':
            writes.append(path);r.fulfill(status=403,json={'detail':'Offline regression; no real writes'});return
        if path=='/api/auth/me':
            if signed_in:r.fulfill(json={'id':'offline-consent','email':'qa@example.invalid','name':'Offline consent','credits':100,'is_preview':True,'plan_tier':'free'})
            else:r.fulfill(status=401,json={'detail':'Not authenticated'})
        elif path=='/api/auth/email/status':r.fulfill(json={'login_available':True,'registration_available':True,'recovery_available':True})
        else:r.fulfill(json={})
    context.route('**/api/**',route)
    return writes,calls


def inside(node,w,h):
    b=node.bounding_box();assert b
    assert b['x']>=-1 and b['y']>=-1 and b['x']+b['width']<=w+1 and b['y']+b['height']<=h+1,b
    return b


def check_size(browser,w,h):
    touch=w<900
    ctx=browser.new_context(viewport={'width':w,'height':h},has_touch=touch,is_mobile=touch,reduced_motion='reduce')
    writes,calls=safe_routes(ctx);errors=[]
    page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(APP,wait_until='domcontentloaded');page.get_by_test_id('skip-intro-btn').click()
    panel=page.get_by_test_id('splash-consent-panel');expect(panel).to_be_visible()
    page.evaluate('document.fonts.ready')
    box=inside(panel,w,h)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    assert panel.locator('.disclaimer-compact').count()==1
    assert panel.evaluate("e=>getComputedStyle(e).backgroundImage.includes('rgba')")
    assert panel.get_by_test_id('inline-disclaimer').evaluate("e=>getComputedStyle(e).backgroundColor")=='rgba(0, 0, 0, 0)'
    assert box['width']<=471,box
    assert abs(box['x']+box['width']/2-w/2)<=1,box
    if w>=500:assert abs(box['width']-470)<=1,box
    if w>=1000:assert box['height']<=220,box
    if w==390:assert box['height']<=220,box
    # At common sizes, all default controls are reachable with no internal scroll.
    if w>=320:assert panel.evaluate('e=>e.scrollHeight <= e.clientHeight+1')
    checkbox=page.get_by_test_id('disclaimer-checkbox');enter=page.get_by_test_id('enter-roast-btn')
    expect(checkbox).not_to_be_checked();expect(enter).to_be_disabled()
    inside(checkbox,w,h);enter_box=inside(enter,w,h)
    assert abs(enter_box['x']+enter_box['width']/2-w/2)<=1,enter_box
    assert enter_box['width']<=241,enter_box
    assert enter_box['y']>=page.get_by_test_id('inline-disclaimer').bounding_box()['y']+page.get_by_test_id('inline-disclaimer').bounding_box()['height']-1,enter_box
    audio_button=page.get_by_test_id('landing-audio-toggle');audio_box=inside(audio_button,w,h)
    overlap=min(box['x']+box['width'],audio_box['x']+audio_box['width'])-max(box['x'],audio_box['x'])>0 and min(box['y']+box['height'],audio_box['y']+audio_box['height'])-max(box['y'],audio_box['y'])>0
    assert not overlap,(box,audio_box)
    notice=page.get_by_test_id('consent-full-notice');trigger=page.get_by_test_id('help-adult-consent')
    assert not notice.evaluate('e=>e.open')
    if w in (1440,390):
        page.evaluate("new Promise(r=>{const im=new Image();im.onload=r;im.onerror=r;im.src='/assets/splash_bg.png';})")
        page.screenshot(path=str(OUT/f'splash-{w}.png'))
    # Sound stays usable outside the modal without accepting consent.
    audio_button.click();expect(page.get_by_test_id('landing-audio')).to_have_attribute('data-muted','false')
    page.wait_for_function("!document.querySelector('[data-testid=\"landing-beat\"]').paused")
    expect(checkbox).not_to_be_checked();expect(enter).to_be_disabled()
    audio_button.click();expect(page.get_by_test_id('landing-audio')).to_have_attribute('data-muted','true')
    assert page.get_by_test_id('landing-beat').evaluate('e=>e.paused')
    # Full notice includes the original text and attestation limits. Opening it
    # cannot grant consent, navigate, or send an API request.
    trigger.tap() if touch else trigger.click()
    assert notice.evaluate('e=>e.open')
    expect(notice).to_contain_text('not liable')
    expect(notice).to_contain_text('photos you have permission to use')
    expect(notice).to_contain_text('not verified age')
    expect(checkbox).not_to_be_checked();expect(enter).to_be_disabled()
    inside(panel,w,h)
    page.keyboard.press('Escape');assert not notice.evaluate('e=>e.open')
    expect(trigger).to_be_focused();expect(panel).to_be_visible()
    # Native disclosure keyboard behavior, independent of the consent checkbox.
    trigger.press('Enter');assert notice.evaluate('e=>e.open')
    trigger.press('Enter');assert not notice.evaluate('e=>e.open')
    expect(checkbox).not_to_be_checked()
    checkbox.check();expect(enter).to_be_enabled()
    assert page.evaluate("sessionStorage.getItem('roastbox_adult_consent_21_v2')")=='accepted'
    checkbox.uncheck();expect(enter).to_be_disabled()
    assert page.evaluate("sessionStorage.getItem('roastbox_adult_consent_21_v2')") is None
    checkbox.check();enter.click()
    dialog=page.get_by_test_id('sign-in-dialog');expect(dialog).to_be_visible();inside(dialog,w,h)
    page.keyboard.press('Escape');expect(panel).to_be_visible();expect(checkbox).to_be_checked()
    assert not writes and not errors,(writes,errors)
    result={'width':w,'height':h,'panel':box,'enter':enter_box,'api_writes':len(writes)}
    ctx.close()
    print(f'PASS: {w}x{h}, {box["width"]:.0f}x{box["height"]:.1f}px centered glass panel / centered Enter; readable/reachable controls, full notice/tap/keyboard/Escape, sound clear/usable, explicit checkbox, sign-in handoff; no real API writes',flush=True)
    return result


def check_direct_gate(browser):
    ctx=browser.new_context(viewport={'width':390,'height':844},reduced_motion='reduce')
    writes,calls=safe_routes(ctx,signed_in=True)
    page=ctx.new_page();page.goto(APP+'/studio',wait_until='domcontentloaded');page.get_by_test_id('skip-intro-btn').click()
    gate=page.get_by_test_id('inline-disclaimer');expect(gate).to_be_visible(timeout=12000)
    assert gate.locator('.compact-consent-heading').count()==0
    assert page.get_by_test_id('consent-full-notice').count()==0
    expect(gate).to_contain_text('not liable')
    expect(page.get_by_test_id('disclaimer-checkbox')).not_to_be_checked()
    assert page.get_by_test_id('roast-studio').count()==0 and '/api/personas' not in calls
    assert not writes
    ctx.close();print('PASS: direct-route gate retains full disclaimer and blocks protected content before consent',flush=True)



def check_lobby_rotation(browser):
    ctx=browser.new_context(viewport={'width':1440,'height':900},reduced_motion='no-preference')
    writes,_=safe_routes(ctx)
    page=ctx.new_page();page.clock.install()
    page.goto(APP,wait_until='domcontentloaded');page.get_by_test_id('skip-intro-btn').click()
    expect(page.get_by_test_id('splash-consent-panel')).to_be_visible()
    page.wait_for_function("!document.querySelector('[data-testid=\"landing-beat\"]').paused")
    assert page.get_by_test_id('landing-beat').evaluate('e=>e.loop')
    page.wait_for_timeout(1150)
    first=page.get_by_test_id('landing-welcome').get_attribute('src')
    assert first and 'roastbox-welcome' in first
    page.clock.fast_forward('00:31')
    second=page.get_by_test_id('landing-welcome').get_attribute('src')
    assert second and second!=first,(first,second)
    expect(page.get_by_test_id('disclaimer-checkbox')).not_to_be_checked()
    assert not writes
    ctx.close();print('PASS: original lobby beat loops and welcome rotates after 30s without accepting consent or real API writes',flush=True)


def main():
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--mute-audio'])
        try:
            results=[check_size(b,w,h) for w,h in [(200,400),(240,568),(320,568),(390,844),(568,320),(844,390),(768,1024),(1024,768),(1440,900),(2560,1440)]]
            check_direct_gate(b)
            check_lobby_rotation(b)
        finally:b.close()
    (OUT/'measurements.json').write_text(json.dumps(results,indent=2))

if __name__=='__main__':main()
