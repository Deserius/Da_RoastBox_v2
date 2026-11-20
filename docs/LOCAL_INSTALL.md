# Local installation and one-click startup

## Windows: extract, double-click, use your default browser

1. Right-click **`Da_RoastBox_Windows_Preinstalled.zip` → Extract All**. Extract the
   complete package to a writable, preferably short path such as
   `E:\RoastBox\da_roastbox`. Do not run it inside the ZIP viewer.
2. Double-click **`thelaunch.bat`**. **`start.bat`** and
   **`LAUNCH_DA_ROASTBOX.bat`** remain equivalent aliases. No terminal, winget,
   separate Python/Node installation or browser selection is normally needed.
3. Keep the launcher window open. Once the API and site pass readiness checks,
   your **registered default browser** opens **http://127.0.0.1:3000**.
4. The Hustler Anomalies Enterprises intro tries sound automatically. If blocked,
   **press Enter/Space with the page focused, or tap/click the intro**. Scene and
   audio restart together. The sound button also works; Escape/Skip moves on.

Full local MongoDB setup targets **Windows 11 x64 / Windows Server 2022 with an
AVX-capable CPU** and built-in Windows PowerShell 5.1. ARM64, 32-bit Windows, older
OS/CPUs and restricted/managed machines are not promised compatibility. A supported
external MongoDB can avoid the local database requirement (`--skip-mongodb`).
Do not disable antivirus or weaken organizational policy to run an untrusted file.

## What is preinstalled in this download

The **prepared** download contains actual Windows x64 files, **not a Linux venv**:

| Component | Included version / handling |
| --- | --- |
| Python | Official PSF NuGet runtime **3.13.16**, project-local; no global installation |
| Python application dependencies | **50** pinned packages, installed into Windows Python's `Lib/site-packages`, with Windows-aware dependency/ABI checks |
| FFmpeg | Windows binary supplied by `imageio-ffmpeg==0.8.0` (**FFmpeg 9.0.2**) |
| Node.js | **22.23.4**, Windows x64 executable and license |
| MongoDB | **8.0.34**, Windows x64 server + licenses; huge debug symbols omitted |
| Microsoft C++ runtime | App-local Microsoft runtime DLLs with MongoDB; no normal machine-wide prerequisite setup |
| Yarn | **1.22.22**, available if an edited source genuinely needs rebuilding |
| Website | Compiled React production build; no normal frontend package installation or build |

The installed dependency file tree is shipped as a **local compressed payload**.
First launch verifies and unpacks it **offline**, without running pip/npm/Yarn
installation or fetching those components. This is extraction of preinstalled files,
not a claim that Windows binaries were run on this Linux build machine. Unchanged
public assets are stored once in the ZIP and copied into the compiled site locally.
Later starts verify/reuse the resulting files and skip decompression, pip and builds.
The integrity manifest is `runtime/windows-x64/bundle.json`.

Allow **at least 2 GiB free after ZIP extraction** for offline dependency unpacking
and initial local runtime/database work; **4 GiB or more** is recommended for
repairs, frontend rebuilds and data growth. Windows needs system-drive headroom too.
See [bundle details](WINDOWS_BUNDLE.md) and [storage guidance](../INSTALLER_SPACE_FIX.txt).

A source-only download does **not** contain the prepared runtime/build and uses the
online installation path below. Missing/damaged dependency files in the prepared
bundle are restored from its local payload first. If the payload is missing/corrupt,
it is not executed: the launcher falls back to compatible installed tools and verified
online setup. A malformed manifest or failed publisher-trust check fails closed.

## Launch sequence and Python entry points

```text
thelaunch.bat / LAUNCH_DA_ROASTBOX.bat
  -> start.bat -> install.bat -> scripts/bootstrap_python.ps1
  -> start.py -> install.py (shared setup/readiness logic)
  -> bundled Windows Python OR project .venv + scripts/local_start.py
  -> API 127.0.0.1:8001 + same-origin frontend :3000
  -> registered default browser, after readiness
```

`python start.py` and `python Launcher.py` use the same setup/start path when a
supported interpreter is already able to run Python files. **A `.py` file cannot
start itself on a computer with no Python/file association**: use the BAT entry
point, which can use the shipped interpreter or bootstrap one.

### Discovery and online fallback

- Uses the built-in **Windows PowerShell 5.1** host with `-NoProfile`; the x64 host is
  selected even from a 32-bit file manager. Execution-policy bypass is process-local;
  no machine/user policy is changed and higher-priority enterprise policy still wins.
- Prefers the shipped PSF interpreter. Its executable/core DLL hashes are checked
  before execution, together with Windows Authenticode publisher trust for Python.
