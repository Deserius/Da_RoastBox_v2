#!/usr/bin/env python3
"""Install Da RoastBox locally, without changing system Node or MongoDB.

The prepared Windows download ships Python 3.13, installed application packages,
Node, MongoDB, Yarn, FFmpeg and a prebuilt frontend. Its first-run dependency
unpacking is offline. A source-only/changed/damaged setup uses supported Python
3.11–3.13 and official verified downloads. Existing .env/data are preserved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import time
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / ".cache" / "local-tools"
VENV = ROOT / ".venv"
sys.path.insert(0, str(ROOT / "scripts"))
from launcher_common import (NODE_VERSION, MONGO_VERSION, YARN_VERSION, IS_WINDOWS,
                             AlreadyRunning, ProjectLock, app_ready, occupied,
                             open_default_browser, port_number)
from prepared_runtime import (load_manifest as load_prepared_manifest, prepared_python, prepared_tool,
                              prepared_frontend, verify_bundle, materialize_frontend_assets)
from dependency_discovery import discover
from prepare_bundle import ensure_expanded
from installer_storage import (GIB, MIB, DiskSpaceError, installation_environment,
                               announce_storage, require_space, is_space_error,
                               space_message, run_pip_install)

YARN_SHA512 = "a6b2f7906b721bba3d67d4aff083df04dad64c399707841b7acf00f6b133b7ac24255f2652fa22ae3534329dc6180534e98d17432037ff6fd140556e2bb3137e"

NODE_HASHES = {
    "linux-x64.tar.gz": "b8492284c76a54baf58d61668dd0e41ee0fc98adabf9503d30f05d08f55b4406",
    "linux-arm64.tar.gz": "f7a1e486dbc8b286847815b477d4fb5e9fb963ed4489c3e1588853d685f589f9",
    "darwin-x64.tar.gz": "efcc2b0db6f94bf53eddb038fe2b370277a042bd29e4f19b8f8e23598795b819",
    "darwin-arm64.tar.gz": "c9e1dbc748b33ed2d14f42445191ecaf14c56259c7a9a26d0042c49ec2b66428",
    "win-x64.zip": "cbc74b5e0982c9dbb41525fd8fb5dcd32fbee237863f7829072f4639a1ce5f20",
}
MONGO_HASHES = {
    "linux-x86_64-debian12": "0e869e044162d101d4ee468e89bc139628c4c9e041bdcdaec19bf99331827215",
    "linux-x86_64-ubuntu2204": "8eef2a821651ac20f732b6636731a51b407675674ced8d7f1f1578ebc7aced43",
    "linux-x86_64-ubuntu2404": "3e55cdcf7013fbc805d29d8195230df4b23c7688733ee15ad58ac6bc2a416611",
    "linux-aarch64-ubuntu2204": "fe918ca853000d5b48fcd3b2bc6119c72f4aab9e2b04a9a10e42923cb3aef6a4",
    "linux-aarch64-ubuntu2404": "52655dd90adf0dbcbb87011075233285f44e262048ea30a9a48ad2a834c67736",
    "macos-arm64": "3255cbf2e70cc5de04220046e006067d20068656d1bfa674828768a51d20d5a6",
    "macos-x86_64": "3d391b8c41df069671afaa88ca21def057178aecce1813437539143b71f28152",
    "windows-x86_64": "6b021a0864494e4decf278b36477a29eb36072432773e4e62c2f42c302630db0",
}


def run(command, *, cwd=ROOT, env=None):
    print("\n> " + " ".join(str(item) for item in command), flush=True)
    command = [str(item) for item in command]
    child_env = installation_environment(ROOT, env)
    if "pip" in command and "install" in command:
        run_pip_install(command, cwd=cwd, env=child_env, root=ROOT)
    else:
        subprocess.run(command, cwd=cwd, env=child_env, check=True)


def download(url, destination, expected, algorithm="sha256"):
    """Download over HTTPS and verify against our pinned vendor checksum."""
    print(f"Downloading {url}", flush=True)
    digest = hashlib.new(algorithm)
    with urlopen(Request(url, headers={"User-Agent": "DaRoastBox-Installer/1.0"}), timeout=90) as response, destination.open("wb") as output:
        total = 0
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            # The official Windows MongoDB ZIP includes large debug symbols.
            if total > 1200 * 1024 * 1024:
                raise RuntimeError("Download exceeded the expected size limit")
            digest.update(block)
            output.write(block)
    if digest.hexdigest() != expected:
        destination.unlink(missing_ok=True)
        raise RuntimeError("Download checksum mismatch; installation stopped. Retry or check your network.")
    print("Verified download checksum.", flush=True)


def copy_tar_member(archive, suffix, destination):
    with tarfile.open(archive, "r:gz") as tar:
        matches = [m for m in tar.getmembers() if m.isfile() and m.name.endswith(suffix)]
        if len(matches) != 1:
            raise RuntimeError(f"Unexpected archive layout: {suffix}")
        source = tar.extractfile(matches[0])
        if source is None:
            raise RuntimeError("Could not read archive member")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source, destination.open("wb") as target:
            shutil.copyfileobj(source, target)
    destination.chmod(0o755)


def copy_zip_member(archive, suffix, destination):
    with zipfile.ZipFile(archive) as zip_file:
        matches = [name for name in zip_file.namelist() if name.endswith(suffix)]
        if len(matches) != 1:
            raise RuntimeError(f"Unexpected archive layout: {suffix}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zip_file.open(matches[0]) as source, destination.open("wb") as target:
            shutil.copyfileobj(source, target)


def system_arch():
    value = platform.machine().lower()
    if value in ("x86_64", "amd64", "x64"):
        return "x64"
    if value in ("arm64", "aarch64"):
        return "arm64"
    raise RuntimeError(f"Unsupported CPU architecture: {value}. See docs/LOCAL_INSTALL.md.")


def node_target():
    os_name = {"Windows": "win", "Darwin": "darwin", "Linux": "linux"}.get(platform.system())
    arch = system_arch()
    extension = "zip" if os_name == "win" else "tar.gz"
    key = f"{os_name}-{arch}.{extension}"
    if key not in NODE_HASHES:
        raise RuntimeError(f"No bundled Node download for {platform.system()} {arch}. See docs/LOCAL_INSTALL.md.")
    return key


def mongo_target():
    system, arch = platform.system(), system_arch()
    mongo_arch = "x86_64" if arch == "x64" else "aarch64"
    if system == "Windows" and arch == "x64":
        return "windows-x86_64", "windows", "zip"
    if system == "Darwin":
        return f"macos-{'x86_64' if arch == 'x64' else 'arm64'}", "osx", "tgz"
    if system == "Linux":
        values = {}
        os_release = Path("/etc/os-release")
        if os_release.exists():
            for line in os_release.read_text(errors="replace").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    values[key] = value.strip().strip('"')
        ids = (values.get("ID", "") + " " + values.get("ID_LIKE", "")).lower().split()
        major = values.get("VERSION_ID", "").split(".")[0]
        if "ubuntu" in ids:
            distro = "ubuntu2404" if major.isdigit() and int(major) >= 24 else "ubuntu2204"
        elif "debian" in ids and arch == "x64":
            distro = "debian12"
            if major != "12":
                print("Note: testing the Debian 12 MongoDB binary on this Debian-compatible system; official support may differ.", flush=True)
        else:
            raise RuntimeError("Automatic MongoDB download supports Ubuntu 22.04/24.04 and Debian x64. Use an existing MongoDB/Atlas and rerun with --skip-mongodb; see docs/LOCAL_INSTALL.md.")
        key = f"linux-{mongo_arch}-{distro}"
        if key in MONGO_HASHES:
            return key, "linux", "tgz"
    raise RuntimeError("No portable MongoDB for this OS/CPU. Configure an existing MongoDB/Atlas and rerun with --skip-mongodb; see docs/LOCAL_INSTALL.md.")


def ensure_node(tmp):
    if IS_WINDOWS:
        bundled = prepared_tool(ROOT, "node")
        if bundled:
            run([bundled, "--version"])
            return bundled
    exe = TOOLS / f"node-{NODE_VERSION}" / ("node.exe" if IS_WINDOWS else "node")
    if exe.is_file():
        try:
            run([exe, "--version"])
            return exe
        except (OSError, subprocess.CalledProcessError):
            print("Restoring a Node executable that failed its runtime check.", flush=True)
    if IS_WINDOWS and os.name == "nt":
        installed = discover("node", expected_node=NODE_VERSION)
        if installed:
            print("Using a compatible installed Node.js; no duplicate download.", flush=True)
            return installed
    require_space(ROOT, 256 * MIB, "portable Node.js installation")
    target = node_target()
    filename = f"node-v{NODE_VERSION}-{target}"
    archive = tmp / filename
    download(f"https://nodejs.org/dist/v{NODE_VERSION}/{filename}", archive, NODE_HASHES[target])
    if filename.endswith(".zip"):
        copy_zip_member(archive, "/node.exe", exe)
    else:
        copy_tar_member(archive, "/bin/node", exe)
    archive.unlink(missing_ok=True)  # Installer-owned vendor archive only.
    run([exe, "--version"])
    return exe


def ensure_yarn(tmp, node):
    if IS_WINDOWS:
        bundled = prepared_tool(ROOT, "yarn")
        if bundled:
            run([node, bundled, "--version"])
            return bundled
    yarn_dir = TOOLS / f"yarn-{YARN_VERSION}"
    yarn = yarn_dir / "bin" / "yarn.js"
    ready = False
    if yarn.is_file() and (yarn_dir / "lib" / "cli.js").is_file():
        try:
            run([node, yarn, "--version"])
            ready = True
        except (OSError, subprocess.CalledProcessError):
            print("Restoring Yarn files that failed their runtime check.", flush=True)
    if not ready:
        require_space(ROOT, 64 * MIB, "portable Yarn installation")
        archive = tmp / f"yarn-{YARN_VERSION}.tgz"
        download(f"https://registry.npmjs.org/yarn/-/yarn-{YARN_VERSION}.tgz", archive, YARN_SHA512, "sha512")
        # Extract only ordinary package files under the designated directory.
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() or not member.name.startswith("package/"):
                    continue
                relative = PurePosixPath(member.name).relative_to("package")
                if ".." in relative.parts or relative.is_absolute():
                    raise RuntimeError("Unsafe Yarn archive path")
                target = yarn_dir.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    raise RuntimeError("Could not read Yarn archive")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        archive.unlink(missing_ok=True)
    run([node, yarn, "--version"])
    return yarn


def ensure_windows_runtime(redist, *, force=False):
    """Use Microsoft's redistributable from the checksum-verified Mongo ZIP."""
    if not IS_WINDOWS:
        return
    system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    required = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")
    if not force and (all((system / name).is_file() for name in required)
                      or all((redist.parent / name).is_file() for name in required)):
        return  # Prepared bundles include signed Microsoft app-local runtime DLLs.
    if not redist.is_file():
        raise RuntimeError("Microsoft Visual C++ 2015-2022 x64 runtime is missing. Run start.bat --repair to restore MongoDB's bundled runtime, or install it from Microsoft.")
    print("Installing Microsoft's required Visual C++ x64 runtime. Approve the Windows permission prompt if shown.", flush=True)
    # Start-Process performs the UAC handoff and waits for a real exit status.
    # Escape a project path containing spaces or apostrophes; never use shell=True.
    path = str(redist).replace("'", "''")
    script = ("$ErrorActionPreference='Stop'; try { $p=Start-Process -FilePath '" + path +
              "' -ArgumentList '/install /quiet /norestart' -Verb RunAs -Wait -PassThru; exit $p.ExitCode } catch { Write-Error $_; exit 1 }")
    host = system / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not host.is_file():
        raise RuntimeError("The built-in Windows PowerShell host was not found. Ask your Windows administrator; no runtime or data was changed.")
    result = subprocess.run([str(host), "-NoProfile", "-NonInteractive", "-Command", script], check=False)
    code = result.returncode & 0xFFFFFFFF
    if code not in (0, 1638, 3010, 0x80070666):
        raise RuntimeError(f"Microsoft C++ runtime installation did not complete (exit {result.returncode}). Approve its permission request or install it manually, then rerun start.bat.")
    if code == 3010:
        print("Microsoft's runtime installer requested a Windows restart. If MongoDB cannot start, restart Windows and run start.bat again.", flush=True)


