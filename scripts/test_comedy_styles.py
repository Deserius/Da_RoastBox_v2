#!/usr/bin/env python3
"""No paid calls: verify style selection, persistence, and form submission."""
from playwright.sync_api import sync_playwright, expect
from ui_helpers import accept_adult_consent
from test_theater_display import PHOTOS

with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 try:
  ctx=b.new_context(viewport={'width':390,'height':844}); page=ctx.new_page()
  bodies=[]
  def mock(route):
   bodies.append((route.request.post_data_buffer or b'').decode('utf-8', errors='replace'))
   route.fulfill(status=400,json={'detail':'offline fixture'})
  ctx.route('**/api/roast/generate',mock)
  page.goto('http://127.0.0.1:3000');accept_adult_consent(page)
  page.get_by_test_id('preview-login-btn').click();page.wait_for_url('**/studio',timeout=20000)
  page.get_by_test_id('comedy-style-savage').check();page.get_by_test_id('comedy-style-absurdist').check()
  page.get_by_test_id('nav-settings-btn').click();page.get_by_test_id('settings-page').wait_for()
  page.get_by_test_id('brand-link').click();page.get_by_test_id('roast-studio').wait_for()
  expect(page.get_by_test_id('comedy-style-savage')).to_be_checked();expect(page.get_by_test_id('comedy-style-absurdist')).to_be_checked()
  page.get_by_test_id('persona-card-persona_1').locator('.persona-card-main').click()
  page.get_by_test_id('image-file-input').set_input_files({'name':'test.jpg','mimeType':'image/jpeg','buffer':PHOTOS[0]})
  page.get_by_test_id('generate-roast-btn').click();page.wait_for_timeout(400)
  assert len(bodies)==1 and 'comedy_styles' in bodies[0] and 'savage' in bodies[0] and 'absurdist' in bodies[0]
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
  print('PASS: style selection, route persistence, and offline multipart submission')
 finally:b.close()
