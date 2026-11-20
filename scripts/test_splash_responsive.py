#!/usr/bin/env python3
"""Offline consent/auth flow, keyboard, audio and responsive regression (no paid APIs)."""
from playwright.sync_api import sync_playwright, expect

APP='http://127.0.0.1:3000'

def safe_routes(ctx):
    def route(r):
        u=r.request.url
        if '/api/auth/me' in u: return r.fulfill(status=401,json={'detail':'Not authenticated'})
        if '/api/auth/email/status' in u: return r.fulfill(json={'login_available':False,'registration_available':False,'recovery_available':False})
        if '/api/' in u: return r.fulfill(status=200,json={})
        if not u.startswith(APP): return r.abort()
        return r.continue_()
    ctx.route('**/*', route)

def test_size(browser,w,h):
    ctx=browser.new_context(viewport={'width':w,'height':h},reduced_motion='reduce'); safe_routes(ctx)
    page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(APP,wait_until='domcontentloaded');page.get_by_test_id('skip-intro-btn').click()
    panel=page.get_by_test_id('splash-consent-panel');expect(panel).to_be_visible()
    enter=page.get_by_test_id('enter-roast-btn'); expect(enter).to_be_disabled()
    assert panel.get_by_test_id('lounge-toggle').count()==0
    assert page.get_by_test_id('sign-in-dialog').count()==0
    page.get_by_test_id('disclaimer-checkbox').check();expect(enter).to_be_enabled()
    rect=panel.bounding_box();assert rect['x']>=-1 and rect['x']+rect['width']<=w+1,(w,h,rect)
    assert rect['y']>=-1 and rect['y']+rect['height']<=h+1,(w,h,rect)
    assert page.evaluate('document.documentElement.scrollWidth')<=w+1,(w,h)
    enter.click();modal=page.get_by_test_id('sign-in-dialog');expect(modal).to_be_visible()
    rect=modal.bounding_box();assert rect['x']>=-1 and rect['x']+rect['width']<=w+1,(w,h,rect)
    assert abs(rect['x']+rect['width']/2-w/2)<2 and abs(rect['y']+rect['height']/2-h/2)<2,(w,h,rect)
    expect(modal.get_by_test_id('splash-login-btn')).to_be_visible()
    modal.get_by_test_id('email-auth-open').click()
    expect(page.get_by_test_id('email-auth-dialog')).to_be_visible();page.keyboard.press('Escape')
    expect(modal).to_be_visible();page.keyboard.press('Escape');expect(panel).to_be_visible()
    assert page.get_by_test_id('disclaimer-checkbox').is_checked()
    assert not errors,errors
    ctx.close();print(f'PASS consent and centered sign-in {w}x{h}',flush=True)

def test_sound(browser):
    ctx=browser.new_context(viewport={'width':390,'height':844})
    safe_routes(ctx);page=ctx.new_page();page.goto(APP,wait_until='domcontentloaded')
    expect(page.get_by_test_id('cinematic-intro')).to_be_visible()
    assert page.locator('audio[src*="hae-cinematic-swoosh.mp3"]').count()==1
    page.wait_for_timeout(300)
    if page.get_by_test_id('intro-sound-btn').inner_text().strip() == 'Mute':
        page.get_by_test_id('intro-sound-btn').click()
    page.get_by_test_id('intro-sound-btn').click(); page.wait_for_timeout(500)
    assert page.evaluate('''() => {const a=document.querySelector('audio[src*="hae-cinematic-swoosh"]'); return !a.paused && a.currentTime > 0}''')
    page.get_by_test_id('skip-intro-btn').click();expect(page.get_by_test_id('splash-consent-panel')).to_be_visible()
    ctx.close();print('PASS intro sound via user gesture and splash handoff',flush=True)

if __name__=='__main__':
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required'])
        try:
            for w,h in [(200,400),(240,568),(320,568),(390,844),(568,320),(844,390),(768,1024),(1024,768),(1440,900),(2560,1440)]: test_size(browser,w,h)
            test_sound(browser)
        finally:browser.close()
