#!/usr/bin/env python3
"""Desktop/touch help, no hidden style drafts, compact layout and actual elapsed UI.

Requires ROASTBOX_TEST_ORIGIN pointing to an isolated, blank-provider-key QA app.
Generation, voice and email-send requests are intercepted. No paid providers.
"""
import io
import json
import os
from pathlib import Path
import requests
from PIL import Image
from playwright.sync_api import sync_playwright, expect
from ui_helpers import accept_adult_consent
from test_theater_display import install_fixtures, RESULT
from test_responsive import make_tiny_video

APP = os.environ.get('ROASTBOX_TEST_ORIGIN', '').rstrip('/')
ROOT = Path(__file__).resolve().parents[1]
image = io.BytesIO();Image.new('RGB',(40,40),'#c87848').save(image,'JPEG')


def bounds(page, node, size):
    box=node.bounding_box();assert box, 'No visible help box'
    assert box['x']>=-1 and box['y']>=-1 and box['x']+box['width']<=size['width']+1 and box['y']+box['height']<=size['height']+1, box
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')


def help_check(page, id, size, touch=False, close_button=False):
    trigger=page.get_by_test_id('help-'+id)
    trigger.scroll_into_view_if_needed()
    if touch:trigger.tap()
    else:trigger.hover()
    popup=page.locator('.info-tip-content')
    expect(popup).to_be_visible();bounds(page,popup,size)
    assert len(popup.inner_text())>35
    if close_button:popup.get_by_role('button').click()
    else:page.keyboard.press('Escape')
    expect(popup).to_have_count(0)
    expect(trigger).to_be_focused()


