#!/usr/bin/env python3
"""Offline email authentication checks; mock SMTP, use an isolated Mongo DB.

No Google, Stripe, AI, or actual email delivery requests are made.
"""
from __future__ import annotations
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
test_db = f"roastbox_email_test_{uuid.uuid4().hex[:12]}"
os.environ.update({"MONGO_URL": os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017"),
    "DB_NAME": test_db, "JWT_SECRET": "offline-email-test-secret-not-for-production",
    "EMAIL_AUTH_ENABLED": "true", "SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587",
    "SMTP_TLS_MODE": "starttls", "SMTP_FROM": "Da RoastBox <hello@example.com>",
    "SMTP_USERNAME": "", "SMTP_PASSWORD": "", "APP_BASE_URL": "https://roastbox.example.com",
    "STORAGE_BACKEND": "local", "ENABLE_PREVIEW_LOGIN": "false", "ALLOW_DEV_LOGIN": "false",
    "ALLOW_PREVIEW_HOSTED_AI": "false", "EMERGENT_LLM_KEY": "", "OPENAI_API_KEY": ""})

from fastapi.testclient import TestClient
from pymongo import MongoClient
from server import app
from models import User
import config
import routes.auth as google
import services.email_auth as email_service

outbox = []
async def fake_send(recipient, subject, body):
    outbox.append((recipient, subject, body))
email_service.send_mail = fake_send


def check(condition, label):
    if not condition: raise AssertionError(label)
    print('PASS:', label, flush=True)


def link_token():
    match = re.search(r'#token=([A-Za-z0-9_-]+)', outbox[-1][2])
    assert match, 'expected an emailed one-time link'
    return match.group(1)


