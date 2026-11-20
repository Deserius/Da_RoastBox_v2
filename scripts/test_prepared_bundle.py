#!/usr/bin/env python3
"""Offline prepared-runtime safety checks; never starts the app or reads real envs."""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import prepared_runtime as runtime
import prepare_bundle as unpack
import dependency_discovery as discovery
spec = importlib.util.spec_from_file_location("prepared_fixture_installer", ROOT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PreparedBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="roastbox-prepared-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = {
            "runtime/windows-x64/python/Lib/site-packages/fixture.py": b"# installed Windows fixture\n",
            "runtime/windows-x64/node/node.exe": b"node fixture, not executable",
            "runtime/windows-x64/mongodb/mongod.exe": b"mongo fixture, not executable",
            "runtime/windows-x64/yarn/bin/yarn.js": b"// yarn fixture\n",
        }
        self.manifest = {"schema": 1, "platform": "win_amd64", "files": {k: sha(v) for k, v in self.data.items()},
                         "node": "runtime/windows-x64/node/node.exe", "mongod": "runtime/windows-x64/mongodb/mongod.exe",
                         "yarn": "runtime/windows-x64/yarn/bin/yarn.js"}
        for name in ("backend/.env", "frontend/.env", ".data/mongo/KEEP", "backend/local_storage/KEEP"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"KEEP unchanged\n")
        self.write_payload()
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("No networking allowed"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def write_manifest(self):
        target = self.root / "runtime/windows-x64/bundle.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.manifest), encoding="utf-8")

    def write_payload(self, *, extra=None, symlink=False):
        path = self.root / "runtime/windows-x64/installed-runtime.tar.xz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(path, "w:xz") as archive:
            for name, data in self.data.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            if extra:
                member = tarfile.TarInfo(extra)
                if symlink:
                    member.type = tarfile.SYMTYPE
                    member.linkname = "../../backend/.env"
                    archive.addfile(member)
                else:
                    member.size = 1
                    archive.addfile(member, io.BytesIO(b"!"))
        self.manifest["payload"] = {"path": path.relative_to(self.root).as_posix(), "sha256": runtime.file_sha256(path),
                                    "members": list(self.data), "uncompressed_bytes": sum(map(len, self.data.values()))}
        self.write_manifest()

    def assert_data_intact(self):
        for name in ("backend/.env", "frontend/.env", ".data/mongo/KEEP", "backend/local_storage/KEEP"):
            self.assertEqual((self.root / name).read_bytes(), b"KEEP unchanged\n")

    def test_unpack_is_offline_complete_and_preserves_data(self):
        self.assertTrue(unpack.ensure_expanded(self.root))
        for name, data in self.data.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        self.assert_data_intact()
        self.assertTrue(runtime.verify_bundle(self.root))

    def test_repeat_start_does_not_reopen_or_decompress_payload(self):
        unpack.ensure_expanded(self.root)
        with patch.object(unpack.tarfile, "open", side_effect=AssertionError("Unnecessary extraction")):
            self.assertTrue(unpack.ensure_expanded(self.root))
        self.assert_data_intact()

    def test_missing_and_changed_dependency_restored_with_backup(self):
        unpack.ensure_expanded(self.root)
        changed = self.root / self.manifest["node"]
        changed.write_bytes(b"preserve a locally changed runtime")
        (self.root / self.manifest["yarn"]).unlink()
        unpack.ensure_expanded(self.root)
        backups = list((self.root / ".cache").glob("preserved-runtime-*/runtime/windows-x64/node/node.exe"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"preserve a locally changed runtime")
        self.assert_data_intact()

    def test_corrupt_payload_stops_before_any_runtime_is_written(self):
        path = self.root / self.manifest["payload"]["path"]
        path.write_bytes(b"broken archive")
        with self.assertRaisesRegex(RuntimeError, "missing or corrupt"):
            unpack.ensure_expanded(self.root)
        self.assertFalse((self.root / self.manifest["node"]).exists())
        self.assert_data_intact()

    def test_missing_offline_payload_allows_explicit_safe_online_fallback(self):
        (self.root / self.manifest["payload"]["path"]).unlink()
        self.assertFalse(unpack.ensure_expanded(self.root, allow_online_fallback=True))
        self.assertFalse((self.root / self.manifest["node"]).exists())
        self.assert_data_intact()

    def test_archive_traversal_is_rejected_before_commit(self):
        self.write_payload(extra="../../backend/.env")
        with self.assertRaisesRegex(RuntimeError, "Unexpected or unsafe"):
            unpack.ensure_expanded(self.root)
        self.assertFalse((self.root / self.manifest["node"]).exists())
        self.assert_data_intact()

    def test_archive_symlink_is_rejected_before_commit(self):
        self.write_payload(extra="runtime/windows-x64/node/evil", symlink=True)
        with self.assertRaisesRegex(RuntimeError, "Unexpected or unsafe"):
            unpack.ensure_expanded(self.root)
        self.assert_data_intact()

    def test_duplicate_archive_member_is_rejected(self):
        self.write_payload(extra=self.manifest["node"])
        with self.assertRaisesRegex(RuntimeError, "Unexpected or unsafe"):
            unpack.ensure_expanded(self.root)
        self.assert_data_intact()

    def test_payload_destination_cannot_be_configuration_or_database(self):
        for name in ("backend/.env", ".data/mongo/KEEP", "runtime/windows-x64/../backend/.env", "C:/Windows/evil"):
            with self.subTest(name=name):
                manifest = json.loads(json.dumps(self.manifest))
                manifest["payload"]["members"].append(name)
                manifest["files"][name] = "0" * 64
                with self.assertRaises((RuntimeError, ValueError)):
                    unpack.payload_members(manifest)
        self.assert_data_intact()

    def test_safe_member_rejects_absolute_backslash_and_parent_paths(self):
        for name in ("/tmp/evil", "../evil", "a/../evil", "C:/evil", "a\\evil"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                runtime.safe_member(self.root, name)

    def test_symlink_destination_cannot_escape_project(self):
        outside = self.root.parent / (self.root.name + "-outside")
        outside.mkdir()
        self.addCleanup(outside.rmdir)
        link = self.root / "external"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks is restricted on this OS")
        with self.assertRaises(ValueError):
            runtime.safe_member(self.root, "external/evil")

    def test_manifest_schema_and_platform_are_validated(self):
        self.assertIsNotNone(runtime.load_manifest(self.root))
        for value in ([], {"schema": 99}, {"schema": 1, "platform": "linux_x64", "files": {"a": "0" * 64}}):
            (self.root / "runtime/windows-x64/bundle.json").write_text(json.dumps(value))
            self.assertIsNone(runtime.load_manifest(self.root))

    def test_tool_integrity_check_detects_changed_binary(self):
        unpack.ensure_expanded(self.root)
        self.assertEqual(runtime.prepared_tool(self.root, "node"), self.root / self.manifest["node"])
        (self.root / self.manifest["node"]).write_bytes(b"bad node")
        self.assertIsNone(runtime.prepared_tool(self.root, "node"))
        self.assertFalse(runtime.verify_bundle(self.root))

    def test_requirement_change_invalidates_preinstalled_python(self):
        for name in ("backend/requirements.txt", "backend/requirements-runtime.txt"):
            (self.root / name).write_text("# fixture\n")
        self.manifest["requirements_hash"] = runtime.requirements_hash(self.root)
        python = self.root / "runtime/windows-x64/python/python.exe"
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_bytes(b"not executed")
        self.assertEqual(runtime.prepared_python(self.root, self.manifest), python)
        (self.root / "backend/requirements-runtime.txt").write_text("# changed\n")
        self.assertIsNone(runtime.prepared_python(self.root, self.manifest))

    def test_frontend_reuse_requires_matching_source_and_public_configuration(self):
        for name, data in {"frontend/src/App.jsx": "// fixture", "frontend/public/index.html": "<html>",
                           "frontend/yarn.lock": "# fixture", "frontend/package.json": "{}", "frontend/build/index.html": "<html>"}.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)
        env = {"REACT_APP_ENABLE_PREVIEW_LOGIN": "true"}
        self.manifest["frontend_source_hash"] = runtime.source_hash(self.root)
        self.manifest["public_build_environment"] = runtime.public_build_environment(self.root, env)
        self.assertTrue(runtime.prepared_frontend(self.root, env, self.manifest))
        self.assertFalse(runtime.prepared_frontend(self.root, {"REACT_APP_ENABLE_PREVIEW_LOGIN": "false"}, self.manifest))
        (self.root / "frontend/src/App.jsx").write_text("// changed source")
        self.assertFalse(runtime.prepared_frontend(self.root, env, self.manifest))

    def test_prepared_normal_launch_skips_pip_yarn_and_frontend_build(self):
        python = self.root / "runtime/windows-x64/python/python.exe"
        args = SimpleNamespace(repair=False, with_browser_tests=False, skip_mongodb=True,
                               configure_writer=False, start=False, no_browser=True, port=None, api_port=None)
        commands = []
        with patch.multiple(installer, ROOT=self.root, TOOLS=self.root / ".cache/tools", IS_WINDOWS=True), \
                patch.object(installer, "ensure_expanded", return_value=True), \
                patch.object(installer, "ensure_node", return_value=self.root / "node.exe"), \
                patch.object(installer, "ensure_virtualenv", return_value=python), \
                patch.object(installer, "prepared_python", return_value=python), \
                patch.object(installer, "python_dependencies_ready", return_value=True), \
                patch.object(installer, "prepared_frontend", return_value=True), \
                patch.object(installer, "verify_bundle", return_value=True), \
                patch.object(installer, "materialize_frontend_assets", return_value=True), \
                patch.object(installer, "build_ready", return_value=True), \
                patch.object(installer, "ensure_yarn", side_effect=AssertionError("Unnecessary Yarn call")), \
                patch.object(installer, "run", side_effect=lambda command, **_kwargs: commands.append(command)):
            installer.install_and_launch(args)
        self.assertEqual(len(commands), 1)
        self.assertTrue(str(commands[0][1]).endswith("scripts/init_env.py"))
        self.assert_data_intact()

    def test_shared_public_assets_copy_offline_without_overwriting_modified_build(self):
        source = self.root / "frontend/public/assets/logo.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"owned bundled image fixture")
        target_name = "frontend/build/assets/logo.png"
        self.manifest["frontend_asset_copies"] = {target_name: "frontend/public/assets/logo.png"}
        self.manifest["files"][target_name] = sha(source.read_bytes())
        self.assertTrue(runtime.materialize_frontend_assets(self.root, self.manifest))
        target = self.root / target_name
        self.assertEqual(target.read_bytes(), source.read_bytes())
        target.write_bytes(b"modified build asset")
        self.assertTrue(runtime.materialize_frontend_assets(self.root, self.manifest))
        self.assertEqual(target.read_bytes(), b"modified build asset")
        self.assert_data_intact()

    def test_failed_prepared_native_check_repairs_in_separate_venv(self):
        bundled = self.root / "runtime/windows-x64/python/python.exe"
        venv = self.root / ".venv/Scripts/python.exe"
        args = SimpleNamespace(repair=False, with_browser_tests=False, skip_mongodb=True,
                               configure_writer=False, start=False, no_browser=True, port=None, api_port=None)
        commands = []
        with patch.multiple(installer, ROOT=self.root, TOOLS=self.root / ".cache/tools", IS_WINDOWS=True), \
                patch.object(installer, "ensure_expanded", return_value=True), \
                patch.object(installer, "ensure_node", return_value=self.root / "node.exe"), \
                patch.object(installer, "ensure_virtualenv", side_effect=[bundled, venv]), \
                patch.object(installer, "require_space", return_value=None), \
                patch.object(installer, "prepared_python", return_value=bundled), \
                patch.object(installer, "python_dependencies_ready", side_effect=[False, True]), \
                patch.object(installer, "prepared_frontend", return_value=True), \
                patch.object(installer, "verify_bundle", return_value=True), \
                patch.object(installer, "materialize_frontend_assets", return_value=True), \
                patch.object(installer, "build_ready", return_value=True), \
                patch.object(installer, "ensure_yarn", side_effect=AssertionError("Unnecessary Yarn")), \
                patch.object(installer, "run", side_effect=lambda command, **_kwargs: commands.append(command)):
            installer.install_and_launch(args)
        pip = next(command for command in commands if "pip" in command)
        self.assertEqual(pip[0], venv)
        self.assertIn("--require-virtualenv", pip)
        self.assert_data_intact()

    def test_app_local_cpp_files_skip_machine_wide_installer(self):
        redist = self.root / "runtime/windows-x64/mongodb/vc_redist.x64.exe"
        redist.parent.mkdir(parents=True, exist_ok=True)
        for name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"):
            (redist.parent / name).write_bytes(b"fixture only")
        with patch.object(installer, "IS_WINDOWS", True), \
                patch.object(installer.subprocess, "run", side_effect=AssertionError("Unnecessary UAC/installer")):
            installer.ensure_windows_runtime(redist)
        self.assert_data_intact()

    def test_dependency_discovery_is_bounded_and_does_not_recurse(self):
        drive = self.root / "drive"
        known = drive / "Tools/nodejs/node.exe"
        known.parent.mkdir(parents=True)
        known.write_bytes(b"fixture")
        hidden = drive / "unrelated/private/huge/tree/node.exe"
        hidden.parent.mkdir(parents=True)
        hidden.write_bytes(b"must not be scanned")
        found = list(discovery.candidates("node", env={"PATH": ""}, drives=[drive]))
        self.assertEqual(found, [known])
        output = SimpleNamespace(returncode=0, stdout="v22.23.4\n", stderr="")
        with patch.object(discovery.subprocess, "run", return_value=output):
            self.assertEqual(discovery.discover("node", env={"PATH": ""}, drives=[drive]), known)
        output.stdout = "v16.0.0\n"
        with patch.object(discovery.subprocess, "run", return_value=output):
            self.assertIsNone(discovery.discover("node", env={"PATH": ""}, drives=[drive]))
        self.assertEqual(hidden.read_bytes(), b"must not be scanned")


if __name__ == "__main__":
    unittest.main(verbosity=2)
