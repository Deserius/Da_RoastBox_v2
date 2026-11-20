"""Validate/use an explicitly packaged Windows runtime and prebuilt frontend.

No imports from third-party packages; no credential discovery or process stops.
A release bundle is an installed Windows file tree, NOT a copied Linux venv.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath

BUNDLE_SCHEMA = 1
PUBLIC_BUILD_KEYS = (
    "REACT_APP_BACKEND_URL", "REACT_APP_ENABLE_PREVIEW_LOGIN",
    "REACT_APP_SOURCE_DOWNLOAD_ENABLED", "REACT_APP_ENABLE_SESSION_TUNNEL",
    "REACT_APP_SUPPORT_EMAIL", "REACT_APP_FACEBOOK_URL", "REACT_APP_INSTAGRAM_URL",
    "REACT_APP_TIKTOK_URL", "REACT_APP_YOUTUBE_URL", "PUBLIC_URL",
)
PUBLIC_DEFAULTS = {
    "REACT_APP_BACKEND_URL": "", "REACT_APP_ENABLE_PREVIEW_LOGIN": "false",
    "REACT_APP_SOURCE_DOWNLOAD_ENABLED": "false", "REACT_APP_ENABLE_SESSION_TUNNEL": "false",
    "REACT_APP_SUPPORT_EMAIL": "", "REACT_APP_FACEBOOK_URL": "", "REACT_APP_INSTAGRAM_URL": "",
    "REACT_APP_TIKTOK_URL": "", "REACT_APP_YOUTUBE_URL": "", "PUBLIC_URL": "",
}


def file_sha256(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def safe_member(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts or "\\" in name or ":" in name:
        raise ValueError("Unsafe packaged runtime path")
    result = Path(root).joinpath(*relative.parts)
    if not result.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("Packaged path escapes project")
    return result


def load_manifest(root):
    path = Path(root) / "runtime" / "windows-x64" / "bundle.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        if data.get("schema") != BUNDLE_SCHEMA or data.get("platform") != "win_amd64":
            return None
        if not isinstance(data.get("files"), dict) or not data["files"]:
            return None
        return data
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def verify_bundle(root, manifest=None, prefix=None):
    """Hash once per unchanged file stat; revalidate changes, never execute repairs."""
    manifest = manifest or load_manifest(root)
    if not manifest:
        return False
    try:
        cache_path = Path(root) / ".cache" / "prepared-integrity.json"
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            cached = {}
        verified = dict(cached)
        matched = 0
        for name, expected in manifest["files"].items():
            if prefix is not None and not name.startswith(prefix):
                continue
            matched += 1
            if not isinstance(expected, str) or len(expected) != 64:
                return False
            path = safe_member(root, name)
            stat = path.stat()
            marker = [stat.st_size, stat.st_mtime_ns, expected]
            if cached.get(name) != marker and file_sha256(path) != expected:
                return False
            verified[name] = marker
        if not matched:
            return False
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(verified, sort_keys=True), encoding="utf-8")
        temporary.replace(cache_path)
        return True
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def requirements_hash(root):
    digest = hashlib.sha256()
    for name in ("backend/requirements.txt", "backend/requirements-runtime.txt"):
        digest.update(name.encode())
        digest.update((Path(root) / name).read_bytes())
    return digest.hexdigest()


def source_hash(root):
    root = Path(root)
    frontend = root / "frontend"
    paths = [p for part in ("src", "public") for p in (frontend / part).rglob("*") if p.is_file()]
    paths += [p for p in frontend.iterdir() if p.is_file() and p.suffix in (".js", ".cjs", ".json")]
    paths.append(frontend / "yarn.lock")
    digest = hashlib.sha256()
    for path in sorted(set(paths), key=lambda p: p.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def public_build_environment(root, env=None):
    """Only public build variables; never include server keys in manifests."""
    values = dict(PUBLIC_DEFAULTS)
    path = Path(root) / "frontend" / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = line.strip().partition("=")
            if separator and key in values:
                values[key] = value.strip().strip("\"'")
    for key, value in (os.environ if env is None else env).items():
        if key in values:
            values[key] = str(value)
    # These are deliberate per-build overrides, never on-disk .env edits.
    values["REACT_APP_BACKEND_URL"] = ""
    values["PUBLIC_URL"] = ""
    return values


def prepared_python(root, manifest=None):
    manifest = manifest or load_manifest(root)
    if not manifest or manifest.get("requirements_hash") != requirements_hash(root):
        return None
    path = safe_member(root, manifest.get("python", "runtime/windows-x64/python/python.exe"))
    return path if path.is_file() else None


def prepared_tool(root, kind, manifest=None):
    manifest = manifest or load_manifest(root)
    if not manifest or kind not in ("node", "mongod", "yarn"):
        return None
    value = manifest.get(kind)
    if not value:
        return None
    path = safe_member(root, value)
    expected = manifest["files"].get(path.relative_to(Path(root)).as_posix())
    return path if path.is_file() and expected and file_sha256(path) == expected else None


def prepared_frontend(root, env=None, manifest=None):
    manifest = manifest or load_manifest(root)
    if not manifest:
        return False
    try:
        return (manifest.get("frontend_source_hash") == source_hash(root)
                and manifest.get("public_build_environment") == public_build_environment(root, env)
                and (Path(root) / "frontend/build/index.html").is_file())
    except (OSError, ValueError, TypeError):
        return False


def materialize_frontend_assets(root, manifest=None):
    """The bundle stores unchanged public assets once, not twice in the ZIP.

    Copy only missing manifest-listed build assets. Never replace a modified
    build file or write source/configuration; the normal build check decides
    whether edited source requires a genuine frontend rebuild instead.
    """
    import os
    import shutil
    import tempfile
    root = Path(root)
    manifest = manifest or load_manifest(root)
    if not manifest:
        return False
    try:
        copies = manifest.get("frontend_asset_copies", {})
        for target_name, source_name in copies.items():
            if (not target_name.startswith("frontend/build/")
                    or not source_name.startswith("frontend/public/")
                    or target_name not in manifest["files"]):
                return False
            target = safe_member(root, target_name)
            source = safe_member(root, source_name)
            if target.is_file():
                continue
            if not source.is_file() or file_sha256(source) != manifest["files"][target_name]:
                return False
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix=".prepared-", dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
            try:
                shutil.copyfile(source, temporary)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return True
    except (OSError, ValueError, TypeError, AttributeError):
        return False
