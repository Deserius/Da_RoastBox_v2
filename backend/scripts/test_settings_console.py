"""Offline checks for the owner settings console.

No provider is called and no database is required: the app is driven through
an in-memory Motor substitute, so these assertions are safe to run anywhere.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "roastbox_console_test")
os.environ.setdefault("JWT_SECRET", "0123456789abcdef0123456789abcdef")
os.environ["APP_ENV"] = "development"
os.environ["ALLOW_RUNTIME_SETTINGS"] = "true"
os.environ["RUNTIME_SETTINGS_PASSPHRASE"] = "test-passphrase"
os.environ["ENABLE_PREVIEW_LOGIN"] = "true"
# Needed only to mint a NON-preview account for the authorisation check below.
os.environ["ALLOW_DEV_LOGIN"] = "true"
os.environ["PREVIEW_UNLIMITED_CREDITS"] = "true"

# Point the console's persistence at a throwaway file before the app boots, so a
# test run can never leave placeholder credentials in the real backend/.env.
import tempfile  # noqa: E402

from services import env_writer  # noqa: E402

_TMPDIR = tempfile.mkdtemp(prefix="roastbox-console-test-")
env_writer.SECRETS_FILE = Path(_TMPDIR) / ".env"
# Ambient declarations would legitimately outrank a console save; clear them so
# the assertions describe the console alone.
for _k in ("OPENAI_API_KEY", "ROAST_WRITER_PROVIDER", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"):
    os.environ.pop(_k, None)

import mongomock_motor  # noqa: E402
import motor.motor_asyncio as motor_asyncio  # noqa: E402

motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

from fastapi.testclient import TestClient  # noqa: E402

from services import env_writer  # noqa: E402

import server  # noqa: E402


def check(name, condition, detail=""):
    if not condition:
        raise AssertionError(f"{name} failed{': ' + detail if detail else ''}")
    print(f"PASS: {name}")


def main():
    try:
        _run()
    finally:
        import shutil
        shutil.rmtree(_TMPDIR, ignore_errors=True)


def _run():
    with TestClient(server.app) as client:
        preview = client.post("/api/auth/preview-login").json()
        ph = {"Authorization": f"Bearer {preview['session_token']}"}

        me = client.get("/api/auth/me", headers=ph).json()
        check("preview account reports unlimited credits", me["unlimited_credits"] is True)
        check("preview account has every add-on unlocked",
              all(me[k] for k in ("premium_personas_unlocked", "premium_voices_unlocked",
                                  "roast_battle_unlocked", "nsfw_edgier_unlocked")))

        check("console starts locked", client.get("/api/settings/console", headers=ph).json()["unlocked"] is False)
        check("wrong passphrase is rejected",
              client.post("/api/settings/console/unlock", json={"passphrase": "nope"}, headers=ph).status_code == 401)
        check("writes are refused while locked",
              client.put("/api/settings/console", json={"keys": {"OPENAI_API_KEY": "sk-x"}}, headers=ph).status_code == 403)
        check("correct passphrase unlocks",
              client.post("/api/settings/console/unlock", json={"passphrase": "test-passphrase"}, headers=ph).status_code == 200)

        saved = client.put("/api/settings/console",
                           json={"keys": {"OPENAI_API_KEY": "sk-console-value", "ROAST_WRITER_PROVIDER": "existing"}},
                           headers=ph)
        check("console stores a key", saved.status_code == 200, saved.text[:160])
        state = client.get("/api/settings/console", headers=ph).json()
        check("stored key is reported as console-sourced",
              state["secrets"]["OPENAI_API_KEY"]["source"] == "console")
        check("passphrase is never echoed", "test-passphrase" not in str(state))
        check("plaintext key is never returned", "sk-console-value" not in str(state))

        diag = client.get("/api/diagnostics").json()["config"]
        check("diagnostics reflects the console key without a restart", diag["openai_hosted_key"] is True)

        cleared = client.delete("/api/settings/console?scope=OPENAI_API_KEY", headers=ph)
        check("clearing one key works", cleared.status_code == 200)
        check("cleared key is no longer configured",
              client.get("/api/settings/console", headers=ph).json()["secrets"]["OPENAI_API_KEY"]["configured"] is False)

        client.post("/api/settings/console/lock", headers=ph)
        check("locking works", client.get("/api/settings/console", headers=ph).json()["unlocked"] is False)

        # The passphrase is the gate, not the account type: an owner signing in
        # normally must be able to configure their own deployment. (Gating on
        # preview-only previously 403'd the very person entitled to do this.)
        real = client.post("/api/auth/dev-login", json={"email": "real@customer.test", "name": "Real"}).json()
        rh = {"Authorization": f"Bearer {real['session_token']}"}
        check("a normal signed-in owner can read the console",
              client.get("/api/settings/console", headers=rh).status_code == 200)
        check("a normal signed-in owner can unlock with the passphrase",
              client.post("/api/settings/console/unlock", json={"passphrase": "test-passphrase"},
                          headers=rh).status_code == 200)
        check("a wrong passphrase is still refused",
              client.post("/api/settings/console/unlock", json={"passphrase": "nope"},
                          headers=rh).status_code == 401)

        check("anonymous access is refused", client.get("/api/settings/console").status_code == 401)

        # Regression: Google sign-in state must reflect a stored credential
        # immediately, without a restart (config is snapshotted at import).
        before = client.get("/api/auth/email/status").json()["google_login_available"]
        unlock_again = client.post("/api/settings/console/unlock", json={"passphrase": "test-passphrase"}, headers=ph)
        check("preview account can unlock again", unlock_again.status_code == 200)
        client.put("/api/settings/console", headers=ph, json={
            "keys": {"GOOGLE_CLIENT_ID": "999-abc.apps.googleusercontent.com",
                     "GOOGLE_CLIENT_SECRET": "GOCSPX-testsecret"},
            "mode": "apply", "persist_env": False})
        after = client.get("/api/auth/email/status").json()["google_login_available"]
        check("Google sign-in turns on after saving credentials", after is True and before is False,
              f"before={before} after={after}")

        # Regression: env-status must report gitignore protection truthfully,
        # not just whether this request happened to add the rule.
        env = client.get("/api/settings/env-status", headers=ph).json()
        check("env-status reports the file is gitignored", env["gitignored"] is True, str(env))
        check("env-status names the secrets file", env["file"] == "backend/.env", str(env))


main()
print("PASS: settings console guards, live wiring and secret hygiene")
