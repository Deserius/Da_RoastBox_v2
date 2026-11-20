#!/usr/bin/env python3
"""Offline disk-full regression coverage; never fills disks or touches real data."""
from __future__ import annotations

import errno
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import installer_storage as storage
spec = importlib.util.spec_from_file_location("storage_test_installer", ROOT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class StorageTests(unittest.TestCase):
    def test_temp_and_package_cache_are_project_local(self):
        with tempfile.TemporaryDirectory(prefix="project with spaces ") as folder:
            root = Path(folder)
            env = storage.installation_environment(root, {"TEMP": "C:/old-temp", "TMP": "C:/old-temp", "PIP_CACHE_DIR": "C:/old-cache", "YARN_CACHE_FOLDER": "C:/old-yarn", "KEEP": "unchanged"})
            for key in ("TEMP", "TMP", "TMPDIR", "PIP_CACHE_DIR", "YARN_CACHE_FOLDER", "NPM_CONFIG_CACHE"):
                self.assertTrue(Path(env[key]).is_relative_to(root), key)
            self.assertEqual(env["PIP_NO_CACHE_DIR"], "1")
            self.assertEqual(env["KEEP"], "unchanged")
            self.assertTrue(Path(env["TEMP"]).is_dir())

    def test_windows_mixed_case_cache_variables_do_not_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            env = storage.installation_environment(Path(folder), {"Temp": "C:/old", "npm_config_cache": "C:/old", "pip_no_cache_dir": "0"})
            self.assertNotIn("Temp", env)
            self.assertNotIn("npm_config_cache", env)
            self.assertNotIn("pip_no_cache_dir", env)
            self.assertEqual(env["PIP_NO_CACHE_DIR"], "1")

    def test_parent_environment_and_user_files_are_untouched(self):
        before = os.environ.copy()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("backend/.env", "frontend/.env", ".data/mongo/keep", "backend/local_storage/keep"):
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b"preserve exactly\r\n")
            storage.installation_environment(root)
            for name in ("backend/.env", "frontend/.env", ".data/mongo/keep", "backend/local_storage/keep"):
                self.assertEqual((root / name).read_bytes(), b"preserve exactly\r\n")
        self.assertEqual(os.environ.copy(), before)

    def test_preflight_stops_early_with_actionable_drive_message(self):
        with patch.object(storage.shutil, "disk_usage", return_value=SimpleNamespace(free=20 * storage.MIB)):
            with self.assertRaises(storage.DiskSpaceError) as raised:
                storage.require_space(ROOT, 2 * storage.GIB, "Python package installation")
        text = str(raised.exception)
        for expected in (str(ROOT), "0.02 GiB", "2.00 GiB", "start.bat", ".data/mongo", ".env"):
            self.assertIn(expected, text)

    def test_preflight_allows_exact_threshold(self):
        with patch.object(storage.shutil, "disk_usage", return_value=SimpleNamespace(free=2 * storage.GIB)):
            storage.require_space(ROOT, 2 * storage.GIB, "Python")

    def test_native_and_localized_windows_disk_full_codes(self):
        for error in (OSError(errno.ENOSPC, "full"), OSError(getattr(errno, "EDQUOT", 122), "quota")):
            self.assertTrue(storage.is_space_error(error))
        windows = OSError("localized Windows message")
        windows.winerror = 112
        self.assertTrue(storage.is_space_error(windows))
        self.assertTrue(storage.is_space_error("ERROR: [WinError 112] localized message"))
        self.assertFalse(storage.is_space_error(PermissionError("Access denied")))
        self.assertFalse(storage.is_space_error("No matching distribution found"))

    def pip_process(self, text, code):
        process = MagicMock()
        process.stdout = io.StringIO(text)
        process.wait.return_value = code
        context = MagicMock()
        context.__enter__.return_value = process
        return context

    def test_original_pip_errno28_is_streamed_and_explained(self):
        output = "Collecting a-package\nERROR: Could not install packages due to an OSError: [Errno 28] No space left on device\n"
        with patch.object(storage.subprocess, "Popen", return_value=self.pip_process(output, 1)), patch.object(sys, "stdout", new_callable=io.StringIO) as stdout:
            with self.assertRaises(storage.DiskSpaceError) as raised:
                storage.run_pip_install(["python", "-m", "pip", "install"], cwd=ROOT, env={}, root=ROOT)
            self.assertIn("[Errno 28]", stdout.getvalue())
        self.assertIn("Storage became full", str(raised.exception))

    def test_other_pip_failure_is_not_mislabeled_as_storage(self):
        with patch.object(storage.subprocess, "Popen", return_value=self.pip_process("ERROR: ResolutionImpossible\n", 1)), patch.object(sys, "stdout", new_callable=io.StringIO):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                storage.run_pip_install(["python", "-m", "pip", "install"], cwd=ROOT, env={}, root=ROOT)
        self.assertIn("ResolutionImpossible", raised.exception.output)

    def test_success_does_not_treat_ordinary_words_as_an_error(self):
        with patch.object(storage.subprocess, "Popen", return_value=self.pip_process("Successfully installed probe\n", 0)), patch.object(sys, "stdout", new_callable=io.StringIO):
            storage.run_pip_install(["python", "-m", "pip", "install"], cwd=ROOT, env={}, root=ROOT)

    def test_normal_subprocess_inherits_local_temp(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(installer, "ROOT", Path(folder)), patch.object(installer.subprocess, "run") as run, patch.object(installer, "run_pip_install") as pip:
            installer.run(["node", "--version"])
            env = run.call_args.kwargs["env"]
            self.assertEqual(env["TMP"], str(Path(folder) / ".cache/install-temp"))
            pip.assert_not_called()

    def test_pip_install_uses_streaming_helper_and_local_environment(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(installer, "ROOT", Path(folder)), patch.object(installer, "run_pip_install") as pip, patch.object(installer.subprocess, "run") as run:
            installer.run(["python", "-m", "pip", "install", "--no-cache-dir", "some-package"])
            self.assertEqual(pip.call_args.kwargs["env"]["PIP_NO_CACHE_DIR"], "1")
            self.assertEqual(pip.call_args.kwargs["root"], Path(folder))
            run.assert_not_called()

    def test_low_space_never_starts_pip_or_creates_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            args = SimpleNamespace(repair=True, with_browser_tests=False, skip_mongodb=True, start=True)
            with patch.object(installer, "ROOT", root), patch.object(installer, "TOOLS", root / ".cache/tools"), \
                 patch.object(installer, "ensure_node", return_value=root / "node"), \
                 patch.object(installer, "ensure_yarn", return_value=root / "yarn.js"), \
                 patch.object(installer, "ensure_virtualenv", return_value=root / "python"), \
                 patch.object(installer, "require_space", side_effect=storage.DiskSpaceError("fixture: insufficient disk")), \
                 patch.object(installer, "run") as run:
                with self.assertRaises(storage.DiskSpaceError):
                    installer.install_and_launch(args)
                run.assert_not_called()
                self.assertFalse((root / "backend/.env").exists())
                self.assertFalse((root / ".data").exists())

    def test_new_virtualenv_is_created_with_redirected_ensurepip_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(installer, "ROOT", root), patch.object(installer, "VENV", root / ".venv"), patch.object(installer, "require_space"), patch.object(installer, "run") as run:
                installer.ensure_virtualenv()
            self.assertEqual(run.call_args.args[0], [sys.executable, "-m", "venv", root / ".venv"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
