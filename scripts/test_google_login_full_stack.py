#!/usr/bin/env python3
"""Exercise the browser, real FastAPI auth routes and MongoDB against a local provider stub.

The frontend preview must already be running on localhost:3000. Requires Python
Playwright + Chromium and a local MongoDB. Uses and drops a random temporary
MongoDB database; never contacts Google, pays for services, or touches user data.
"""
from __future__ import annotations

from ui_helpers import accept_adult_consent, accept_adult_consent_async

import json
import os
import socket
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect
from pymongo import MongoClient
import uvicorn

from test_google_login_ui import APP, PROVIDER_START, callback_for, iframe_page

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
test_db = f"roastbox_google_e2e_{uuid.uuid4().hex[:12]}"
os.environ.update({
    "MONGO_URL": os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017"),
    "DB_NAME": test_db,
    "JWT_SECRET": "not-a-production-secret-for-the-local-e2e-test",
    "EMERGENT_LLM_KEY": "",
    "ELEVENLABS_API_KEY": "",
    "STRIPE_API_KEY": "",
    "STORAGE_BACKEND": "local",
    "ENABLE_PREVIEW_LOGIN": "false",
    "ALLOW_DEV_LOGIN": "false",
})

import routes.auth as auth_routes
import server

PROVIDER_TOKEN = "local-provider-token-not-an-app-session"
EMAIL = "full-stack-google-test@example.invalid"
requests_seen = []


class ProviderStub(BaseHTTPRequestHandler):
    def do_GET(self):
        session_id = self.headers.get("X-Session-ID")
        requests_seen.append((self.path, session_id))
        valid = session_id == "offline-valid-google-session"
        payload = ({"email": EMAIL, "name": "Google Test User", "email_verified": True, "session_token": PROVIDER_TOKEN}
                   if valid else {"detail": "invalid"})
        body = json.dumps(payload).encode()
        self.send_response(200 if valid else 401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def main():
    mongo = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
    mongo.admin.command("ping")
    provider = ThreadingHTTPServer(("127.0.0.1", 0), ProviderStub)
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    auth_routes.EMERGENT_AUTH_URL = f"http://127.0.0.1:{provider.server_address[1]}/auth/v1/env/oauth/session-data"
    server.prune_audio_cache = lambda: 0
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    api_port = sock.getsockname()[1]
    api = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=api_port, log_level="warning"))
    api_thread = threading.Thread(target=api.run, kwargs={"sockets": [sock]}, daemon=True)
    api_thread.start()
    try:
        deadline = time.time() + 20
        while not api.started and time.time() < deadline:
            time.sleep(0.05)
        assert api.started, "test API did not start"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context()

            def forward(route):
                parsed = urlparse(route.request.url)
                url = f"http://127.0.0.1:{api_port}{parsed.path}"
                if parsed.query:
                    url += "?" + parsed.query
                # Model a preview proxy that consumes Authorization and cookies.
                # The app-specific session header must still reach the real API.
                headers = dict(route.request.all_headers())
                headers.pop("authorization", None)
                headers["cookie"] = ""
                route.fulfill(response=route.fetch(url=url, headers=headers))

            context.route("**/api/**", forward)
            context.route(PROVIDER_START + "**", lambda route: route.fulfill(
                status=200, content_type="text/html", body="<h1>Offline Google provider</h1>"))
            page = context.new_page()

            def top_level_sign_in(session_id):
                page.goto(APP, wait_until="domcontentloaded")
                accept_adult_consent(page)
                page.get_by_test_id("splash-login-btn").click()
                page.wait_for_url(PROVIDER_START + "**")
                callback, _ = callback_for(page.url)
                page.goto(callback + "#session_id=" + session_id)

            top_level_sign_in("offline-valid-google-session")
            page.wait_for_url("**/studio", timeout=20000)
            first_token = page.evaluate("localStorage.getItem('roastbox_token')")
            first_user = mongo[test_db].users.find_one({"email": EMAIL})
            assert first_user and first_user["credits"] == 25 and first_token != PROVIDER_TOKEN
            assert mongo[test_db].sessions.find_one({"session_token": first_token, "user_id": first_user["id"]})
            mongo[test_db].users.update_one({"id": first_user["id"]}, {"$set": {"credits": 73}})
            page.get_by_test_id("logout-btn").click()
            page.wait_for_url(APP + "/", timeout=10000)
            assert not mongo[test_db].sessions.find_one({"session_token": first_token})
            top_level_sign_in("offline-valid-google-session")
            page.wait_for_url("**/studio", timeout=20000)
            expect(page.get_by_test_id("credit-pill")).to_contain_text("73 Credits", timeout=10000)
            assert mongo[test_db].users.count_documents({"email": EMAIL}) == 1
            print("PASS: browser → real API → stub provider → MongoDB → studio; repeat login preserves credits and logout revokes")

            context.unroute_all(behavior="wait")
            context.close()
            context = browser.new_context()
            context.route("**/api/**", forward)
            context.route(PROVIDER_START + "**", lambda route: route.fulfill(
                status=200, content_type="text/html", body="<h1>Offline Google provider</h1>"))
            page, frame = iframe_page(context)
            accept_adult_consent(frame)
            with page.expect_popup() as opened:
                frame.get_by_test_id("splash-login-btn").click()
            popup = opened.value
            popup.wait_for_url(PROVIDER_START + "**")
            callback, _ = callback_for(popup.url)
            popup.evaluate("url => { window.location.href = url; }", callback + "#session_id=offline-valid-google-session")
            frame.wait_for_url("**/studio", timeout=20000)
            expect(frame.get_by_test_id("credit-pill")).to_contain_text("73 Credits", timeout=10000)
            token = frame.evaluate("localStorage.getItem('roastbox_token')")
            assert token != PROVIDER_TOKEN and mongo[test_db].sessions.find_one({"session_token": token})
            assert len(requests_seen) == 3 and all(sid == "offline-valid-google-session" for _, sid in requests_seen)
            print("PASS: embedded popup completes against real API and database without exposing the provider token")
            context.unroute_all(behavior="wait")
            context.close()
            browser.close()
    finally:
        api.should_exit = True
        api_thread.join(timeout=10)
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=3)
        mongo.drop_database(test_db)
        mongo.close()


if __name__ == "__main__":
    main()
