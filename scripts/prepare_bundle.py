"""Unpack an already-installed Windows dependency tree from the local download.

This is OFFLINE extraction, not pip/npm installation. Only manifest-listed
runtime files are restored; application configuration, media and DB paths are
not valid payload destinations. A changed runtime file is backed up, not deleted.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import time

from prepared_runtime import file_sha256, load_manifest, safe_member, verify_bundle
from installer_storage import MIB, require_space

PAYLOAD_PREFIXES = (
    "runtime/windows-x64/python/Lib/site-packages/",
    "runtime/windows-x64/node/", "runtime/windows-x64/mongodb/",
    "runtime/windows-x64/yarn/",
)


def payload_members(manifest):
    members = manifest.get("payload", {}).get("members")
    if not isinstance(members, list) or not members or len(members) != len(set(members)):
        raise RuntimeError("Invalid installed-runtime payload manifest")
    for name in members:
        if not isinstance(name, str) or not name.startswith(PAYLOAD_PREFIXES) or name not in manifest["files"]:
            raise RuntimeError("Payload destination is not an approved runtime file")
        safe_member(Path.cwd(), name)  # Reject traversal, drive letters and Windows backslashes.
    return set(members)


def ensure_expanded(root, *, allow_online_fallback=False):
    root = Path(root)
    manifest = load_manifest(root)
    if not manifest or not manifest.get("payload"):
        return False  # Source-only download: the existing verified online installer handles it.
    members = payload_members(manifest)
    # Verification caching checks size/mtime, so unchanged launches read no archive.
    if (all(safe_member(root, name).is_file() for name in members)
            and all(verify_bundle(root, manifest, prefix=prefix) for prefix in PAYLOAD_PREFIXES)):
        return True
    specification = manifest["payload"]
    archive = safe_member(root, specification["path"])
    expected = specification.get("sha256", "")
    if not archive.is_file() or file_sha256(archive) != expected:
        if allow_online_fallback:
            print("The local prepared dependency archive is missing/corrupt and WILL NOT be used. Falling back to compatible installed tools and verified online dependency setup; existing data is preserved.", flush=True)
            return False
        raise RuntimeError("The local prepared-runtime archive is missing or corrupt. Extract the original complete download into a NEW folder; your existing data was not touched. Source-only downloads can use the online installer instead.")
    uncompressed = int(specification.get("uncompressed_bytes", 0))
    if uncompressed <= 0 or uncompressed > 1024 * MIB:
        raise RuntimeError("Invalid prepared-runtime size limit")
    require_space(root, uncompressed + 128 * MIB, "offline unpacking of preinstalled Windows dependencies")
    cache = root / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    print("Unpacking preinstalled Windows dependencies from the download (offline; no pip/npm or network)...", flush=True)
    restored = 0
    with tempfile.TemporaryDirectory(prefix="prepared-", dir=cache) as temporary:
        staging = Path(temporary)
        seen = set()
        total = 0
        # Bounded LZMA memory usage is set when building the release (64 MiB).
        with tarfile.open(archive, "r:xz") as source:
            for member in source:
                if not member.isfile() or member.name not in members or member.name in seen:
                    raise RuntimeError("Unexpected or unsafe prepared-runtime archive member")
                total += member.size
                if member.size < 0 or total > uncompressed:
                    raise RuntimeError("Prepared runtime exceeds the manifest size limit")
                destination = safe_member(staging, member.name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                stream = source.extractfile(member)
                if stream is None:
                    raise RuntimeError("Could not read the installed runtime")
                digest = hashlib.sha256()
                written = 0
                with stream, destination.open("xb") as output:
                    while block := stream.read(1024 * 1024):
                        written += len(block)
                        digest.update(block)
                        output.write(block)
                if written != member.size or digest.hexdigest() != manifest["files"][member.name]:
                    raise RuntimeError("Prepared-runtime file verification failed")
                seen.add(member.name)
        if seen != members or total != uncompressed:
            raise RuntimeError("Prepared-runtime archive is incomplete")
        backup = cache / f"preserved-runtime-{time.time_ns()}"
        for name in sorted(members):
            source = safe_member(staging, name)
            destination = safe_member(root, name)
            if destination.is_file() and file_sha256(destination) == manifest["files"][name]:
                continue
            if destination.exists():
                old = safe_member(backup, name)
                old.parent.mkdir(parents=True, exist_ok=True)
                destination.replace(old)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            restored += 1
    print(f"Ready: {restored} preinstalled dependency files unpacked/restored. Configuration and data were not changed.", flush=True)
    if not all(verify_bundle(root, manifest, prefix=prefix) for prefix in PAYLOAD_PREFIXES):
        raise RuntimeError("Unpacked Windows dependencies did not pass integrity checks")
    return True