- If that interpreter is absent/corrupt, searches working **x64 Python 3.11–3.13** in
  the project venv/cache, `ROASTBOX_PYTHON_EXE`, Python registry, launcher list, PATH
  and known folders on fixed drives. The Store placeholder is not executed.
- If needed, downloads the pinned official **Python 3.13.16** full installer from
  python.org. SHA256 from `deploy/windows-bootstrap.json` **and** a valid Python
  Software Foundation Authenticode signature must pass before per-user setup.
  No global PATH/launcher/file-association changes or automatic elevation for Python.
- Missing-Python setup is serialized by an OS-released mutex. Interrupted/checksum
  failures retry at most three times; signature failures do not bypass trust.
  Cancellation, another MSI, installer failure or a restart requirement stops with
  a visible explanation. `/norestart` prevents forced reboot.
- Node/MongoDB discovery is bounded: explicit `ROASTBOX_NODE_EXE` /
  `ROASTBOX_MONGOD_EXE`, PATH, known registry/install locations and a small list of
  known fixed-drive folders. **It does not recursively search whole drives or inspect
  unrelated credentials/documents.** Only compatible executable versions are reused.
- Missing tools download from their official vendors with pinned checksums.
  Project-local installs do not replace global Node/MongoDB. For an online MongoDB
  repair, the large vendor ZIP is downloaded but debug symbols are not retained.
- If a prepared Python native import/FFmpeg check fails, repair uses a **separate
  `.venv`**, not a pip installation into the sealed bundled runtime. A broken/moved
  venv is preserved in `.cache/old-venv-*`. `--repair` deliberately reinstalls packages
  and rebuilds, so internet and extra headroom may be needed.
- The source-only MongoDB path can request approval for Microsoft's genuine C++
  redistributable if no working app-local/system runtime exists. The launcher cannot
  bypass a declined UAC prompt, restart requirement or organizational security policy.