def ensure_mongo(tmp):
    if IS_WINDOWS:
        bundled = prepared_tool(ROOT, "mongod")
        if bundled:
            ensure_windows_runtime(bundled.parent / "vc_redist.x64.exe")
            run([bundled, "--version"])
            return bundled
        if os.name == "nt":
            installed = discover("mongod")
            if installed:
                print("Using an installed MongoDB 8.0 executable; no duplicate download.", flush=True)
                return installed
    base = TOOLS / f"mongodb-{MONGO_VERSION}"
    name = "mongod.exe" if IS_WINDOWS else "mongod"
    candidates = (base / name, base / "bin" / name)
    for exe in candidates:
        if exe.is_file():
            try:
                run([exe, "--version"])
                return exe
            except (OSError, subprocess.CalledProcessError):
                if IS_WINDOWS and (exe.parent / "vc_redist.x64.exe").is_file():
                    ensure_windows_runtime(exe.parent / "vc_redist.x64.exe", force=True)
                    run([exe, "--version"])
                    return exe
                print("Cached MongoDB did not pass its runtime check; restoring verified program files only (not data).", flush=True)
    exe = base / name
    target, section, extension = mongo_target()
    require_space(ROOT, (1536 if extension == "zip" else 512) * MIB, "portable MongoDB download/extraction")
    filename = f"mongodb-{target}-{MONGO_VERSION}.{extension}"
    archive = tmp / filename
    download(f"https://fastdl.mongodb.org/{section}/{filename}", archive, MONGO_HASHES[target])
    if extension == "zip":
        copy_zip_member(archive, "/bin/mongod.exe", exe)
        # The original installer discarded this required Windows dependency.
        copy_zip_member(archive, "/bin/vc_redist.x64.exe", base / "vc_redist.x64.exe")
        archive.unlink(missing_ok=True)
        ensure_windows_runtime(base / "vc_redist.x64.exe")
    else:
        copy_tar_member(archive, "/bin/mongod", exe)
        archive.unlink(missing_ok=True)
    try:
        run([exe, "--version"])
    except (OSError, subprocess.CalledProcessError) as exc:
        if IS_WINDOWS:
            ensure_windows_runtime(base / "vc_redist.x64.exe", force=True)
            try:
                run([exe, "--version"])
                return exe
            except (OSError, subprocess.CalledProcessError):
                pass
        raise RuntimeError("MongoDB could not run. Check the Microsoft C++ runtime, 64-bit/AVX CPU support and OS libraries; use an existing database with --skip-mongodb if needed. No database files were removed.") from exc
    return exe


