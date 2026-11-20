#!/usr/bin/env python3
"""Offline one-click startup coverage; never installs packages or calls providers."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import launcher_common as common
import local_start as launcher

spec = importlib.util.spec_from_file_location("one_click_installer", ROOT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class OneClickTests(unittest.TestCase):
    def test_windows_bat_bootstrap_and_quoted_paths(self):
        for name in ("LAUNCH_DA_ROASTBOX.bat", "start.bat", "install.bat"):
            raw = (ROOT / name).read_bytes()
            self.assertIn(b"\r\n", raw)
            self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
            self.assertIn(b"DisableDelayedExpansion", raw)
            self.assertFalse(any(c < 32 and c not in (9, 10, 13) for c in raw))
        alias = (ROOT / "LAUNCH_DA_ROASTBOX.bat").read_text()
        self.assertIn('"%~dp0start.bat" %*', alias)
        self.assertIn('ZIP viewer', alias)
        bat = (ROOT / "start.bat").read_text()
        self.assertIn('"%~dp0install.bat" --start %*', bat)
        self.assertNotIn('call "%~dp0install.bat"', bat.lower())
        self.assertIn('cd /d "%~dp0"', bat)
        self.assertIn('if not exist "%~dp0install.py"', bat)
        bootstrap = (ROOT / "install.bat").read_text()
        self.assertIn('-NoLogo -NoProfile -ExecutionPolicy Bypass -File', bootstrap)
        self.assertIn('-ProjectRoot "%~dp0." %*', bootstrap)
        self.assertIn('Sysnative', bootstrap)
        self.assertNotIn('winget install', bootstrap)
        self.assertIn('pause', bootstrap)
        ps = (ROOT / "scripts/bootstrap_python.ps1").read_text()
        for required in ('Get-RegisteredPythonPaths', 'WindowsApps', 'sys.maxsize>2**32',
                         'Get-FileHash', 'Get-AuthenticodeSignature', 'Python Software Foundation',
                         'InstallAllUsers=0', 'PrependPath=0', 'ValueFromRemainingArguments',
                         'Enter-PythonBootstrapLock', '| Out-Host'):
            self.assertIn(required, ps)
        self.assertNotIn('Invoke-Expression', ps)
        self.assertNotIn('Set-ExecutionPolicy', ps)
        self.assertNotIn('-Verb RunAs', ps)

    def test_windows_32bit_venv_is_rejected_without_data_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            venv = root / ".venv"
            python = venv / "Scripts/python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"unusable x86 fixture")
            sentinel = root / ".data/mongo/keep"
            sentinel.parent.mkdir(parents=True)
            sentinel.write_bytes(b"do not touch")
            with patch.object(installer, "ROOT", root), patch.object(installer, "VENV", venv), \
                 patch.object(installer, "IS_WINDOWS", True), \
                 patch.object(installer.subprocess, "run", return_value=SimpleNamespace(returncode=1)) as probe, \
                 patch.object(installer, "run") as run, patch.object(installer, "require_space"):
                self.assertEqual(installer.ensure_virtualenv(), python)
                self.assertIn("sys.maxsize > 2**32", probe.call_args.args[0][-1])
                self.assertEqual(len(list((root / ".cache").glob("old-venv-*"))), 1)
                run.assert_called_once_with([sys.executable, "-m", "venv", venv])
            self.assertEqual(sentinel.read_bytes(), b"do not touch")

    def test_default_windows_browser_uses_registered_shell(self):
        with patch.object(common, "IS_WINDOWS", True), patch.object(common.os, "startfile", create=True) as shell, patch.object(common.webbrowser, "open") as web:
            self.assertTrue(common.open_default_browser("http://127.0.0.1:3000"))
            shell.assert_called_once_with("http://127.0.0.1:3000")
            web.assert_not_called()

    def test_browser_unavailable_does_not_abort_server(self):
        with patch.object(common, "IS_WINDOWS", True), patch.object(common.os, "startfile", create=True, side_effect=OSError("No browser")):
            self.assertFalse(common.open_default_browser("http://127.0.0.1:3000"))

    def test_file_lock_releases_without_deleting_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "install.lock"
            with common.ProjectLock(p):
                with self.assertRaises(common.AlreadyRunning):
                    with common.ProjectLock(p):
                        self.fail("Duplicate installation acquired the lock")
            with common.ProjectLock(p):
                self.assertTrue(p.is_file())

    def test_duplicate_start_reopens_without_reinstalling(self):
        with patch.object(installer, "app_ready", return_value=True), patch.object(installer, "install_and_launch") as setup, patch.object(installer, "open_default_browser") as browser:
            installer.main(["--start"])
            setup.assert_not_called()
            browser.assert_called_once_with("http://127.0.0.1:3000")

    def test_port_conflict_does_not_kill_anything(self):
        with patch.object(installer, "app_ready", return_value=False), patch.object(installer, "occupied", return_value=True), patch.object(installer, "install_and_launch") as setup:
            with self.assertRaisesRegex(RuntimeError, "occupied"):
                installer.main(["--start"])
            setup.assert_not_called()

    def test_repair_requires_stopping_only_web_app(self):
        with patch.object(installer, "app_ready", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "leave MongoDB running"):
                installer.main(["--start", "--repair"])

    def test_explicit_writer_upgrade_is_available_and_never_changes_a_running_app(self):
        raw = (ROOT / "upgrade_21plus.bat").read_bytes()
        self.assertIn(b"--configure-writer --start", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        with patch.object(installer, "app_ready", return_value=True), patch.object(installer, "install_and_launch") as setup:
            with self.assertRaisesRegex(RuntimeError, "leave MongoDB running"):
                installer.main(["--configure-writer", "--start"])
            setup.assert_not_called()

    def test_windows_mongo_keeps_bundled_cpp_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            def fake_download(_url, archive, *_args):
                with zipfile.ZipFile(archive, "w") as z:
                    z.writestr("vendor/bin/mongod.exe", b"mock executable")
                    z.writestr("vendor/bin/vc_redist.x64.exe", b"mock Microsoft runtime")
            with patch.object(installer, "IS_WINDOWS", True), patch.object(installer, "TOOLS", base / "tools"), \
                 patch.object(installer, "mongo_target", return_value=("windows-x86_64", "windows", "zip")), \
                 patch.object(installer, "download", side_effect=fake_download), patch.object(installer, "run"), \
                 patch.object(installer, "ensure_windows_runtime") as runtime:
                exe = installer.ensure_mongo(base)
                self.assertEqual(exe.read_bytes(), b"mock executable")
                self.assertEqual((exe.parent / "vc_redist.x64.exe").read_bytes(), b"mock Microsoft runtime")
                runtime.assert_called_once_with(exe.parent / "vc_redist.x64.exe")

    def test_windows_cpp_installer_waits_and_handles_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "Project's folder" / "vc_redist.x64.exe"
            p.parent.mkdir(); p.touch()
            host = Path(tmp) / "windows/System32/WindowsPowerShell/v1.0/powershell.exe"
            host.parent.mkdir(parents=True); host.touch()
            with patch.object(installer, "IS_WINDOWS", True), patch.dict(os.environ, {"SystemRoot": str(Path(tmp) / "windows")}), \
                 patch.object(installer.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                installer.ensure_windows_runtime(p)
                command = run.call_args.args[0]
                self.assertEqual(command[0], str(host))
                self.assertIn("Project''s folder", command[-1])
                self.assertIn("-Verb RunAs -Wait -PassThru", command[-1])
                self.assertIn("/install /quiet /norestart", command[-1])
                run.return_value.returncode = 1603
                with self.assertRaisesRegex(RuntimeError, "did not complete"):
                    installer.ensure_windows_runtime(p, force=True)

    def test_existing_mongodb_is_only_pinged(self):
        with patch.object(launcher, "ping", return_value=True), patch.object(launcher, "spawn") as spawn, patch.object(launcher, "stop_web_process") as stop:
            launcher.ensure_database("mongodb://127.0.0.1:27017")
            spawn.assert_not_called(); stop.assert_not_called()

    def test_external_database_is_never_bootstrapped(self):
        with patch.object(launcher, "ping", return_value=False), patch.object(launcher, "spawn") as spawn:
            for uri, flag in (("mongodb://127.0.0.1:27017", True), ("mongodb+srv://database.invalid/", False)):
                with self.assertRaisesRegex(RuntimeError, "not reachable"):
                    launcher.ensure_database(uri, external_only=flag)
            spawn.assert_not_called()

    def test_new_database_is_detached_and_not_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); exe = root / "mongod"; exe.touch()
            sentinel = root / ".data/mongo/keep"; sentinel.parent.mkdir(parents=True); sentinel.write_bytes(b"preserve database")
            process = SimpleNamespace(poll=lambda: None)
            with patch.object(launcher, "ROOT", root), patch.object(launcher, "mongo_executable", return_value=exe), \
                 patch.object(launcher, "ping", side_effect=[False, True]), patch.object(launcher, "occupied", return_value=False), \
                 patch.object(launcher, "spawn", return_value=process) as spawn, patch.object(launcher, "stop_web_process") as stop:
                launcher.ensure_database("mongodb://127.0.0.1:27017")
                self.assertTrue(spawn.call_args.kwargs["detached"])
                stop.assert_not_called()
                self.assertEqual(sentinel.read_bytes(), b"preserve database")

    def test_browser_opens_only_after_api_and_frontend_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "frontend/build").mkdir(parents=True)
            (root / "frontend/build/index.html").write_text("<html>Da RoastBox</html>")
            node = root / "node"; node.touch()
            api, ui = Mock(), Mock()
            api.poll.return_value = ui.poll.return_value = None
            browser_opened = []
            def sleep(_seconds):
                if browser_opened:
                    raise KeyboardInterrupt
            with patch.object(launcher, "ROOT", root), patch.object(launcher, "NODE", node), \
                 patch.dict(os.environ, {"MONGO_URL": "mongodb://127.0.0.1:27017"}), \
                 patch.object(launcher, "occupied", return_value=False), patch.object(launcher, "ensure_database"), \
                 patch.object(launcher, "spawn", side_effect=[api, ui]) as spawn, \
                 patch.object(launcher, "app_ready", side_effect=[False, False, True]) as ready, \
                 patch.object(launcher, "open_default_browser", side_effect=lambda url: browser_opened.append((url, ready.call_count))), \
                 patch.object(launcher.time, "sleep", side_effect=sleep), patch.object(launcher, "stop_web_process") as stop:
                with self.assertRaises(KeyboardInterrupt):
                    launcher.run_local()
                self.assertEqual(browser_opened, [("http://127.0.0.1:3000", 3)])
                self.assertIn("8001", spawn.call_args_list[0].args[0])
                self.assertEqual(spawn.call_args_list[1].kwargs["env"]["PORT"], "3000")
                self.assertEqual(spawn.call_args_list[1].kwargs["env"]["API_PROXY_TARGET"], "http://127.0.0.1:8001")
                self.assertEqual([call.args[0] for call in stop.call_args_list], [ui, api])

    def test_failed_readiness_never_opens_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "frontend/build").mkdir(parents=True)
            (root / "frontend/build/index.html").touch(); node = root / "node"; node.touch()
            api, ui = Mock(), Mock()
            api.poll.return_value = ui.poll.return_value = None
            with patch.object(launcher, "ROOT", root), patch.object(launcher, "NODE", node), \
                 patch.dict(os.environ, {"MONGO_URL": "mongodb://127.0.0.1:27017"}), \
                 patch.object(launcher, "occupied", return_value=False), patch.object(launcher, "ensure_database"), \
                 patch.object(launcher, "spawn", side_effect=[api, ui]), patch.object(launcher, "app_ready", return_value=False), \
                 patch.object(launcher, "open_default_browser") as browser, patch.object(launcher, "stop_web_process") as stop:
                with self.assertRaisesRegex(RuntimeError, "did not become ready"):
                    launcher.run_local(startup_timeout=0)
                browser.assert_not_called()
                self.assertEqual(stop.call_count, 2)

    def test_fast_restart_and_source_rebuild_preserve_env(self):
        with tempfile.TemporaryDirectory(prefix="project with spaces ") as tmp:
            root = Path(tmp)
            for name in ("backend", "frontend/src", "frontend/public", ".cache/tools"):
                (root / name).mkdir(parents=True)
            for name in ("backend/requirements.txt", "frontend/package.json", "frontend/yarn.lock", "frontend/src/app.jsx"):
                (root / name).write_text("fixture")
            for name in ("backend/.env", "frontend/.env"):
                (root / name).write_bytes(b"# preserve exact config\r\nVALUE=unchanged\r\n")
            snapshots = {name: (root / name).read_bytes() for name in ("backend/.env", "frontend/.env")}
            node, yarn, python = (root / "node", root / "yarn.js", root / ".venv/bin/python")
            args = SimpleNamespace(repair=False, with_browser_tests=False, skip_mongodb=True, start=True, no_browser=False, port=None, api_port=None)
            with patch.object(installer, "ROOT", root), patch.object(installer, "TOOLS", root / ".cache/tools"), \
                 patch.object(installer, "ensure_node", return_value=node), patch.object(installer, "ensure_yarn", return_value=yarn), \
                 patch.object(installer, "ensure_virtualenv", return_value=python), \
                 patch.object(installer, "python_dependencies_ready", return_value=True), \
                 patch.object(installer, "frontend_dependencies_ready", return_value=True), \
                 patch.object(installer, "build_ready", return_value=True), patch.object(installer, "require_space") as space, \
                 patch.object(installer, "run") as run:
                installer.install_and_launch(args)
                first = [[str(v) for v in call.args[0]] for call in run.call_args_list]
                self.assertTrue(any("pip" in c and "--require-virtualenv" in c and "--no-cache-dir" in c for c in first))
                self.assertTrue(any("--frozen-lockfile" in c and "--cache-folder" in c for c in first))
                self.assertTrue(any(c[-1] == "build" for c in first))
                self.assertIn("--external-db", first[-1])
                build_call = next(c for c in run.call_args_list if str(c.args[0][-1]) == "build")
                self.assertEqual(build_call.kwargs["env"]["REACT_APP_BACKEND_URL"], "")
                self.assertEqual(build_call.kwargs["env"]["PUBLIC_URL"], "")
                run.reset_mock(); space.reset_mock()
                installer.install_and_launch(args)
                space.assert_not_called()  # Warm startup does not demand fresh-install disk space.
                warm = [[str(v) for v in call.args[0]] for call in run.call_args_list]
                self.assertFalse(any("pip" in c or "--frozen-lockfile" in c or c[-1] == "build" for c in warm))
                (root / "frontend/src/app.jsx").write_text("changed source")
                run.reset_mock(); installer.install_and_launch(args)
                self.assertEqual(sum(str(c.args[0][-1]) == "build" for c in run.call_args_list), 1)
                args.repair = True; run.reset_mock(); installer.install_and_launch(args)
                commands = [[str(v) for v in c.args[0]] for c in run.call_args_list]
                self.assertTrue(any("--force-reinstall" in c for c in commands))
                self.assertTrue(any("--force" in c for c in commands))
            for name, data in snapshots.items():
                self.assertEqual((root / name).read_bytes(), data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
