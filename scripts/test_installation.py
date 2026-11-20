#!/usr/bin/env python3
"""Offline installer safety/unit tests; never invokes installers or paid APIs."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load("roastbox_installer", ROOT / "install.py")
launcher = load("roastbox_launcher", ROOT / "scripts/local_start.py")


class InstallationTests(unittest.TestCase):
    def test_node_platforms_and_hashes(self):
        for system, machine, expected in (
            ("Windows", "AMD64", "win-x64.zip"),
            ("Darwin", "arm64", "darwin-arm64.tar.gz"),
            ("Darwin", "x86_64", "darwin-x64.tar.gz"),
            ("Linux", "x86_64", "linux-x64.tar.gz"),
            ("Linux", "aarch64", "linux-arm64.tar.gz"),
        ):
            with self.subTest(system=system, machine=machine), patch.object(installer.platform, "system", return_value=system), patch.object(installer.platform, "machine", return_value=machine):
                self.assertEqual(installer.node_target(), expected)
                self.assertEqual(len(installer.NODE_HASHES[expected]), 64)

    def test_windows_mongo_target_and_hash(self):
        with patch.object(installer.platform, "system", return_value="Windows"), patch.object(installer.platform, "machine", return_value="AMD64"):
            key, directory, extension = installer.mongo_target()
        self.assertEqual((key, directory, extension), ("windows-x86_64", "windows", "zip"))
        self.assertEqual(len(installer.MONGO_HASHES[key]), 64)

    def test_download_rejects_bad_checksum(self):
        payload = b"local offline fixture"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture"
            with patch.object(installer, "urlopen", side_effect=lambda *_a, **_k: io.BytesIO(payload)):
                installer.download("https://example.invalid/fixture", path, hashlib.sha256(payload).hexdigest())
                self.assertEqual(path.read_bytes(), payload)
                with self.assertRaises(RuntimeError):
                    installer.download("https://example.invalid/fixture", path, "0" * 64)
                self.assertFalse(path.exists())

    def test_only_plain_local_mongo_is_auto_started(self):
        self.assertEqual(launcher.local_mongo_port("mongodb://127.0.0.1:27017"), 27017)
        self.assertEqual(launcher.local_mongo_port("mongodb://localhost:27028/"), 27028)
        for uri in ("mongodb+srv://db.example/", "mongodb://db.example:27017", "mongodb://u:p@localhost:27017", "mongodb://localhost:27017/?tls=true", "mongodb://localhost:27017,host2:27017"):
            self.assertIsNone(launcher.local_mongo_port(uri), uri)

    def test_essential_files_exist_and_data_is_ignored(self):
        for path in ("LAUNCH_DA_ROASTBOX.bat", "scripts/bootstrap_python.ps1", "deploy/windows-bootstrap.json", "install.py", "install.bat", "install.sh", "start.bat", "start.sh", "Dockerfile", "render.yaml", "requirements-test.txt"):
            self.assertTrue((ROOT / path).is_file(), path)
        ignore = (ROOT / ".gitignore").read_text()
        for item in (".env", ".data/", ".cache/", ".venv/", "backend/local_storage/"):
            self.assertIn(item, ignore)
        docker_ignore = (ROOT / ".dockerignore").read_text()
        for item in ("**/.env", ".data", ".cache", ".venv", "**/node_modules", "backend/local_storage"):
            self.assertIn(item, docker_ignore)


if __name__ == "__main__":
    unittest.main(verbosity=2)