def fingerprint(paths, extra=""):
    digest = hashlib.sha256(extra.encode())
    for path in sorted(paths, key=lambda p: str(p)):
        if path.is_file():
            digest.update(str(path.relative_to(ROOT)).replace("\\", "/").encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def cache_matches(name, value):
    try:
        return json.loads((ROOT / ".cache" / name).read_text()).get("fingerprint") == value
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def save_cache(name, value):
    destination = ROOT / ".cache" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps({"fingerprint": value, "schema": 1}) + "\n")
    temporary.replace(destination)


PYTHON_CHECK = r'''import importlib, importlib.metadata as md, json, pathlib, sys
from packaging.requirements import Requirement
def check_requirements(path):
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        raw = raw.split(" #", 1)[0].strip()
        if not raw or raw.startswith("#"): continue
        if raw.startswith("-r "):
            check_requirements(path.parent / raw[3:].strip())
            continue
        req = Requirement(raw)
        if req.marker and not req.marker.evaluate(): continue
        dist = md.distribution(req.name)
        if req.specifier and dist.version not in req.specifier: raise RuntimeError("version mismatch")
        if req.url and "#sha256=" in req.url:
            direct = json.loads(dist.read_text("direct_url.json") or "{}")
            info = direct.get("archive_info", {})
            actual = info.get("hashes", {}).get("sha256") or str(info.get("hash", "")).removeprefix("sha256=")
            if actual != req.url.split("#sha256=", 1)[1]: raise RuntimeError("direct wheel mismatch")
check_requirements(pathlib.Path(sys.argv[1]))
for name in ("fastapi", "uvicorn", "pymongo", "motor", "PIL.Image", "openai", "elevenlabs", "dotenv", "imageio_ffmpeg", "stripe", "cryptography.fernet", "vercel.blob", "httpx2", "numpy", "mutagen"):
    importlib.import_module(name)
import imageio_ffmpeg
imageio_ffmpeg.get_ffmpeg_version()
'''