Official compatibility pins: [Python 3.13.16](https://www.python.org/downloads/release/python-31316/),
[PSF NuGet runtime documentation](https://docs.python.org/3.13/using/windows.html#the-nuget-org-packages).
These are fixed versions, **not a claim to select the newest release**.

## Configuration, database and readiness safeguards

- `backend/.env` and `frontend/.env` are created **only if missing**. Existing keys,
  model choices, users, balances, entitlements, history, purchases and media are not
  reset/recharged/regenerated. No migration or cloud mutation runs.
- A fresh local configuration explicitly uses preview login, an isolated preview
  database, local media and a randomly generated persistent secret. This is not
  fake paid-provider output or a complete production service configuration.
- Reuses a reachable configured MongoDB. A private server is started only for a
  **plain unauthenticated loopback URI**, against preserved `.data/mongo` (or the
  existing per-port data folder). Remote, authenticated, SRV or multi-host URIs are
  never silently replaced with a local database. **27017 is MongoDB, not a web page.**
- Prebuilt frontend reuse requires matching source and public configuration plus
  intact outputs. Source/config changes trigger the necessary lockfile install/build.
  Same-origin backend/public-prefix overrides are process-local, never `.env` rewrites.
- Starts **one API worker on loopback 8001** and the website on **3000**. The Node
  server proxies `/api`; browser code does not call a separately hardcoded localhost
  backend. An explicit port override follows through to the proxy.
- API identity/health, frontend HTML and proxied API health must pass before browser
  launch. Windows ShellExecute opens the **registered default browser**. If it fails,
  servers remain available and the working URL is printed. If readiness fails, no
  broken page is opened.
- Already-running matching apps are reopened without duplicate setup/processes.
  Project locks prevent concurrent installers. Port conflicts are reported; no
  unrelated process is killed and ports are not arbitrarily cycled.

**Keep the launcher window open. Ctrl+C stops only its own API/UI children. MongoDB
is detached and intentionally left running. Never delete `.data/mongo` or media to
fix startup.** The existing frontend `0.0.0.0` binding is retained for preview/LAN/
container use; API/MongoDB use loopback. Do not port-forward this local preview or
expose it to untrusted networks. External beta needs its extra access/security setup.

## Intro sound: reliable gesture, not fake automation

Allowed autoplay is attempted without requiring a button. Browser policy may still
block sound on a fresh origin/profile. Enter, Space or a genuine tap/click inside the
focused intro calls audio playback in that **trusted gesture**, restarts the visual
scene/playhead together, and gives the complete intro a fresh timer. Explicit Mute
is respected; Escape/Skip does not unexpectedly start audio. Reduced-motion mode
keeps a static short intro; a sound gesture may hold that static scene for the audio.

No synthetic JavaScript click/key or unfocused OS-wide keyboard injection is used.
Such automation generally cannot grant browser activation and could affect another
application. Universal forced autoplay is **not** promised.

## Existing installations and private service configuration

Back up the app and persistent stores first. Keep `backend/.env` (especially its
persistent JWT/encryption secret), `frontend/.env`, `.data/mongo`, media and configured
remote stores unchanged. The ZIP excludes filled env files, private keys, database
records and customer-generated media; it does not import your current accounts/shows.
Do not blindly overlay recovered source on a richer/custom historical native release.
The launcher does not change your selected AI-model configuration.

Real AI/voices, Google login, email and **Stripe TEST** require valid private service
configuration, internet and applicable provider terms. Bundled software does not
provision those credentials/accounts. Setup makes no AI, voice, payment, email or
cloud-migration requests. See [AI configuration](AI_PIPELINE.md),
[environment reference](ENVIRONMENT.md) and [vendor licenses/source links](WINDOWS_THIRD_PARTY.md).
The optional `upgrade_21plus.bat` is not invoked during normal launch.

## Optional commands

```bat
thelaunch.bat                    REM normal checks/setup/start/default browser
start.bat --repair               REM separate venv reinstall + fresh frontend build
start.bat --skip-mongodb         REM use only the reachable configured database
start.bat --no-browser           REM no automatic browser window
start.bat --port 3050            REM explicit frontend override
start.bat --api-port 8011        REM explicit API override
python start.py                 REM same path if Python already runs
python Launcher.py              REM compatibility alias
install.bat                     REM prepare only, do not start
install.bat --with-browser-tests REM optional test packages/browser, needs internet
```

Stop only the web-app window before repair; leave MongoDB running. `PORT` defaults
to 3000, `API_PORT` to 8001 and they must differ. No app source is auto-updated.
Installer **1.2.3** retains the 1.2.1 project-local TEMP/TMP/TMPDIR, Yarn/npm caches,
pip no-download-cache and stage-specific disk checks. No global cache/data is purged.

## macOS / Linux

`sh ./start.sh` uses the existing source installer with native dependencies. It does
**not** try to execute this Windows runtime. Python installation via apt/Homebrew
can need user/system approval; Debian/Ubuntu may need matching `python3-venv`.
Supported portable MongoDB targets remain OS/CPU/library-specific. This Windows
bundle is not a promise of universal macOS/Linux prerequisites.

## Validation and troubleshooting

Offline unit/fixture checks (not production-data installation tests):

```text
python scripts/test_installation.py
python scripts/test_one_click_start.py
python scripts/test_installer_storage.py
python scripts/test_prepared_bundle.py
powershell -NoProfile -File scripts/test_windows_bootstrap.ps1
```

The separately served prepared frontend was checked with all API calls intercepted
and external requests blocked: autoplay allowed/blocked, real Enter/Space/mobile tap,
synthetic-key rejection, audio/visual sync, fresh timing, Mute, Skip, reduced motion,
responsive fit and explicit consent. No paid/provider requests were made.

**This workspace is Linux.** Windows dependency markers/PE headers/import metadata,
installed-file/payload integrity, mocks, PowerShell Core fixtures and Chromium
emulation **are not a native Windows double-click/Authenticode-trust/UAC/default-
browser or physical-mobile execution test**. Verify on the target PC before release.
The included [manual Windows fixture workflow](../.github/workflows/windows-launcher.yml)
has not been run here; review account allowances before using it.

- **Missing/corrupt download:** extract the complete original ZIP into a **new** folder.
  Do not replace/delete saved data to fix program files. A missing runtime payload can
  use verified online fallback; an invalid manifest/signature stops for review.
- **No sound:** focus the page and press Enter/Space or tap the intro; check browser,
  tab, device mute/output and site sound permissions. Use Replay with sound.
- **Disk full:** free space on the reported drive/quota and relaunch. Do not repeatedly
  force reinstall, delete databases/media or purge unrelated caches.
- **Permission/UAC/enterprise policy:** approve only a legitimate dependency request
  if appropriate, otherwise consult your administrator. No automatic security bypass.
- **Restart requested:** save work and restart Windows yourself, then relaunch.
- **Dependency/build error:** read the visible error; check complete extraction,
  supported Windows/CPU, RAM, disk and connection. Use repair only when needed.
- **Port conflict:** use the existing app or close only the conflicting web window.
- **Database unavailable:** check URI/server/network or `.data/mongo-27017.log`;
  the launcher does not delete/reinitialize data as recovery.
- **No browser:** configure a Windows default browser or open the printed ready URL.
