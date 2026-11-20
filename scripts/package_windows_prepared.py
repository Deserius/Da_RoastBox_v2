#!/usr/bin/env python3
"""Package a sanitized app + genuinely installed Windows dependency file tree.

Owner/build helper, NOT run on normal launch. Supply the cross-installed,
checksum-verified Windows runtime and an isolated matching React production
build. Does not run Windows programs, read filled env files, copy a Linux venv,
modify the served frontend build, or access any database/provider.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata as metadata
import json
import lzma
from pathlib import Path
import shutil
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from package_source import collect, scan
from prepare_bundle import PAYLOAD_PREFIXES
from prepared_runtime import (file_sha256, requirements_hash, source_hash)


def validate_installed_windows(root):
    """Check Windows markers + extras/transitive closure, not the Linux host markers."""
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.utils import canonicalize_name
    from packaging.version import Version
    libraries = root / "runtime/windows-x64/python/Lib/site-packages"
    distributions = {canonicalize_name(d.metadata["Name"]): d for d in metadata.distributions(path=[str(libraries)])}
    environment = default_environment()
    environment.update(sys_platform="win32", os_name="nt", platform_system="Windows", platform_machine="AMD64",
                       python_version="3.13", python_full_version="3.13.16", implementation_name="cpython",
                       implementation_version="3.13.16", platform_python_implementation="CPython", extra="")
    extras = {name: set() for name in distributions}
    application = {}
    for line in (ROOT / "backend/requirements-runtime.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        name = canonicalize_name(requirement.name)
        if name not in distributions or distributions[name].version not in requirement.specifier:
            raise RuntimeError(f"Installed Windows requirement is missing/mismatched: {name}")
        extras[name].update(requirement.extras)
        application[name] = distributions[name].version
    changed = True
    while changed:
        changed = False
        for name, distribution in distributions.items():
            python_requirement = distribution.metadata.get("Requires-Python")
            if python_requirement and Version("3.13.16") not in SpecifierSet(python_requirement):
                raise RuntimeError(f"Incompatible Windows Python version: {name}")
            for raw in distribution.requires or []:
                requirement = Requirement(raw)
                contexts = [dict(environment, extra=extra) for extra in [""] + sorted(extras[name])]
                if requirement.marker and not any(requirement.marker.evaluate(context) for context in contexts):
                    continue
                target = canonicalize_name(requirement.name)
                if target not in distributions or distributions[target].version not in requirement.specifier:
                    raise RuntimeError(f"Incomplete Windows dependency closure: {name} -> {target}")
                previous = len(extras[target])
                extras[target].update(requirement.extras)
                changed |= previous != len(extras[target])
    for path in (root / "runtime/windows-x64").rglob("*"):
        if path.is_file():
            with path.open("rb") as source:
                header = source.read(4)
            if path.suffix.lower() == ".so" or header == b"\x7fELF":
                raise RuntimeError("A Linux binary must never be shipped in the Windows runtime")
    return dict(sorted(application.items()))


def build_payload(installed, output, members):
    hashes = {name: file_sha256(installed / name) for name in members}
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    cache = output.with_suffix(".fingerprint.json")
    if output.is_file() and cache.is_file():
        previous = json.loads(cache.read_text())
        if previous.get("fingerprint") == fingerprint and previous.get("sha256") == file_sha256(output):
            return previous
    temporary = output.with_suffix(".partial")
    print("Compressing the already-installed Windows tree for offline first-run unpacking...", flush=True)
    try:
        # x86 BCJ improves actual Windows executables. 32 MiB dictionary keeps
        # first-run decoding memory below 64 MiB. No Windows 7-Zip install needed.
        filters = [{"id": lzma.FILTER_X86}, {"id": lzma.FILTER_LZMA2, "preset": 7, "dict_size": 32 * 1024 * 1024}]
        with lzma.open(temporary, "wb", filters=filters) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|") as archive:
                for name in members:
                    source = installed / name
                    entry = tarfile.TarInfo(name)
                    entry.size = source.stat().st_size
                    entry.mode = 0o644
                    entry.mtime = 0
                    with source.open("rb") as stream:
                        archive.addfile(entry, stream)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    result = {"fingerprint": fingerprint, "sha256": file_sha256(output), "bytes": output.stat().st_size,
              "uncompressed_bytes": sum((installed / name).stat().st_size for name in members)}
    cache.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination")
    parser.add_argument("--installed-runtime", required=True, type=Path,
                        help="Root containing runtime/windows-x64/python, node, mongodb and yarn")
    parser.add_argument("--frontend-build", required=True, type=Path,
                        help="Production build from the CURRENT source, with local preview enabled")
    args = parser.parse_args()
    installed = args.installed_runtime.resolve()
    frontend = args.frontend_build.resolve()
    destination = Path(args.destination).expanduser().resolve()
    if destination.is_relative_to(ROOT):
        parser.error("Write the deliverable outside the source folder")
    if frontend == (ROOT / "frontend/build").resolve():
        parser.error("Use a separately built frontend; do not package or overwrite the live served build")
    required = ("python/python.exe", "python/python313.dll", "python/python3.dll", "python/vcruntime140.dll",
                "python/vcruntime140_1.dll", "node/node.exe", "mongodb/mongod.exe", "yarn/bin/yarn.js")
    for name in required:
        if not (installed / "runtime/windows-x64" / name).is_file():
            raise RuntimeError(f"Prepared Windows file is missing: {name}")
    if not (frontend / "index.html").is_file() or not (frontend / "asset-manifest.json").is_file():
        raise RuntimeError("Isolated frontend production build is incomplete")
    packages = validate_installed_windows(installed)
    runtime_files = sorted(p for p in (installed / "runtime/windows-x64").rglob("*") if p.is_file())
    if any(p.is_symlink() for p in runtime_files):
        raise RuntimeError("Prepared runtime must contain real files, not external symlinks")
    names = [p.relative_to(installed).as_posix() for p in runtime_files]
    members = [name for name in names if name.startswith(PAYLOAD_PREFIXES)]
    base = [name for name in names if name not in members]
    scratch = ROOT / ".cache/windows-prepared/package-metadata"
    scratch.mkdir(parents=True, exist_ok=True)
    payload_path = scratch / "installed-runtime.tar.xz"
    payload = build_payload(installed, payload_path, members)
    payload.update(path="runtime/windows-x64/installed-runtime.tar.xz", members=members)
    build_files = sorted(p for p in frontend.rglob("*") if p.is_file())
    sources = collect()
    findings = scan(sources + build_files)
    if findings:
        raise RuntimeError("Potential secret found; review the source/build before packaging")
    hashes = {name: file_sha256(installed / name) for name in names}
    hashes.update({"frontend/build/" + p.relative_to(frontend).as_posix(): file_sha256(p) for p in build_files})
    copies = {}
    for source in build_files:
        relative = source.relative_to(frontend).as_posix()
        original = ROOT / "frontend/public" / relative
        target = "frontend/build/" + relative
        if original.is_file() and not original.is_symlink() and file_sha256(original) == hashes[target]:
            copies[target] = "frontend/public/" + relative
    # Read examples/defaults, NEVER the owner's filled frontend/.env.
    from prepared_runtime import PUBLIC_DEFAULTS
    public_environment = dict(PUBLIC_DEFAULTS)
    public_environment["REACT_APP_ENABLE_PREVIEW_LOGIN"] = "true"
    manifest = {"schema": 1, "platform": "win_amd64", "installer_version": "1.2.3", "python_version": "3.13.16",
                "node_version": "22.23.4", "mongodb_version": "8.0.34", "yarn_version": "1.22.22",
                "python": "runtime/windows-x64/python/python.exe", "node": "runtime/windows-x64/node/node.exe",
                "mongod": "runtime/windows-x64/mongodb/mongod.exe", "yarn": "runtime/windows-x64/yarn/bin/yarn.js",
                "requirements_hash": requirements_hash(ROOT), "frontend_source_hash": source_hash(ROOT),
                "public_build_environment": public_environment, "application_packages": packages,
                "files": hashes, "payload": payload, "frontend_asset_copies": copies, "windows_execution_verified": False}
    manifest_file = scratch / "bundle.json"
    manifest_file.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for source in sources:
                archive.write(source, source.relative_to(ROOT).as_posix())
            for source in build_files:
                target = "frontend/build/" + source.relative_to(frontend).as_posix()
                if target not in copies:
                    archive.write(source, target)
            for name in base:
                archive.write(installed / name, name)
            archive.write(manifest_file, "runtime/windows-x64/bundle.json")
            archive.write(payload_path, payload["path"], compress_type=zipfile.ZIP_STORED)
        with zipfile.ZipFile(temporary) as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise RuntimeError(f"Prepared ZIP CRC failure: {corrupt}")
            count = len(archive.infolist())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    checksum = file_sha256(destination)
    destination.with_name(destination.name + ".sha256.txt").write_text(f"{checksum}  {destination.name}\n")
    print(json.dumps({"archive": str(destination), "files": count, "bytes": destination.stat().st_size, "sha256": checksum,
                      "preinstalled_application_packages": len(packages), "installed_runtime_files": len(runtime_files),
                      "offline_payload_bytes": payload["bytes"], "frontend_files": len(build_files),
                      "public_assets_stored_once": len(copies),
                      "native_windows_execution": "NOT TESTED in this Linux workspace"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