def run(browser,size,video,touch=False):
    context=browser.new_context(viewport=size,has_touch=touch,is_mobile=touch)
    install_fixtures(context)  # Synthetic local photos/tones; our generation handler overrides it below.
    side_effects=[]
    def block_write(route):side_effects.append(route.request.url);route.fulfill(status=422,json={'detail':'Offline action interception'})
    context.route('**/api/roast/*/share',block_write);context.route('**/api/roast/*/reel',block_write)
    context.route('**/api/roast/*/reels',lambda route:route.fulfill(json={'reels':[{
        'id':'offline-help-reel','roast_id':'offline-theater-test','status':'done','length':30,
        'video_url':'/api/testmedia/reel.mp4','size_bytes':len(video)}]}))
    context.route('**/api/testmedia/reel.mp4',lambda route:route.fulfill(body=video,content_type='video/mp4'))
    sent=[];pending=[];voices=[];errors=[];file_choosers=[];email_sends=[]
    def generation(route):
        sent.append((route.request.url,(route.request.post_data_buffer or b'').decode('utf-8','replace')))
        pending.append(route)  # Hold the request: test elapsed time, never fake a provider benchmark.
    context.route('**/api/roast/generate',generation);context.route('**/api/battle/generate',generation)
    def voice(route):voices.append(route.request.url);route.fulfill(status=403,json={'detail':'Offline voice interception'})
    context.route('**/api/personas/*/voice-preview*',voice)
    context.route('**/api/auth/email/status',lambda route:route.fulfill(json={'login_available':True,'registration_available':True,'recovery_available':True}))
    def no_mail(route):email_sends.append(route.request.url);route.fulfill(status=422,json={'detail':'Offline email interception'})
    for path in ('login','register','forgot','reset','verify'):context.route('**/api/auth/email/'+path,no_mail)
    page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('filechooser',lambda event:file_choosers.append(event))
    page.goto(APP,wait_until='domcontentloaded')
    skip=page.get_by_test_id('skip-intro-btn')
    if skip.count() and skip.is_visible():skip.click()
    expect(page.get_by_test_id('disclaimer-checkbox')).not_to_be_checked()
    notice=page.get_by_test_id('consent-full-notice')
    page.get_by_test_id('help-adult-consent').click()
    expect(notice).to_have_attribute('open','')
    expect(notice).to_contain_text('not verified age')
    page.keyboard.press('Escape');expect(notice).not_to_have_attribute('open','')
    expect(page.get_by_test_id('disclaimer-checkbox')).not_to_be_checked()
    accept_adult_consent(page)
    # Nested dialog help remains accessible, inside the viewport, and never
    # submits the login form or dismisses the sign-in dialog on its first Escape.
    page.get_by_test_id('email-auth-open').click()
    expect(page.get_by_test_id('email-auth-dialog')).to_be_visible()
    help_check(page,'email-address',size,touch,close_button=True)
    help_check(page,'email-password',size,touch)
    expect(page.get_by_test_id('email-auth-dialog')).to_be_visible()
    assert not email_sends
    page.get_by_role('button',name='Close email sign-in',exact=True).click()
    page.get_by_test_id('preview-login-btn').click()
    page.wait_for_url('**/studio',timeout=20000)
    expect(page.get_by_test_id('heat-value')).to_contain_text('Inferno')
    expect(page.get_by_test_id('adult-language-toggle')).to_be_checked()
    # An old tab's saved styles must not survive invisibly after the upgrade.
    page.evaluate("sessionStorage.setItem('roastbox_show_draft_v1:shared.comedyStyles',JSON.stringify(['savage','absurdist']))")
    page.reload(wait_until='domcontentloaded')
    expect(page.get_by_test_id('generate-roast-btn')).to_be_enabled(timeout=20000)
    assert page.evaluate("sessionStorage.getItem('roastbox_show_draft_v1:shared.comedyStyles')") is None
    expect(page.locator('[data-testid^="comedy-style-"]')).to_have_count(0)
    for id in ('step-hotseat','photos','guest-name','personal-ammo','off-limits','step-heat','roast-heat','set-length',
               'adult-language','step-showtime','writing-tier','premium-voices','prepay-reels','show-cost','step-lineup',
               'roaster-search','roaster-filter','roaster-sort','roaster-categories'):
        before_adult=page.get_by_test_id('adult-language-toggle').is_checked()
        before_hd=page.get_by_test_id('hd-export-toggle').is_checked()
        help_check(page,id,size,touch)
        assert page.get_by_test_id('adult-language-toggle').is_checked()==before_adult
        assert page.get_by_test_id('hd-export-toggle').is_checked()==before_hd
    assert not file_choosers and not sent and not voices
    # Keyboard focus and Enter work separately from hover; Close must not
    # immediately reopen itself by returning focus to its trigger.
    trigger=page.get_by_test_id('help-personal-ammo');trigger.scroll_into_view_if_needed()
    page.get_by_test_id('subject-name-input').focus();trigger.focus()
    expect(page.locator('.info-tip-content')).to_be_visible()
    page.keyboard.press('Enter');expect(trigger).to_have_attribute('aria-expanded','true')
    page.keyboard.press('Escape');expect(page.locator('.info-tip-content')).to_have_count(0)
    # A touch user's first tap opens, second tap closes; neither changes adult.
    adult_trigger=page.get_by_test_id('help-adult-language');adult_trigger.scroll_into_view_if_needed()
    if touch:
        adult_trigger.tap();expect(page.locator('.info-tip-content')).to_be_visible()
        adult_trigger.tap();expect(page.locator('.info-tip-content')).to_have_count(0)
    else:
        adult_trigger.click();expect(page.locator('.info-tip-content')).to_be_visible()
        page.get_by_test_id('subject-name-input').click();expect(page.locator('.info-tip-content')).to_have_count(0)
    expect(page.get_by_test_id('adult-language-toggle')).to_be_checked()
    # Optional adult samples are not fetched merely by opening profile/help.
    page.get_by_test_id('persona-search').fill('Big Sun-K')
    page.get_by_test_id('persona-info-persona_1').click()
    help_check(page,'persona-style',size,touch)
    help_check(page,'voice-samples',size,touch)
    expect(page.get_by_test_id('persona-detail-modal')).to_be_visible()
    assert not voices
    page.get_by_test_id('persona-detail-close-btn').click()
    page.get_by_test_id('persona-card-persona_1').locator('.persona-card-main').click()
    page.get_by_test_id('image-file-input').set_input_files({'name':'synthetic-adult.jpg','mimeType':'image/jpeg','buffer':image.getvalue()})
    page.get_by_test_id('subject-name-input').fill('QA Guest')
    page.get_by_test_id('context-textarea').fill('A loud floral collar and a tiny bowling trophy are the supplied story.')
    page.get_by_test_id('off-limits-input').fill('family, work')
    page.get_by_test_id('generate-roast-btn').click()
    expect(page.get_by_test_id('generation-clock')).to_be_visible()
    expect(page.get_by_test_id('generation-clock')).to_contain_text('0:01 elapsed',timeout=4000)
    help_check(page,'generation-wait',size,touch)
    assert len(sent)==1 and pending
    payload=sent[-1][1]
    for forbidden in ('comedy_styles','savage','absurdist'):assert forbidden not in payload
    assert 'name="adult_subjects_confirmed"\r\n\r\ntrue' in payload
    assert 'name="adult_language"\r\n\r\ntrue' in payload
    pending.pop(0).fulfill(status=422,json={'detail':'Offline UI regression; no provider contacted.'})
    expect(page.get_by_test_id('generate-roast-btn')).to_be_enabled(timeout=10000)
    expect(page.get_by_test_id('generation-clock')).to_have_count(0)
    # Fixture success tests response mapping (not actual provider latency) and
    # popovers in both the full-screen theater and a nested MP4 dialog.
    page.get_by_test_id('generate-roast-btn').click()
    expect(page.get_by_test_id('generation-clock')).to_be_visible()
    assert len(sent)==2
    pending.pop(0).fulfill(json={**RESULT,'generation_timing':{'writer_ms':1200,'voice_tail_ms':300,'total_ms':1500,'overlapped_clips':4}})
    expect(page.get_by_test_id('roast-theater')).to_be_visible()
    page.get_by_test_id('theater-mix-toggle').click()
    crowd_before=page.get_by_test_id('theater-crowd-volume').input_value()
    help_check(page,'crowd-volume',size,touch)
    assert page.get_by_test_id('theater-crowd-volume').input_value()==crowd_before
    expect(page.get_by_test_id('roast-theater')).to_be_visible()
    page.get_by_test_id('theater-close-btn').click()
    expect(page.get_by_test_id('generation-timing')).to_contain_text('Writer 1.2s · Voice tail 0.3s · Pipeline 1.5s')
    for id in ('generation-timing','share-show'):help_check(page,id,size,touch)
    expect(page.get_by_test_id('reel-view-btn')).to_be_visible()
    page.get_by_test_id('reel-change-length').click()
    help_check(page,'reel-length',size,touch)
    page.get_by_test_id('reel-view-btn').click()
    expect(page.get_by_test_id('reel-ready')).to_be_visible()
    help_check(page,'download-reel',size,touch)
    expect(page.get_by_test_id('reel-ready')).to_be_visible()
    page.get_by_test_id('reel-close-btn').click()
    assert not side_effects
    # Explicit clean/lower settings remain honored across routes and reloads.
    page.get_by_test_id('heat-mild-btn').click();page.get_by_test_id('adult-language-row').click()
    page.get_by_test_id('nav-settings-btn').click()
    expect(page.get_by_test_id('settings-page')).to_be_visible()
    for id in ('service-config','openai-key','elevenlabs-key','save-keys'):help_check(page,id,size,touch)
    page.get_by_test_id('nav-credits-btn').click()
    expect(page.get_by_test_id('credits-page')).to_be_visible()
    help_check(page,'credit-costs',size,touch)
    help_check(page,'credits-subscriptions',size,touch)
    page.get_by_test_id('nav-battle-btn').click()
    expect(page.get_by_test_id('battle-page')).to_be_visible()
    expect(page.get_by_test_id('heat-value')).to_contain_text('Mild')
    expect(page.get_by_test_id('adult-language-toggle')).not_to_be_checked()
    expect(page.locator('[data-testid^="comedy-style-"]')).to_have_count(0)
    for id in ('battle-style','battle-rounds','roast-heat','adult-language','battle-guest','battle-ammo',
               'battle-off-limits','battle-photo','battle-cost','battle-scoring','battle-fighters'):
        help_check(page,id,size,touch)
    expect(page.get_by_test_id('adult-language-toggle')).not_to_be_checked()
    for pid in ('persona_1','persona_2'):
        page.get_by_test_id('persona-search').fill('Big Sun-K' if pid=='persona_1' else 'Granny Snap')
        page.get_by_test_id('battle-persona-'+pid).locator('.persona-card-main').click()
    page.get_by_test_id('battle-fight-btn').click()
    expect(page.get_by_test_id('generation-clock')).to_be_visible()
    assert len(sent)==3
    payload=sent[-1][1]
    assert 'comedy_styles' not in payload and 'name="adult_language"\r\n\r\nfalse' in payload and 'name="heat"\r\n\r\nmild' in payload
    pending.pop(0).fulfill(status=422,json={'detail':'Offline battle UI regression; no provider contacted.'})
    expect(page.get_by_test_id('battle-fight-btn')).to_be_enabled(timeout=10000)
    assert not voices and not email_sends and not file_choosers and not errors,(voices,email_sends,errors)
    page.screenshot(path=str(ROOT/'.cache'/f'usercut-help-{size["width"]}.png'),full_page=True)
    page.goto(APP+'/auth/reset#token=offline_help_'+'A'*35,wait_until='domcontentloaded')
    page.get_by_test_id('skip-intro-btn').click()
    expect(page.get_by_test_id('email-token-page')).to_be_visible(timeout=10000)
    help_check(page,'new-password',size,touch)
    help_check(page,'confirm-password',size,touch)
    assert not email_sends and not side_effects and not errors
    context.close()
    print(f'PASS: {size["width"]}x{size["height"]} {"touch" if touch else "desktop"}: 40+ help checks, viewport/keyboard/tap/modal behavior, no accidental toggles/audio/mail; stale styles absent from both submissions; actual elapsed clock + fixture timing display, theater/reel/password help; explicit clean/mild preserved',flush=True)


def main():
    if not APP:raise SystemExit('Set ROASTBOX_TEST_ORIGIN to an isolated, blank-key QA app.')
    cfg=requests.get(APP+'/api/diagnostics',timeout=10).json()['config']
    assert all(not cfg.get(k) for k in ('openrouter_hosted_key','openai_hosted_key','emergent_llm_key','elevenlabs_hosted_key','stripe_api_key')),'Refusing to test a configured live app'
    video=make_tiny_video()  # Encode the one-second synthetic fixture BEFORE starting Chromium.
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            run(browser,{'width':1440,'height':900},video)
            run(browser,{'width':390,'height':844},video,touch=True)
        finally:browser.close()

if __name__=='__main__':main()
