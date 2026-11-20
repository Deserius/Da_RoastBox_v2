#!/usr/bin/env python3
"""No-cost production-serving and Render-configuration checks.

Uses a throwaway Mongo database and temporary media/files, then deletes them.
It does not call Google, Stripe, AI or object-storage providers.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT))
test_db = f"roastbox_deploy_test_{uuid.uuid4().hex[:12]}"


def main():
    with tempfile.TemporaryDirectory(prefix="roastbox-deployment-") as temp:
        temp = Path(temp)
        frontend = temp / "frontend"
        (frontend / "static/js").mkdir(parents=True)
        (frontend / "index.html").write_text("<html><body>SPA shell</body></html>", encoding="utf-8")
        (frontend / "auth-complete.html").write_text("<html>OAuth bridge</html>", encoding="utf-8")
        (frontend / "static/js/app.js").write_text("window.example = true;", encoding="utf-8")
        media = temp / "persistent-media"
        os.environ.update({
            "MONGO_URL": os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017"),
            "DB_NAME": test_db,
            "JWT_SECRET": "temporary-test-secret-not-for-production",
            "FRONTEND_BUILD_DIR": str(frontend),
            "STORAGE_BACKEND": "local",
            "LOCAL_STORAGE_DIR": str(media),
            "ENABLE_PREVIEW_LOGIN": "false",
            "ALLOW_DEV_LOGIN": "false",
            "ALLOW_SOURCE_DOWNLOAD": "false",
            "ALLOW_PREVIEW_HOSTED_AI": "false",
            "APP_BASE_URL": "",
            "RENDER_EXTERNAL_URL": "https://example.onrender.com",
            "EMERGENT_LLM_KEY": "",
            "OPENAI_API_KEY": "",
            "ELEVENLABS_API_KEY": "",
            "STRIPE_API_KEY": "",
            "STRIPE_WEBHOOK_SECRET": "",
        })
        from fastapi.testclient import TestClient
        from pymongo import MongoClient
        import yaml
        import config
        import services.storage as storage
        import routes.download as download_routes
        from server import app

        mongo = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
        try:
            mongo.admin.command("ping")
            blueprint = yaml.safe_load((PROJECT / "render.yaml").read_text())
            assert len(blueprint["services"]) == 1
            service = blueprint["services"][0]
            env = {item["key"]: item for item in service["envVars"] if "key" in item}
            assert service["runtime"] == "docker" and service["numInstances"] == 1
            assert service["healthCheckPath"] == "/api/health"
            assert service["disk"]["mountPath"] == "/var/data" and service["disk"]["sizeGB"] >= 1
            assert env["MONGO_URL"].get("sync") is False and env["JWT_SECRET"].get("generateValue") is True
            for name in ("ENABLE_PREVIEW_LOGIN", "ALLOW_DEV_LOGIN", "ALLOW_SOURCE_DOWNLOAD", "ALLOW_PREVIEW_HOSTED_AI"):
                assert env[name]["value"] == "false"
            assert env["LOCAL_STORAGE_DIR"]["value"].startswith("/var/data/")
            assert config.APP_BASE_URL == "https://example.onrender.com" and config.LOCAL_STORAGE_DIR == media
            print("PASS: Blueprint uses one worker, persistent media, generated secret and safe production flags")
            with TestClient(app) as client:
                for path in ("/", "/studio", "/auth/callback", "/r/test-share"):
                    response = client.get(path)
                    assert response.status_code == 200 and "SPA shell" in response.text, path
                    assert response.headers.get("cache-control") == "no-cache"
                assert client.get("/auth-complete.html").text == "<html>OAuth bridge</html>"
                assert client.get("/static/js/app.js").status_code == 200
                for path in ("/static/js/missing.js", "/assets/missing.mp3"):
                    assert client.get(path).status_code == 404, path
                missing_api = client.get("/api/no-such-route")
                assert missing_api.status_code == 404 and missing_api.headers["content-type"].startswith("application/json")
                assert client.get("/api", follow_redirects=False).status_code == 307
                assert client.get("/api/health").json()["status"] == "ok"
                assert client.get("/api/payments/activity").status_code == 401
                assert client.post("/api/auth/preview-login").status_code == 404
                assert client.post("/unknown-path").status_code == 405
                print("PASS: SPA deep links and OAuth bridge work; missing assets and API routes remain 404s")
                print("PASS: health, auth isolation and disabled preview login work in production mode")
                # Even the optional, normally-disabled source export must omit
                # private envs, credential formats, data directories and symlinks.
                source = temp / "source-fixture"
                (source / "backend/local_storage").mkdir(parents=True)
                (source / "frontend").mkdir()
                (source / "backend/.env").write_text("PRIVATE_ENV_FIXTURE")
                (source / "backend/.env.example").write_text("TEMPLATE_ONLY")
                (source / "backend/local_storage/private.jpg").write_text("PRIVATE_MEDIA_FIXTURE")
                for name in ("credential.key", "private.pem", "credentials.json", "token.json", "data.sqlite3", ".netrc"):
                    (source / name).write_text("PRIVATE_FIXTURE")
                (source / "safe.py").write_text("print('safe')")
                try:
                    (source / "linked-secret.txt").symlink_to(source / "credential.key")
                except (OSError, NotImplementedError):
                    pass
                old_root, old_allow = download_routes.APP_ROOT, download_routes.ALLOW_SOURCE_DOWNLOAD
                try:
                    download_routes.APP_ROOT, download_routes.ALLOW_SOURCE_DOWNLOAD = source, True
                    exported = client.get("/api/download/source.zip")
                    assert exported.status_code == 200
                    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
                        names = set(archive.namelist())
                        assert names == {"da_roastbox/safe.py", "da_roastbox/backend/.env.example"}, names
                        assert b"PRIVATE_" not in b"".join(archive.read(name) for name in names)
                finally:
                    download_routes.APP_ROOT, download_routes.ALLOW_SOURCE_DOWNLOAD = old_root, old_allow
                print("PASS: optional source export excludes private data, credentials and symlinks")
                asyncio.run(storage.put_blob("tests/sample.bin", b"local-storage-test", "application/octet-stream"))
                assert (media / "da-roastbox/tests/sample.bin").read_bytes() == b"local-storage-test"
                assert asyncio.run(storage.get_blob("tests/sample.bin")) == b"local-storage-test"
                try:
                    storage._local_path("../../outside")
                    raise AssertionError("path traversal was not rejected")
                except ValueError:
                    pass
                print("PASS: configured persistent media path works and rejects path traversal")
        finally:
            mongo.drop_database(test_db)
            mongo.close()
    print("Deployment checks completed without paid services.")


if __name__ == "__main__":
    main()
