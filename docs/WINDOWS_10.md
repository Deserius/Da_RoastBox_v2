# Running Da RoastBox on Windows 10

Short answer: **yes, it runs on Windows 10 x64** — with one caveat about MongoDB,
covered below. Nothing in the app itself requires Windows 11.

---

## 1. Requirements

| Component | What to install | Notes |
|---|---|---|
| Python | **3.11 or newer** from [python.org](https://www.python.org/downloads/windows/) | Tick **"Add python.exe to PATH"**. Avoid the Microsoft Store build. 3.14 works: every pinned dependency ships a cp314 Windows wheel. 3.10 or older fails — no wheels. |
| Node.js | **20 LTS or 22 LTS** from [nodejs.org](https://nodejs.org/en/download) | 18 works. 24+ is untested; 25+ warns. |
| yarn | Installed automatically by `setup.bat`, or `npm install -g yarn` | Required — see §5. |
| MongoDB | See §2 | **Required.** The app will not start without it. |
| ffmpeg | Optional | Only for MP4 highlight-reel export. Bundled via `imageio-ffmpeg`, so usually nothing to install. |

`setup.bat` checks each of these and stops with a specific message if one is missing.

---

## 2. MongoDB on Windows 10 — the one real caveat

MongoDB's official platform matrix lists only **Windows 11 x64** and
**Windows Server 2022** for versions 7.x, 8.x and 9.x. Windows 10 is **not**
officially supported.

In practice the **7.0.x Windows x64 build installs and runs on Windows 10**.
That is "works but unsupported" — fine for a laptop, not something to build a
business on.

Your three options, easiest first:

**A. MongoDB Atlas (recommended, free, no install)**

1. Sign up at <https://www.mongodb.com/cloud/atlas/register>
2. Create a free **M0** cluster.
3. *Database Access* → add a user and password.
4. *Network Access* → **Add IP Address** → *Allow Access From Anywhere*
   (or just your home IP).
5. *Connect* → *Drivers* → copy the `mongodb+srv://...` string.
6. Open `backend\.env` and replace the `MONGO_URL=` line with it. Keep the
   `?retryWrites=true&w=majority` suffix.

This works on every Windows 10 edition, including Home, and needs no admin rights.

**B. Local MongoDB 7.0.x**

1. Download the **7.0.x Windows x64 MSI** from
   <https://www.mongodb.com/try/download/community> — *not* the 8.x or 9.x build,
   those are Windows 11 only.
2. During install choose **Complete** and keep
   **"Install MongoDB as a Service"** checked. It then starts automatically.
3. Leave `MONGO_URL=mongodb://localhost:27017` as `setup.bat` wrote it.

If the installer refuses to run, right-click → *Properties* → *Unblock* first, and
run it as Administrator.

**C. Docker Desktop**

Needs Windows 10 **Pro, Enterprise or Education** for Hyper-V (Home needs WSL2
backend plus virtualization enabled in BIOS).

```bat
docker run -d -p 27017:27017 --name roastbox-mongo mongo:7
```

### Using a newer Python (3.14, or 3.15 when it lands)

The pinned dependency set installs cleanly on Python 3.14 with **binary wheels
only** — no compiler, no Visual Studio Build Tools. Verified by resolving the
whole `backend/requirements.txt` for `cp314-win_amd64`:

```
numpy 2.4.6          cp314-win_amd64
pydantic_core 2.50   cp314-win_amd64
pillow 13.0.0        cp314-win_amd64
cryptography 50.0.2  cp311-abi3-win_amd64
pymongo 4.18.3       cp314-win_amd64
jiter 0.19.0         cp314-win_amd64
cffi 2.1.1           cp314-win_amd64
websockets 17.4      cp314-win_amd64
charset-normalizer   cp314-win_amd64
imageio-ffmpeg       py3-none-win_amd64
+ 39 pure-Python wheels
sdists requiring compilation: 0
```

So `setup.bat` accepts anything **3.11 or newer** and only prints a note for
versions it was not built against. If a future Python ever does break the
install, you can (a) install 3.13 side by side and let `py -3.13` be picked up,
or (b) point `PY_PYTHON` at 3.13:

```bat
set PY_PYTHON=3.13
setup.bat
```

To install 3.13 alongside 3.14 without replacing it, use the python.org
installer and leave "Add to PATH" unticked for the new one — the `py` launcher
picks up every installed version.

---

## 3. Install and run

1. Right-click the ZIP → **Extract All** to a short writable path such as
   `C:\RoastBox`. Do **not** run it from inside the ZIP viewer — Windows mounts
   those read-only and virtualenv creation fails.
2. Double-click **`setup.bat`**.
3. If MongoDB is not running yet, the script tells you and prints the options above.
4. Start the app — two Command Prompt windows:

```bat
REM Window 1 - backend
cd /d C:\RoastBox\backend
..\.venv\Scripts\uvicorn server:app --port 8001

REM Window 2 - frontend
cd /d C:\RoastBox\frontend
yarn start
```

Or simply `setup.bat run`, which opens both.

5. Open <http://localhost:3000> and click **"Browse as guest"**.
6. **Settings → Connect your services**, passphrase **`roastbox`**, paste your
   OpenRouter / OpenAI / ElevenLabs / Stripe / Google keys.

---

## 4. Windows 10 specifics that actually bite

**Do not use `install.bat` / `thelaunch.bat` / `start.bat`.** They run
`yarn install --frozen-lockfile`, which fails on two `@emergentbase` packages
pinned to `assets.emergent.sh`. The original launcher also expects the
*preinstalled* Windows bundle (`runtime/windows-x64/`), which a source download
does not contain. `setup.bat` is the supported path for a source download.

**Long paths.** Windows 10 blocks paths over 260 characters by default and
`node_modules` nests deeply. Extract to `C:\RoastBox`, not
`C:\Users\...\Downloads\Da_RoastBox_v2 (1)\...`. If you still hit `ENAMETOOLONG`,
enable long paths once in an **Administrator** PowerShell and reboot:

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
```

**Antivirus / Defender.** Real-time scanning can lock `node_modules` mid-install
(`EPERM`, `EACCES`, or half-installed packages). Add the project folder to
Defender's exclusions: *Windows Security → Virus & threat protection → Manage
settings → Exclusions → Add folder*.

**PowerShell execution policy.** `setup.bat` calls PowerShell only for the
built-in `-ExecutionPolicy Bypass`, process-scoped. It never changes your machine
policy. If your organization blocks even that, skip the check — it is only a
port probe — and verify manually that MongoDB is listening on 27017.

**SmartScreen.** Newly downloaded `.bat` files may show "Windows protected your
PC". *More info → Run anyway*. If you prefer, open `setup.bat` in Notepad first
to read it — it is plain batch, ~300 lines, ASCII only.

**Windows 10 Home and `py -3`.** If the `py` launcher is missing, `setup.bat`
falls back to `python` on `PATH` automatically.

---

## 5. Why yarn, and not npm

The project's dependency tree depends on two yarn features:

* **`resolutions`** — 46 transitive versions are pinned in `frontend/package.json`
  using yarn's `resolutions` field. npm ignores it.
* **`yarn.lock`** — 1457 exact tarball URLs with integrity hashes.

Installing with npm produces a *different* tree: ajv 6 gets hoisted where
`ajv-keywords@5` needs ajv 8, and `craco build` / `yarn start` dies with
`MODULE_NOT_FOUND` inside `terser-webpack-plugin`. That is not a bug in the app —
it is npm resolving differently. Use yarn.

`setup.bat` installs yarn globally with npm if it is missing.

**If `yarn install` fails with a TLS error** ("Client network socket disconnected
before secure TLS connection was established"), your network cannot reach
`registry.yarnpkg.com`. `setup.bat` already rewrites the lockfile's URLs to
`registry.npmjs.org` (identical tarballs, identical sha1 hashes) before
installing, and retries against the original host if that fails. Both files are
restored afterwards, so the repo stays unmodified.

---

## 6. Verifying the install

```bat
cd /d C:\RoastBox\backend
..\.venv\Scripts\python scripts\test_pipeline_port.py
..\.venv\Scripts\python scripts\test_byok_generation.py
..\.venv\Scripts\python scripts\test_settings_console.py
```

Then open <http://localhost:3000>, sign in as guest, and start a roast. With
`ROASTBOX_DRY_RUN=true` (what `setup.bat` writes) it works with no internet and
no API keys — the audio is a tone, not speech. Set it to `false` once a real
OpenRouter or OpenAI key is saved.

---

## 7. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `'python' is not recognized` | Python was installed without "Add to PATH". Re-run the installer → *Modify* → tick it, or reinstall. |
| `'yarn' is not recognized` right after setup | Open a **new** Command Prompt; PATH changes do not apply to already-open windows. |
| `ERROR: Node ... is too old` | Install Node 20 or 22 LTS, reopen the terminal. |
| `yarn install` → `EPERM`/`EACCES` | Antivirus lock. Add the folder to Defender exclusions; delete `frontend\node_modules` and retry. |
| `yarn install` → TLS / `socket disconnected` | `registry.yarnpkg.com` unreachable. `setup.bat` handles it; if you install by hand, use the same lockfile rewrite or a VPN/DNS change. |
| `yarn start` → `ERR_OSSL_EVP_UNSUPPORTED` | Node version mismatch. Install Node 20 LTS. |
| `pymongo.errors.ServerSelectionTimeoutError` | MongoDB is not running or `MONGO_URL` is wrong. Check `services.msc` for `MongoDB`, or fix Atlas credentials. |
| App loads but every page 404s | Backend not running on 8001, or `frontend\.env` has a wrong `API_PROXY_TARGET`. |
| Reel export fails | `ffmpeg` unavailable. Rare with `imageio-ffmpeg`; install ffmpeg and add it to `PATH`. |
| Port 8001 already in use | Something else is bound: `netstat -ano | findstr :8001`, then `taskkill /PID <pid> /F`, or start on another port and update `API_PROXY_TARGET`. |

---

## 8. Uninstalling

Delete the `C:\RoastBox` folder. If you installed MongoDB locally, uninstall it
from *Apps & features* and remove `C:\Program Files\MongoDB` plus the
`C:\data\db` directory if you created one. Nothing is written to the registry
except by the MongoDB and Python/Node installers themselves.
