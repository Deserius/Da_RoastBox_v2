#!/usr/bin/env python3
"""Offline browser wiring against a built frontend: NO running API or network.

Every HTTP request is fulfilled from local build files or explicit in-memory
fixtures; external origins and unknown API calls are blocked. Nothing uses a
customer account, database, real provider, checkout or cloud storage. Real codec
and server-side business behavior are tested separately by test_offline.py.
"""
from __future__ import annotations
import argparse
import copy
import io
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import parse_qs, unquote, urlsplit

from PIL import Image
from playwright.sync_api import sync_playwright, expect
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://render-ui.invalid'
PEOPLE = json.loads((ROOT / 'backend/data/personas.json').read_text())
PRIVATE = {'voice_direction', 'elevenlabs', 'tts_voice', 'tts_voice_hd', 'comedy_profile'}


def public_personas():
    result = []
    for p in PEOPLE:
        item = {k: v for k, v in p.items() if k not in PRIVATE}
        profile = p['comedy_profile']
        item.update(is_premium=p.get('tier') == 'premium', locked=False,
                    adult_comedy={'rating': '21+', 'signature_move': profile['comic_engine'], 'target_lenses': profile.get('targets', [])})
        result.append(item)
    return result


class FixtureSite:
    def __init__(self, build, video, *, authed=True, inferno=True, preview=False):
        self.build, self.video, self.authed = build, video, authed
        self.calls, self.unexpected, self.generations, self.voices = [], [], [], []
        self.favorites, self.saved_reels = set(), []
        self.user = dict(id='offline-ui-user', email='offline-ui@example.invalid', name='Offline UI Fixture', credits=25,
                         plan_tier='free', is_preview=preview, has_byok_openai=False, has_byok_elevenlabs=False,
                         premium_personas_unlocked=True, premium_voices_unlocked=True, nsfw_edgier_unlocked=inferno,
                         roast_battle_unlocked=True, lifetime_founder=False, favorite_persona_ids=[])
        self.people = public_personas()
        self.receipt = dict(provider='openrouter', requested_model='anthropic/claude-sonnet-4.5', reported_model='offline-ui-response-model',
                            prompt_revision='offline-ui-fixture', writer_elapsed_ms=1000, usage={'total_tokens': 500})
        self.transcript = [dict(persona_id='persona_1', type='punchline', text='This is an offline browser wiring fixture, not an AI-generated show.',
                                image_index=0, laugh_after='none', audio_url='/api/audio/offline-ui.mp3', provider='openai', audio_model='tts-1', audio_vendor='openai')]
        self.show = dict(id='offline-ui-show', mode='roast', subject_name='Offline consenting adult fixture', image_count=1,
                         persona_ids=['persona_1'], transcript=self.transcript, generation_meta=self.receipt, credits_spent=0,
                         created_at='2026-11-03T12:00:00Z', hd_export=False)

    def answer(self, route, data=None, status=200, body=None, mime=None):
        if body is not None: route.fulfill(status=status, body=body, content_type=mime)
        else: route.fulfill(status=status, json=data)

    def handle(self, route):
        request = route.request
        url = urlsplit(request.url)
        path = unquote(url.path)
        if url.scheme in {'data', 'blob'}: return route.continue_()
        if url.netloc != 'render-ui.invalid':
            self.unexpected.append('external:' + url.netloc)
            return route.abort()
        if not path.startswith('/api/'):
            candidate = (self.build / path.lstrip('/')).resolve()
            if candidate.is_relative_to(self.build.resolve()) and candidate.is_file():
                return self.answer(route, body=candidate.read_bytes(), mime=mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream')
            if Path(path).suffix:
                self.unexpected.append('missing-static:' + path)
                return self.answer(route, body=b'not found', status=404, mime='text/plain')
            return self.answer(route, body=(self.build / 'index.html').read_bytes(), mime='text/html')
        self.calls.append((request.method, path))
        if path == '/api/auth/me': return self.answer(route, self.user if self.authed else {'detail': 'Not authenticated'}, 200 if self.authed else 401)
        if path == '/api/auth/preview-login':
            self.authed = True
            return self.answer(route, {'user': self.user, 'session_token': 'offline-ui-session-not-a-real-token'})
        if path == '/api/auth/logout': self.authed = False; return self.answer(route, {'ok': True})
        if path == '/api/auth/email/status': return self.answer(route, {'login_available': False, 'registration_available': False, 'recovery_available': False})
        if path == '/api/personas': return self.answer(route, {'personas': self.people, 'premium_unlocked': True})
        if path == '/api/personas/favorites': return self.answer(route, {'favorites': sorted(self.favorites)})
        if path.startswith('/api/personas/favorites/'):
            pid = path.rsplit('/', 1)[-1]
            if request.method == 'PUT': self.favorites.add(pid)
            else: self.favorites.discard(pid)
            return self.answer(route, {'persona_id': pid, 'favorite': pid in self.favorites})
        if path.endswith('/voice-preview'):
            self.voices.append(path + '?' + url.query)
            return self.answer(route, {'audio_url': '/api/audio/offline-ui.mp3', 'sample': int(parse_qs(url.query).get('sample', ['0'])[0])})
        if path.startswith('/api/audio/'):
            return self.answer(route, body=(ROOT / 'backend/assets/sfx/chuckle_1.mp3').read_bytes(), mime='audio/mpeg')
        if path.startswith('/api/media/subject/'):
            return self.answer(route, body=(ROOT / 'backend/assets/personas/persona_1.webp').read_bytes(), mime='image/webp')
        if path == '/api/roast/cost-quote': return self.answer(route, {'credit_cost': 8, 'free_available': False, 'credits_balance': self.user['credits'], 'plan_tier': 'free'})
        if path == '/api/roast/history': return self.answer(route, {'history': [self.show]})
        if path in {'/api/roast/generate', '/api/battle/generate'}:
            self.generations.append((path, (request.post_data_buffer or b'').decode('utf-8', 'replace')))
            self.user['credits'] = max(0, self.user['credits'] - 5)
            return self.answer(route, {'roast_id': self.show['id'], 'persona_ids': ['persona_1'], 'transcript': self.transcript,
                'generation_meta': self.receipt, 'images': ['/api/media/subject/offline-ui-show/0.jpg'], 'credits_spent': 5,
                'credits_remaining': self.user['credits'], 'premium_voice_fallback': True, 'was_free_roast': False,
                'battle': {'winner': 'persona_1', 'scores': {'persona_1': 8, 'persona_2': 4}}})
        if path == '/api/battle/access': return self.answer(route, {'unlocked': True, 'base_cost': 5, 'premium_persona_cost': 5})
        if path == '/api/payments/packs':
            return self.answer(route, {'packs': [{'id': 'credits_starter', 'type': 'credits', 'name': 'Starter Pack', 'credits': 50, 'amount_usd': 4.99}], 'roast_costs': {'standard_roast': 5}})
        if path == '/api/payments/checkout': return self.answer(route, {'detail': 'Offline checkout interception; no payment was created.'}, 503)
        if path.startswith('/api/payments/status/'):
            return self.answer(route, {'payment_status': 'failed'})
        if path == '/api/payments/activity': return self.answer(route, {'payments': [], 'credit_activity': [], 'shows': [self.show], 'limit': 20})
        if path == '/api/diagnostics': return self.answer(route, {'status': 'ready', 'config': {'openrouter_hosted_key': True, 'openai_hosted_key': True, 'stripe_api_key': True,
             'stripe_webhook_secret': True, 'stripe_test_only': True, 'storage_backend': 'vercel_blob', 'preview_hosted_ai_enabled': True}})
        if path == '/api/voice-settings/keys':
            self.user['has_byok_openai'] = request.method == 'POST'
            return self.answer(route, {'ok': True})
        if path.endswith('/share') and path.startswith('/api/roast/'):
            return self.answer(route, {'share_path': '/r/offline-ui-share'})
        if path.startswith('/api/share/'):
            return self.answer(route, {**self.show, 'personas': self.people[:1], 'images': ['/api/media/subject/offline-ui-show/0.jpg']})
        if path.endswith('/reels') and path.startswith('/api/roast/'):
            return self.answer(route, {'reels': self.saved_reels})
        if path.endswith('/reel') and path.startswith('/api/roast/'):
            reel = dict(id='offline-ui-reel', status='queued', length=30, filename='da-roastbox-offline-ui.mp4')
            self.saved_reels[:] = [reel]
            return self.answer(route, reel)
        if path == '/api/reels/offline-ui-reel':
            reel = dict(id='offline-ui-reel', status='done', length=30, video_url='/api/reels/offline-ui-reel/video.mp4', download_url='/api/reels/offline-ui-reel/video.mp4?download=true', size_bytes=len(self.video), filename='da-roastbox-offline-ui.mp4')
            self.saved_reels[:] = [reel]
            return self.answer(route, reel)
        if path.endswith('/video.mp4'):
            return self.answer(route, body=self.video, mime='video/mp4')
        self.unexpected.append(request.method + ':' + path)
        return self.answer(route, {'detail': 'Unexpected offline fixture route'}, 500)


def skip_intro(page):
    button = page.get_by_test_id('skip-intro-btn')
    if button.count() and button.is_visible():
        try: button.click(timeout=1500)
        except Exception: pass


def visit(page, path, marker):
    page.goto(ORIGIN + path, wait_until='domcontentloaded')
    skip_intro(page)
    expect(page.get_by_test_id(marker)).to_be_visible(timeout=15000)


def nav(page, destination, marker):
    page.get_by_test_id('menu-toggle').click()
    page.get_by_test_id('menu-nav-' + destination).click()
    expect(page.get_by_test_id(marker)).to_be_visible()


def run_workflow(browser, build, video, viewport, *, inferno=True, full=True):
    fixture = FixtureSite(build, video, inferno=inferno)
    context = browser.new_context(viewport=viewport, service_workers='block', accept_downloads=True)
    context.route('**/*', fixture.handle)
    page = context.new_page(); errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(ORIGIN + '/studio', wait_until='domcontentloaded'); skip_intro(page)
    expect(page.get_by_test_id('disclaimer-checkbox')).to_be_visible(timeout=15000)
    # The one-time consent gate unmounts its checkbox immediately; click, do
    # not ask check() to inspect the no-longer-existing DOM node.
    page.get_by_test_id('disclaimer-checkbox').click()
    expect(page.get_by_test_id('roast-studio')).to_be_visible()
    expect(page.get_by_test_id('adult-language-toggle')).to_be_checked()
    expect(page.get_by_test_id('heat-value')).to_contain_text('Inferno' if inferno else 'Fire')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    # Browser card/profile/sample controls, never a real voice request.
    for pid in ('persona_1', 'persona_2', 'persona_11'):
        person = next(p for p in PEOPLE if p['id'] == pid)
        page.get_by_test_id('persona-search').fill(person['displayName'])
        page.get_by_test_id('persona-info-' + pid).click()
        modal = page.get_by_test_id('persona-detail-modal')
        expect(modal.get_by_test_id('persona-adult-style')).to_contain_text(person['comedy_profile']['comic_engine'])
        expect(modal.get_by_test_id('persona-sample-2')).to_contain_text(person['punchlines'][2])
        if full and pid == 'persona_1':
            modal.get_by_test_id('persona-modal-favorite-' + pid).click()
            expect(modal.get_by_test_id('persona-modal-favorite-' + pid)).to_have_attribute('aria-pressed', 'true')
            for sample in ('persona-voice-preview-btn', 'persona-voice-preview-1', 'persona-voice-preview-2'):
                modal.get_by_test_id(sample).click()
                page.wait_for_timeout(100)
        modal.get_by_test_id('persona-detail-close-btn').click()
    page.get_by_test_id('persona-search').fill(PEOPLE[0]['displayName'])
    page.get_by_test_id('persona-card-persona_1').locator('.persona-card-main').click()
    image = io.BytesIO(); Image.new('RGB', (32, 32), '#8866aa').save(image, 'JPEG')
    page.get_by_test_id('image-file-input').set_input_files({'name': 'offline-adult-fixture.jpg', 'mimeType': 'image/jpeg', 'buffer': image.getvalue()})
    expect(page.get_by_test_id('generate-roast-btn')).to_be_disabled()
    page.get_by_test_id('subject-consent').check()
    expect(page.get_by_test_id('generate-roast-btn')).to_be_enabled()
    page.get_by_test_id('generate-roast-btn').click()
    expect(page.get_by_test_id('theater-close-btn')).to_be_visible(timeout=15000)
    if full:
        page.get_by_test_id('theater-mix-toggle').click()
        page.get_by_test_id('theater-crowd-volume').fill('0.2')
    page.get_by_test_id('theater-close-btn').click()
    receipt = page.get_by_test_id('generation-receipt'); receipt.locator('summary').click()
    expect(receipt).to_contain_text('offline-ui-response-model')
    expect(receipt).to_contain_text('openai: tts-1')
    assert 'name="adult_subjects_confirmed"\r\n\r\ntrue' in fixture.generations[-1][1]
    page.get_by_test_id('heat-mild-btn').click()
    page.get_by_test_id('adult-language-toggle').locator('..').click()
    # Clean still needs explicit per-show subject consent.
    page.get_by_test_id('subject-consent').uncheck()
    expect(page.get_by_test_id('generate-roast-btn')).to_be_disabled()
    page.reload(wait_until='domcontentloaded'); skip_intro(page)
    expect(page.get_by_test_id('heat-value')).to_contain_text('Mild', timeout=15000)
    expect(page.get_by_test_id('adult-language-toggle')).not_to_be_checked()
    expect(page.get_by_test_id('subject-consent')).not_to_be_checked()
    if full:
        recent = page.get_by_test_id('recent-shows'); recent.locator('summary').click()
        page.get_by_test_id('recent-reels-offline-ui-show').click()
        expect(page.get_by_test_id('reel-30-btn')).to_be_visible()
        page.get_by_test_id('reel-30-btn').click()
        expect(page.get_by_test_id('reel-video')).to_be_visible(timeout=15000)
        with page.expect_download(timeout=10000) as pending:
            page.get_by_test_id('reel-download-btn').click()
        download = pending.value
        assert download.suggested_filename.endswith('.mp4')
        assert Path(download.path()).read_bytes() == video
        page.get_by_test_id('reel-close-btn').click()
        page.get_by_test_id('share-roast-btn').click()
        expect(page.get_by_test_id('share-link-input')).to_have_value(ORIGIN + '/r/offline-ui-share')
        nav(page, 'roasters', 'roasters-page')
        page.get_by_test_id('persona-search').fill(PEOPLE[0]['displayName'])
        page.get_by_test_id('persona-info-persona_1').click(); page.get_by_test_id('persona-detail-close-btn').click()
        nav(page, 'battle', 'battle-page')
        expect(page.get_by_test_id('adult-language-toggle')).not_to_be_checked()
        page.get_by_test_id('battle-style-rap').click()
        expect(page.get_by_test_id('battle-style-rap')).to_have_attribute('aria-pressed', 'true')
        page.get_by_test_id('battle-rounds-4').click()
        page.get_by_test_id('battle-subject-input').fill('Offline consenting adult fixture')
        page.get_by_test_id('battle-context-input').fill('Offline UI request-shape check, not real generation.')
        page.get_by_test_id('battle-off-limits-input').fill('Do not mention private addresses')
        page.get_by_test_id('battle-image-input').set_input_files({'name': 'offline-battle.jpg', 'mimeType': 'image/jpeg', 'buffer': image.getvalue()})
        for pid in ['persona_1', 'persona_2']:
            person = next(p for p in PEOPLE if p['id'] == pid)
            page.get_by_test_id('persona-search').fill(person['displayName'])
            page.get_by_test_id('battle-persona-' + pid).locator('.persona-card-main').click()
        expect(page.get_by_test_id('battle-fight-btn')).to_be_disabled()
        page.get_by_test_id('subject-consent').check(); page.get_by_test_id('battle-fight-btn').click()
        expect(page.get_by_test_id('theater-close-btn')).to_be_visible(timeout=15000)
        page.get_by_test_id('theater-close-btn').click()
        skip = page.get_by_test_id('battle-skip-btn')
        if skip.count() and skip.is_visible(): skip.click()
        expect(page.get_by_test_id('battle-winner')).to_be_visible()
        assert fixture.generations[-1][0] == '/api/battle/generate'
        assert 'name="adult_language"\r\n\r\nfalse' in fixture.generations[-1][1]
        assert 'name="battle_style"\r\n\r\nrap' in fixture.generations[-1][1]
        nav(page, 'credits', 'credits-page')
        expect(page.get_by_test_id('credits-page')).to_contain_text('Stripe TEST')
        page.get_by_test_id('buy-credits_starter-btn').click()
        expect(page.get_by_test_id('buy-credits_starter-btn')).to_be_enabled()
        assert ('POST', '/api/payments/checkout') in fixture.calls
        nav(page, 'settings', 'settings-page')
        expect(page.get_by_test_id('service-configuration')).to_contain_text('Private Blob')
        page.get_by_test_id('openai-key-input').fill('offline-ui-noncredential')
        page.get_by_test_id('save-keys-btn').click()
        expect(page.get_by_test_id('openai-key-input')).to_have_value('')
        page.get_by_test_id('clear-keys-btn').click()
        page.get_by_test_id('menu-toggle').click()
        page.get_by_test_id('payment-history-section').locator('summary').click()
        expect(page.get_by_test_id('payment-history')).to_contain_text('No payment history yet')
        page.get_by_test_id('usage-history-section').locator('summary').click()
        expect(page.get_by_test_id('usage-history')).to_contain_text('Offline consenting adult fixture')
        page.get_by_test_id('help-section').locator('summary').click()
        expect(page.get_by_test_id('help-section')).to_contain_text('Open app settings')
        page.get_by_test_id('lounge-toggle').click()
        expect(page.get_by_test_id('lounge-toggle')).to_have_attribute('aria-pressed', 'true')
        page.get_by_test_id('lounge-volume').fill('0.2')
        page.get_by_test_id('lounge-toggle').click()
        page.get_by_role('button', name='About Developer').click()
        expect(page.get_by_test_id('about-author-dialog')).to_be_visible()
        page.get_by_test_id('author-start-reading').click()
        expect(page.get_by_test_id('author-chapter')).to_be_visible()
        page.get_by_test_id('author-next').click(); page.get_by_test_id('author-previous').click()
        page.get_by_test_id('author-play').click(); page.get_by_test_id('author-replay').click()
        page.get_by_test_id('author-close').click()
        if page.get_by_test_id('menu-close').is_visible(): page.get_by_test_id('menu-close').click()
        visit(page, '/credits/cancel', 'checkout-cancel')
        page.get_by_test_id('back-to-credits-btn').click()
        visit(page, '/credits/success?session_id=cs_test_offlineui', 'checkout-success')
        expect(page.get_by_test_id('checkout-success')).to_contain_text('Payment Failed')
        visit(page, '/r/offline-ui-share', 'share-page')
        page.get_by_test_id('share-play-btn').click()
        page.get_by_test_id('theater-close-btn').click()
        for path in ('/auth/verify', '/auth/reset'):
            visit(page, path, 'email-token-page')
            expect(page.get_by_test_id('email-token-page')).to_contain_text('missing or expired')
        visit(page, '/studio', 'roast-studio')
        page.get_by_test_id('menu-toggle').click(); page.get_by_test_id('menu-logout').click()
        expect(page.get_by_test_id('splash-screen')).to_be_visible(timeout=15000)
    assert not fixture.unexpected, fixture.unexpected
    assert not errors, errors
    assert not any(path == '/api/session/dispatch' for _, path in fixture.calls)
    context.close()
    return {'viewport': viewport, 'default_heat': 'inferno' if inferno else 'fire', 'full_workflow': full,
            'api_fixture_requests': len(fixture.calls), 'voice_fixture_requests': len(fixture.voices), 'generation_fixtures': len(fixture.generations),
            'real_api_provider_payment_or_database_requests': 0, 'passed': True}


def run_landing(browser, build, video):
    fixture = FixtureSite(build, video, authed=False, preview=True)
    context = browser.new_context(viewport={'width': 390, 'height': 844}, service_workers='block')
    context.route('**/*', fixture.handle)
    page = context.new_page(); visit(page, '/', 'splash-screen')
    expect(page.get_by_test_id('enter-roast-btn')).to_be_disabled()
    page.get_by_test_id('disclaimer-checkbox').check(); page.get_by_test_id('enter-roast-btn').click()
    expect(page.get_by_test_id('splash-login-btn')).to_be_visible()
    # Unprovisioned email is absent rather than a fake success button.
    expect(page.get_by_test_id('preview-login-btn')).to_be_visible()
    page.get_by_test_id('preview-login-btn').click()
    expect(page.get_by_test_id('roast-studio')).to_be_visible(timeout=15000)
    nav(page, 'credits', 'credits-page')
    expect(page.get_by_test_id('buy-credits_starter-btn')).to_be_disabled()
    assert not fixture.unexpected, fixture.unexpected
    context.close()
    return {'scope': '21+ landing + Explore + preview cannot purchase', 'passed': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--report', type=Path, default=ROOT / '.private/render-transition/ui-report.json')
    parser.add_argument('--chromium', help='Optional explicitly installed Chromium/headless-shell executable')
    args = parser.parse_args()
    build = args.build.resolve()
    if not (build / 'index.html').is_file(): parser.error('Build directory must contain index.html')
    with tempfile.TemporaryDirectory(prefix='roastbox-ui-fixture-') as temp:
        video_path = Path(temp) / 'offline.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi', '-i', 'color=c=purple:s=320x568:r=15:d=2',
                        '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video_path)], check=True)
        video = video_path.read_bytes()
        with sync_playwright() as p:
            options = dict(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-background-networking',
                                               '--disable-component-update', '--disable-sync', '--proxy-server=http://127.0.0.1:9'])
            if args.chromium: options['executable_path'] = args.chromium
            browser = p.chromium.launch(**options)
            try:
                results = [run_landing(browser, build, video)]
                for viewport in ({'width': 1440, 'height': 900}, {'width': 390, 'height': 844}):
                    for inferno in (True, False):
                        result = run_workflow(browser, build, video, viewport, inferno=inferno, full=inferno)
                        results.append(result); print('PASS:', json.dumps(result), flush=True)
            finally: browser.close()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({'scope': 'offline fixture UI wiring only', 'results': results,
                                      'not_proven': ['real provider output/voices', 'real-origin Google and Stripe/Blob integration', 'physical devices, iframe downloads or native Windows']}, indent=2) + '\n')
    print('PASS: offline built-frontend workflows; no production API, cloud or customer data was used.')


if __name__ == '__main__':
    main()
