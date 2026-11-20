#!/usr/bin/env python3
"""No-cost HTTP smoke checks for the workspace's actual API proxy and routes.

The isolated preview login must be enabled. This script does not call AI,
payment, voice, or Google providers and never creates a real purchase.
"""
import os
import sys
import requests

BASE = os.environ.get("ROASTBOX_TEST_ORIGIN", "http://127.0.0.1:3000").rstrip("/") + "/api"
session = requests.Session()
response = session.post(BASE + "/auth/preview-login", timeout=15)
if response.status_code != 200:
    sys.exit(f"Preview login unavailable: HTTP {response.status_code}")
token = response.json()["session_token"]
headers = {"X-Roastbox-Session": token}
checks = [
    ("GET", "/health", 200, {}),
    ("GET", "/diagnostics", 200, {}),
    ("GET", "/diagnostics?deep=true", 403, {}),
    ("GET", "/auth/me", 200, {}),
    ("GET", "/personas", 200, {}),
    ("GET", "/personas/no-such-persona/voice-preview", 404, {}),
    ("GET", "/roast/cost-quote", 200, {}),
    ("GET", "/roast/history", 200, {}),
    ("GET", "/battle/access", 200, {}),
    ("GET", "/payments/packs", 200, {}),
    ("GET", "/payments/activity", 200, {}),
    ("GET", "/payments/status/no-such-session", 404, {}),
    ("GET", "/share/no-such-share", 404, {}),
    ("GET", "/reels/no-such-reel", 404, {}),
    ("GET", "/reels/no-such-reel/video.mp4", 404, {}),
    ("GET", "/media/subject/no-such-roast/0.jpg", 404, {}),
    ("GET", "/audio/no-such-audio.mp3", 404, {}),
    ("POST", "/roast/generate", 422, {}),
    ("POST", "/battle/generate", 400, {"data": {"adult_subjects_confirmed": "true", "persona_a": "persona_1", "persona_b": "persona_1"}}),
    ("POST", "/roast/no-such-roast/share", 404, {}),
    ("POST", "/roast/no-such-roast/reel", 404, {"json": {"length": 30}}),
    ("POST", "/voice-settings/keys", 400, {"json": {}}),
    ("POST", "/payments/checkout", 403, {"json": {"pack_id": "credits_starter", "origin_url": "http://127.0.0.1:3000"}}),
]
try:
    for method, path, expected, kwargs in checks:
        res = session.request(method, BASE + path, headers=headers, timeout=15, **kwargs)
        if res.status_code != expected:
            raise AssertionError(f"{method} {path}: expected {expected}, got {res.status_code}: {res.text[:200]}")
        print(f"PASS: {method} {path} → {expected}")
finally:
    session.post(BASE + "/auth/logout", headers=headers, timeout=15)
assert session.get(BASE + "/auth/me", headers=headers, timeout=15).status_code == 401
print("PASS: logout revokes the preview session")
print("NOTE: live AI, voice and Stripe still require the owner's provider credentials and separate live tests.")