def python_dependencies_ready(python):
    try:
        return subprocess.run([str(python), "-c", PYTHON_CHECK, str(ROOT / "backend/requirements.txt")],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              env=installation_environment(ROOT), timeout=90).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def frontend_dependencies_ready(node, env):
    frontend = ROOT / "frontend"
    if not (frontend / "node_modules/.yarn-integrity").is_file():
        return False
    script = "for(const p of ['react','react-dom','axios','@craco/craco','http-proxy-middleware']) require.resolve(p);"
    try:
        return subprocess.run([str(node), "-e", script], cwd=frontend, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def build_ready():
    build = ROOT / "frontend/build"
    try:
        manifest = json.loads((build / "asset-manifest.json").read_text())
        return (build / "index.html").is_file() and bool(manifest.get("files")) and all(
            (build / value.lstrip("/")).is_file() for value in manifest["files"].values() if isinstance(value, str) and not value.startswith(("http:", "https:")))
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def configured_mongo_uri():
    if os.environ.get("MONGO_URL"):
        return os.environ["MONGO_URL"]
    path = ROOT / "backend/.env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            match = re.match(r"^\s*(?:export\s+)?MONGO_URL\s*=\s*(.*)$", line)
            if match:
                return match[1].strip().strip("\"'")
    return "mongodb://127.0.0.1:27017"


def need_portable_database():
    from urllib.parse import urlsplit
    try:
        parsed = urlsplit(configured_mongo_uri())
        plain_local = (parsed.scheme == "mongodb" and parsed.hostname in ("127.0.0.1", "localhost")
                       and not parsed.username and not parsed.password and not parsed.query
                       and not parsed.fragment and parsed.path in ("", "/") and "," not in parsed.netloc)
        return plain_local and not occupied(parsed.port or 27017)
    except ValueError:
        return False


def ensure_virtualenv(*, prefer_prepared=True):
    if IS_WINDOWS and prefer_prepared:
        bundled = prepared_python(ROOT)
        if bundled and verify_bundle(ROOT, prefix="runtime/windows-x64/python/"):
            print("Using the preinstalled Windows Python packages and FFmpeg; no pip installation needed.", flush=True)
            return bundled
    python = VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
    if python.is_file():
        try:
            result = subprocess.run([str(python), "-c", "import sys; assert (3,11) <= sys.version_info[:2] <= (3,13) and (sys.platform != 'win32' or sys.maxsize > 2**32)"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            if result.returncode == 0:
                return python
        except (OSError, subprocess.TimeoutExpired):
            pass
        # A copied/moved venv is disposable, but preserve it rather than delete.
        backup = ROOT / ".cache" / f"old-venv-{time.time_ns()}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        VENV.replace(backup)
        print("Preserved an unusable virtual environment in .cache; creating a working one. Database and settings were not touched.", flush=True)
    require_space(ROOT, 128 * MIB, "Python virtual environment creation")
    print("Creating project-local Python virtual environment...", flush=True)
    # A child process lets ensurepip inherit project-local TEMP/TMP too.
    run([sys.executable, "-m", "venv", VENV])
    return python


def install_and_launch(args):
    print("Da RoastBox one-click setup. Existing .env files, database and generated media are preserved.", flush=True)
    print("Only missing/changed dependencies and builds are installed. No AI or payment calls are made.", flush=True)
    announce_storage(ROOT)
    if IS_WINDOWS:
        ensure_expanded(ROOT, allow_online_fallback=True)
    env = installation_environment(ROOT)
    TOOLS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="install-", dir=TOOLS) as temporary:
        tmp = Path(temporary)
        node = ensure_node(tmp)
        python = ensure_virtualenv(prefer_prepared=not (args.repair or args.with_browser_tests))
        yarn = None
        py_hash = fingerprint([ROOT / "backend/requirements.txt", ROOT / "backend/requirements-runtime.txt"], extra=f"python-v3:{sys.version}:{platform.machine()}:{python}")
        preinstalled = IS_WINDOWS and python == prepared_python(ROOT)
        prepared_ready = preinstalled and python_dependencies_ready(python)
        if preinstalled and not prepared_ready:
            print("The prepared Python runtime failed its native check; using a separate repair venv. The packaged runtime and data are preserved.", flush=True)
            python = ensure_virtualenv(prefer_prepared=False)
            preinstalled = False
            py_hash = fingerprint([ROOT / "backend/requirements.txt", ROOT / "backend/requirements-runtime.txt"], extra=f"python-v3:{sys.version}:{platform.machine()}:{python}")
        if not args.repair and (cache_matches("python-dependencies.json", py_hash) or preinstalled) and (prepared_ready or python_dependencies_ready(python)):
            print("Python dependencies and bundled FFmpeg are already ready.", flush=True)
            save_cache("python-dependencies.json", py_hash)
        else:
            require_space(ROOT, 2 * GIB, "Python package installation")
            command = [python, "-m", "pip", "install", "--require-virtualenv", "--disable-pip-version-check", "--no-cache-dir"]
            if args.repair:
                command.append("--force-reinstall")
            run([*command, "-r", ROOT / "backend/requirements.txt"])
            if not python_dependencies_ready(python):
                raise RuntimeError("Python dependency checks failed. Review setup errors, or retry start.bat --repair. No server was started.")
            save_cache("python-dependencies.json", py_hash)
        if args.with_browser_tests:
            require_space(ROOT, GIB, "optional browser-test packages and Chromium")
            run([python, "-m", "pip", "install", "--require-virtualenv", "--disable-pip-version-check", "--no-cache-dir", "-r", ROOT / "requirements-test.txt"])
            run([python, "-m", "playwright", "install", "chromium"])
        run([python, ROOT / "scripts/init_env.py", "--preview"])
        if getattr(args, "configure_writer", False):
            run([python, ROOT / "backend/scripts/configure_writer.py", "--apply"])
        if not args.skip_mongodb and need_portable_database():
            mongo = ensure_mongo(tmp)
            env["ROASTBOX_MONGOD_EXE"] = str(mongo)
        else:
            print("Using the configured/existing database; no unnecessary MongoDB download. Launcher will verify it before starting.", flush=True)
        # Missing frontend source packages are irrelevant when the shipped build
        # matches source + public configuration. No node_modules/Yarn install.
        use_prebuilt = (not args.repair and prepared_frontend(ROOT, env)
                        and materialize_frontend_assets(ROOT)
                        and verify_bundle(ROOT, prefix="frontend/build/") and build_ready())
        if not use_prebuilt:
            yarn = ensure_yarn(tmp, node)
    env["ROASTBOX_NODE_EXE"] = str(node)
    env["PATH"] = str(node.parent) + os.pathsep + str(python.parent) + os.pathsep + env.get("PATH", "")
    # This is a local, same-origin build. Preserve frontend/.env on disk but
    # never bake an old remote/localhost:8000 backend URL into the local browser.
    env["REACT_APP_BACKEND_URL"] = ""
    env["PUBLIC_URL"] = ""
    env["CI"] = "true"
    env.setdefault("NODE_OPTIONS", "--max-old-space-size=1024")
    if use_prebuilt:
        print("Using the prebuilt matching frontend. No frontend install/build needed.", flush=True)
    else:
        front_hash = fingerprint([ROOT / "frontend/package.json", ROOT / "frontend/yarn.lock"],
                                 extra=f"frontend-v2:{NODE_VERSION}:{platform.system()}:{platform.machine()}")
        if not args.repair and cache_matches("frontend-dependencies.json", front_hash) and frontend_dependencies_ready(node, env):
            print("Frontend dependencies are already ready.", flush=True)
        else:
            require_space(ROOT, 1536 * MIB, "frontend dependency installation")
            command = [node, yarn, "install", "--frozen-lockfile", "--ignore-engines", "--non-interactive", "--check-files", "--cache-folder", env["YARN_CACHE_FOLDER"]]
            if args.repair:
                command.append("--force")
            run(command, cwd=ROOT / "frontend", env=env)
            if not frontend_dependencies_ready(node, env):
                raise RuntimeError("Frontend dependency check failed. Retry start.bat --repair or review the errors above.")
            save_cache("frontend-dependencies.json", front_hash)
        files = [p for part in ("src", "public") for p in (ROOT / "frontend" / part).rglob("*") if p.is_file()]
        files += [p for p in (ROOT / "frontend").iterdir() if p.is_file() and (p.suffix in (".js", ".cjs", ".json") or p.name.startswith(".env"))]
        extra = front_hash + json.dumps({k: v for k, v in sorted(env.items()) if k.startswith("REACT_APP_")}, sort_keys=True)
        build_hash = fingerprint(files, extra=extra)
        if not args.repair and cache_matches("frontend-build.json", build_hash) and build_ready():
            print("Frontend build is current; no rebuild needed.", flush=True)
        else:
            require_space(ROOT, 512 * MIB, "frontend production build")
            print("Building the local frontend. First setup/source changes can take a few minutes...", flush=True)
            run([node, yarn, "build"], cwd=ROOT / "frontend", env=env)
            if not build_ready():
                raise RuntimeError("Frontend build is incomplete. The browser was not opened.")
            save_cache("frontend-build.json", build_hash)
    print("\nDependencies and frontend are ready.", flush=True)
    if args.start:
        command = [python, ROOT / "scripts/local_start.py"]
        if args.no_browser:
            command.append("--no-browser")
        if args.skip_mongodb:
            command.append("--external-db")
        if args.port is not None:
            command.extend(["--port", str(args.port)])
        if args.api_port is not None:
            command.extend(["--api-port", str(args.api_port)])
        run(command, env=env)
    else:
        print("Setup complete. Double-click start.bat to start the app and open your default browser.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install dependencies, build Da RoastBox and optionally launch it")
    parser.add_argument("--skip-mongodb", action="store_true", help="Use your existing local/remote database; do not download or start a portable database")
    parser.add_argument("--with-browser-tests", action="store_true", help="Install optional Playwright/Chromium tests")
    parser.add_argument("--start", action="store_true", help="Start servers and open the default browser after setup")
    parser.add_argument("--no-browser", action="store_true", help="Suppress browser launch for headless/automated use")
    parser.add_argument("--configure-writer", action="store_true", help="Explicitly apply the requested paid Claude/GPT OpenRouter chain, preserving keys/data")
    parser.add_argument("--repair", action="store_true", help="Reinstall Python/frontend packages and force a fresh build")
    parser.add_argument("--port", type=int, help="Frontend port (default PORT or 3000)")
    parser.add_argument("--api-port", type=int, help="Backend port (default API_PORT or 8001)")
    args = parser.parse_args(argv)
    for name in ("backend/requirements.txt", "frontend/package.json", "frontend/yarn.lock", "scripts/local_start.py", "scripts/serve-preview.cjs", "scripts/installer_storage.py", "backend/.env.example", "frontend/.env.example"):
        if not (ROOT / name).is_file():
            raise RuntimeError("Project files are missing. Extract the complete ZIP to a writable folder before running start.bat.")
    if not ((3, 11) <= sys.version_info[:2] <= (3, 13)):
        raise RuntimeError("Python 3.11, 3.12 or 3.13 is required. start.bat can install Python 3.13 on Windows.")
    if IS_WINDOWS and sys.maxsize <= 2**32:
        raise RuntimeError("64-bit Python is required on Windows. Double-click LAUNCH_DA_ROASTBOX.bat to discover/install a supported x64 interpreter.")
    ui = port_number(args.port if args.port is not None else os.environ.get("PORT", "3000"), "Frontend port")
    api = port_number(args.api_port if args.api_port is not None else os.environ.get("API_PORT", "8001"), "API port")
    if ui == api:
        raise RuntimeError("Frontend and API ports must differ (defaults: 3000 and 8001).")
    if app_ready(ui, api):
        if args.repair or args.configure_writer or not args.start:
            raise RuntimeError("Da RoastBox is already running. Stop its web-server window before changing dependencies; leave MongoDB running.")
        print(f"Da RoastBox is already running at http://127.0.0.1:{ui}. No duplicate installation/server was started.", flush=True)
        if not args.no_browser:
            open_default_browser(f"http://127.0.0.1:{ui}")
        return
    if args.start:
        for label, number in (("Frontend", ui), ("API", api)):
            if occupied(number):
                raise RuntimeError(f"{label} port {number} is already occupied. No existing process was stopped. Close the conflicting web server or choose another port.")
    with ProjectLock(ROOT / ".cache" / "install.lock"):
        install_and_launch(args)


if __name__ == "__main__":
    try:
        main()
    except AlreadyRunning as exc:
        print(str(exc), flush=True)
    except KeyboardInterrupt:
        print("\nSetup/local web servers stopped. MongoDB and data were not terminated or deleted.", flush=True)
    except (RuntimeError, OSError, subprocess.CalledProcessError, ValueError) as exc:
        if is_space_error(exc) and not isinstance(exc, DiskSpaceError):
            exc = DiskSpaceError(space_message(ROOT, "local setup"))
        print(f"\nSetup failed: {exc}\nSee docs/LOCAL_INSTALL.md for troubleshooting. No existing configuration or data was deleted.", file=sys.stderr)
        raise SystemExit(1)
