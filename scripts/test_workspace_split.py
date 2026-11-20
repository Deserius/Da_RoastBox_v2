#!/usr/bin/env python3
"""Verify independent desktop panes and mobile fallback without AI requests."""
from playwright.sync_api import sync_playwright, expect
from ui_helpers import accept_adult_consent

with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 try:
  for width,height in [(1920,1080),(1440,900),(1280,800),(1024,768),(390,844)]:
   ctx=b.new_context(viewport={'width':width,'height':height},reduced_motion='reduce'); page=ctx.new_page()
   page.goto('http://127.0.0.1:3000');accept_adult_consent(page);page.get_by_test_id('preview-login-btn').click();page.wait_for_url('**/studio',timeout=20000)
   expect(page.get_by_test_id('persona-card-persona_1')).to_be_attached()
   if width >= 1000:
    left=page.locator('.studio-side');right=page.locator('.studio-roster')
    assert left.bounding_box()['x'] < right.bounding_box()['x']
    assert abs(left.bounding_box()['width'] - right.bounding_box()['width']) < 1
    assert abs(left.bounding_box()['height'] - right.bounding_box()['height']) < 1
    before=page.evaluate('scrollY'); right.evaluate('(el) => el.scrollTop = el.scrollHeight');
    assert right.evaluate('(el) => el.scrollTop') > 0 and page.evaluate('scrollY') == before
    left.evaluate('(el) => el.scrollTop = el.scrollHeight');assert left.evaluate('(el) => el.scrollTop') > 0 and page.evaluate('scrollY') == before
    page.get_by_test_id('studio-jump-step-heat').click();expect(page.get_by_test_id('step-heat')).to_be_in_viewport()
   page.get_by_test_id('nav-battle-btn').click();expect(page.get_by_test_id('battle-page')).to_be_visible()
   if width >= 1000:
    left=page.locator('.battle-controls');right=page.locator('.battle-roster')
    assert left.bounding_box()['x'] < right.bounding_box()['x']
    assert abs(left.bounding_box()['width'] - right.bounding_box()['width']) < 1
    assert abs(left.bounding_box()['height'] - right.bounding_box()['height']) < 1
    before=page.evaluate('scrollY');right.evaluate('(el) => el.scrollTop = el.scrollHeight');assert right.evaluate('(el) => el.scrollTop') > 0 and page.evaluate('scrollY') == before
   assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
   print('PASS: split workspace and navigation',width,height,flush=True);ctx.close()
 finally:b.close()