def main():
    mongo = MongoClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=5000)
    mongo.admin.command('ping')
    db = mongo[test_db]
    try:
        with TestClient(app) as client:
            status = client.get('/api/auth/email/status')
            check(status.status_code == 200 and status.json()['registration_available'], 'optional email auth reports configured capabilities')
            address = 'new-user@example.com'
            password = 'correct horse roast battery staple'
            prelogin = client.post('/api/auth/email/login', json={'email': address, 'password': password})
            check(prelogin.status_code == 401, 'unverified accounts cannot sign in')
            sent = client.post('/api/auth/email/register', json={'email': address})
            token = link_token()
            check(sent.status_code == 202 and db.users.count_documents({'email': address}) == 0 and
                  db.email_credentials.count_documents({'email': address}) == 0,
                  'registration requires mailbox verification before creating an account or password')
            stored = db.email_tokens.find_one({'email': address})
            check(stored and token not in str(stored) and '#token=' in outbox[-1][2],
                  'only a token hash is stored and the link uses a URL fragment')
            check(client.post('/api/auth/email/verify', json={'token': token, 'password': 'short'}).status_code == 422,
                  'short passwords are rejected')
            verified = client.post('/api/auth/email/verify', json={'token': token, 'password': password})
            cred = db.email_credentials.find_one({'email': address})
            check(verified.status_code == 200 and cred and password not in str(cred) and cred['password_hash'].startswith('scrypt$32768$'),
                  'verified mailbox owner chooses a salted scrypt password')
            check(client.post('/api/auth/email/verify', json={'token': token, 'password': password}).status_code == 400,
                  'verification tokens are one-time use')
            wrong = client.post('/api/auth/email/login', json={'email': address, 'password': 'not the correct password'})
            unknown = client.post('/api/auth/email/login', json={'email': 'unknown@example.com', 'password': 'not the correct password'})
            check(wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json(),
                  'unknown email and wrong password return the same failure')
            signed_in = client.post('/api/auth/email/login', json={'email': address.upper(), 'password': password})
            session = signed_in.json()['session_token']
            check(signed_in.status_code == 200 and client.get('/api/auth/me', headers={'Authorization': f'Bearer {session}'}).status_code == 200,
                  'email sign-in issues the existing revocable app session')
            check('HttpOnly' in signed_in.headers.get('set-cookie', '') and 'Secure' in signed_in.headers.get('set-cookie', ''),
                  'email login session cookie is HttpOnly and Secure')

            # A verified mailbox can add email sign-in to an existing mixed-case
            # Google account without replacing its credits or entitlements.
            existing = User(email='MixedCase@Example.com', name='Existing Google User', credits=47, roast_battle_unlocked=True)
            db.users.insert_one(existing.model_dump())
            client.post('/api/auth/email/register', json={'email': 'mixedcase@example.com'})
            linked_token = link_token()
            linked = client.post('/api/auth/email/verify', json={'token': linked_token, 'password': password})
            linked_cred = db.email_credentials.find_one({'email': 'mixedcase@example.com'})
            linked_login = client.post('/api/auth/email/login', json={'email': 'MIXEDCASE@EXAMPLE.COM', 'password': password})
            check(linked.status_code == 200 and linked_cred['user_id'] == existing.id and
                  linked_login.json()['user']['credits'] == 47 and db.users.count_documents({'id': existing.id}) == 1,
                  'mailbox verification links to the existing Google account without losing purchases')

            # Managed Google exchange is mocked: repeat login must converge on
            # the same mixed-case account and retain all its entitlements.
            original = google.httpx.AsyncClient
            class FakeResponse:
                status_code = 200
                def json(self): return {'email': 'MIXEDCASE@example.com', 'name': 'Google Updated', 'session_token': 'provider-only'}
            class FakeClient:
                def __init__(self, **kw): pass
                async def __aenter__(self): return self
                async def __aexit__(self, *args): pass
                async def get(self, *args, **kwargs): return FakeResponse()
            google.httpx.AsyncClient = FakeClient
            try:
                result = client.post('/api/auth/session', json={'session_id': 'offline-only'})
                check(result.status_code == 200 and result.json()['user']['id'] == existing.id and result.json()['user']['credits'] == 47 and
                      db.users.find_one({'id': existing.id})['roast_battle_unlocked'],
                      'mocked Google sign-in converges case-insensitively on the same account')
            finally:
                google.httpx.AsyncClient = original

            client.post('/api/auth/email/forgot', json={'email': address})
            reset = link_token()
            new_password = 'another sufficiently long password'
            changed = client.post('/api/auth/email/reset', json={'token': reset, 'password': new_password})
            check(changed.status_code == 200 and client.get('/api/auth/me', headers={'Authorization': f'Bearer {session}'}).status_code == 401,
                  'password reset revokes existing app sessions')
            check(client.post('/api/auth/email/reset', json={'token': reset, 'password': new_password}).status_code == 400 and
                  client.post('/api/auth/email/login', json={'email': address, 'password': password}).status_code == 401 and
                  client.post('/api/auth/email/login', json={'email': address, 'password': new_password}).status_code == 200,
                  'reset token is single-use and only the new password works')
            duplicate = client.post('/api/auth/email/register', json={'email': address})
            check(duplicate.status_code == 202 and '#token=' not in outbox[-1][2] and
                  client.post('/api/auth/email/login', json={'email': address, 'password': new_password}).status_code == 200,
                  'repeat registration cannot replace an established password')

            expired_email = 'expired@example.com'
            client.post('/api/auth/email/register', json={'email': expired_email})
            expired = link_token()
            db.email_tokens.update_one({'email': expired_email}, {'$set': {'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)}})
            check(client.post('/api/auth/email/verify', json={'token': expired, 'password': password}).status_code == 400,
                  'expired links are rejected even before Mongo TTL cleanup')
            cross = client.post('/api/auth/email/forgot', json={'email': 'cross@example.com'}, headers={'Origin': 'https://evil.example.com'})
            check(cross.status_code == 403, 'cross-site requests cannot use cookie-bearing auth endpoints')
            for i in range(3):
                r = client.post('/api/auth/email/register', json={'email': 'ratelimit@example.com'})
                assert r.status_code == 202, r.text
            r = client.post('/api/auth/email/register', json={'email': 'ratelimit@example.com'})
            check(r.status_code == 429 and r.headers.get('retry-after'), 'persistent per-address rate limiting is enforced')
            config.SMTP_HOST = ''
            status = client.get('/api/auth/email/status').json()
            check(status['login_available'] and not status['registration_available'] and
                  client.post('/api/auth/email/forgot', json={'email': address}).status_code == 503,
                  'missing SMTP blocks new mail flows without disabling existing email sign-in')
            config.EMAIL_AUTH_ENABLED = False
            check(client.post('/api/auth/email/login', json={'email': address, 'password': new_password}).status_code == 503,
                  'email sign-in is disabled unless explicitly enabled')
    finally:
        mongo.drop_database(test_db)
        mongo.close()


if __name__ == '__main__':
    main()
