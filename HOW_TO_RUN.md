# Da RoastBox — how to download and run this project

This archive is a **complete, standalone project** — the full source tree, every
asset, the launchers and the tests. It is **not** a patch, and you do not apply
it on top of anything.

---

## 1. Get the zip

**Option A — download from the workspace (fastest).**
The archive is at the workspace root as:

```
da-roastbox-complete.zip      (14 MB, 557 files)
```

Download that file and unzip it anywhere. It extracts to a folder named
`Da_RoastBox_v2/`.

**Option B — clone from GitHub instead.**

```bash
git clone -b arena/4d7ffea2-da-roastbox-v2 https://github.com/Deserius/Da_RoastBox_v2.git
cd Da_RoastBox_v2
```

Both give the same project. The zip has no `.git` history and no `node_modules`.

---

## 2. What you need installed first

| Requirement | Version | Why |
|---|---|---|
| Python | **3.11 or newer** (3.14 verified) | Backend (FastAPI) |
| Node.js | 18+, ideally 20 or 22 LTS | Frontend (React) |
| yarn | 1.22.x | Frontend install — npm produces a tree that will not build |
| MongoDB | 6 or newer | Database — **required** |
| ffmpeg | any recent | Highlight-reel export only (usually bundled) |

**On Windows 10?** See [`docs/WINDOWS_10.md`](docs/WINDOWS_10.md) — it covers the
one real caveat (MongoDB does not officially support Windows 10) plus long paths,
antivirus locks and the other Windows-specific traps.

Get MongoDB either with Docker:

```bash
docker run -d -p 27017:27017 --name roastbox-mongo mongo:7
```

or a free **MongoDB Atlas** cluster (copy its connection string).

---

## 3. Install — one command

**macOS / Linux**

```bash
cd Da_RoastBox_v2
./setup.sh
```

**Windows** — double-click `setup.bat`, or in Command Prompt:

```bat
cd Da_RoastBox_v2
setup.bat
```

`setup.sh` / `setup.bat` do these things:

1. Create a `.venv` and install backend requirements.
2. Remove two `@emergentbase/*` dev packages that point at `assets.emergent.sh`,
   a host that no longer exists. *(The bundled `install.sh` runs
   `yarn install --frozen-lockfile`, which fails on exactly those two. They only
   provide the Emergent dev overlay and visual editor — `craco.config.js`
   already loads them defensively and logs "overlay disabled" when absent, so
   nothing else changes.)*
3. If your network cannot reach `registry.yarnpkg.com`, rewrite the lockfile
   hosts to `registry.npmjs.org` for the duration of the install.
4. Install frontend dependencies with `yarn install` (yarn is required — see
   "Why yarn, not npm" below).
5. Generate `backend/.env` with a random `JWT_SECRET` and working local defaults.
6. Print the run commands, and warn if no database is listening on port 27017.

If you would rather do it by hand:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt

cd frontend
python ../scripts/prepare_package_json.py package.json   # drops the 2 dead devDeps
cp yarn.lock yarn.lock.bak
python ../scripts/fix_lockfile_registry.py yarn.lock      # optional: registry swap
yarn install --ignore-engines
mv -f yarn.lock.bak yarn.lock
# restore package.json from your backup when done
cd ..

cp backend/.env.example backend/.env
# then edit backend/.env: set MONGO_URL, DB_NAME, JWT_SECRET
```

### Why yarn, not npm

`frontend/package.json` pins 46 transitive versions through yarn's `resolutions`
field, and `yarn.lock` records 1457 exact tarball URLs. npm ignores `resolutions`
and hoists differently, producing a tree that **will not build**: ajv 6 lands
where `ajv-keywords@5` requires ajv 8, and `craco build` dies with
`MODULE_NOT_FOUND` inside `terser-webpack-plugin`. This is not an app bug; it is
npm resolving a different graph. Install yarn if you do not have it:

```bash
npm install -g yarn
```

---

## 4. Run it

Two terminals.

**Terminal 1 — backend**

```bash
cd Da_RoastBox_v2
. .venv/bin/activate
cd backend
uvicorn server:app --reload --port 8001
```

Windows: `..\.venv\Scripts\uvicorn server:app --reload --port 8001`

**Terminal 2 — frontend**

```bash
cd Da_RoastBox_v2/frontend
npm start
```

Open **http://localhost:3000**.

The frontend proxies `/api` to the backend on port `8001` automatically
(`API_PROXY_TARGET` in `frontend/.env`), so nothing else needs configuring.

**One-shot (macOS/Linux):** `./setup.sh --run` installs and starts both.
**One-shot (Windows):** `setup.bat run`

---

## 5. First-run checklist

1. Click **"Browse as guest"** on the sign-in screen — unlimited credits.
2. Go to **Settings → Connect your services**.
3. Enter the console passphrase: **`roastbox`**
4. Paste your keys: **OpenRouter**, **OpenAI**, **ElevenLabs**, **Stripe**
   (secret key + webhook secret), **Google** (client ID + secret).
5. Click **Verify & save**. Keys are validated, stored encrypted, and written to
   `backend/.env` (gitignored).

> **Change both secrets before exposing this publicly:**
> `RUNTIME_SETTINGS_PASSPHRASE` (console passphrase) and `JWT_SECRET`, in
> `backend/.env`.

---

## 6. About `ROASTBOX_DRY_RUN`

`setup.sh` writes `ROASTBOX_DRY_RUN=true`. In that mode, roast scripts and audio
are generated by a local stand-in so the whole app works **with no internet and
no API keys** — useful for checking the UI, cast, timing, credits and playback.

The audio in this mode is a quiet tone, not speech, and the jokes are generic
filler. **Set it to `false` once you've added a real OpenRouter or OpenAI key**
so live AI is used:

```ini
ROASTBOX_DRY_RUN=false
```

Then restart the backend.

---

## 7. Verify the install

```bash
cd backend
python scripts/test_pipeline_port.py     # 42 checks, no network needed
python scripts/test_byok_generation.py   # proves generation end to end
python scripts/test_settings_console.py  # settings console + key persistence
```

Related suites: `test_rap_battle.py`, `test_lineup_roasts.py`,
`test_roast_showrunner.py`, `test_preview_limits.py`, `test_voice_first_mix.py`,
`test_voice_leveling.py`, `test_key_persistence.py`.

You can also run the original pytest suites in `backend/tests/`:

```bash
pip install -r requirements-test.txt
python -m pytest backend/tests -q
```

---

## 8. Optional: production build

```bash
cd frontend
CI=false npm run build      # emits frontend/build/
```

The backend serves `frontend/build/` automatically when present, so a single
`uvicorn` process can host the whole app.

For Render, `render.yaml` and `deploy/` are included. Set `APP_ENV=production`
and provide real secrets via environment variables — the release guard refuses
preview logins, dry-run mode and the runtime settings console in production.

---

## 9. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ENOENT` / `getaddrinfo assets.emergent.sh` during install | `install.sh`/`install.bat` ran instead of `setup.sh`/`setup.bat`. Use the setup scripts, or delete the two `@emergentbase/*` devDependencies lines from `frontend/package.json` first. |
| `yarn install` fails: "Client network socket disconnected before secure TLS connection was established" | Your network cannot reach `registry.yarnpkg.com`. The setup scripts rewrite the lockfile to `registry.npmjs.org` automatically; if you install by hand, run `python scripts/fix_lockfile_registry.py frontend/yarn.lock`. |
| `MODULE_NOT_FOUND` in `terser-webpack-plugin` / `ajv-keywords` | The frontend was installed with **npm**. npm ignores the repo's yarn-only `resolutions` field and resolves a tree that will not build. Delete `frontend/node_modules` and reinstall with yarn. |
| `KeyError: 'MONGO_URL'` on startup | `backend/.env` is missing or lacks `MONGO_URL`. Copy `backend/.env.example` and set it. |
| Backend starts but pages 404 | Frontend dev server not running, or `API_PROXY_TARGET` is not `http://127.0.0.1:8001`. |
| `pymongo.errors.ServerSelectionTimeoutError` | MongoDB is not running. Start the container or point `MONGO_URL` at Atlas. |
| Roasts fail with a connection error | No reachable provider. Add a real key and set `ROASTBOX_DRY_RUN=false`, or keep dry-run on to demo offline. |
| Reel/MP4 export fails | `ffmpeg` is not installed or not on `PATH`. |
| "This panel is limited to specific operator accounts" | `RUNTIME_SETTINGS_ADMINS` is set in `backend/.env`; remove it or add your email. |

---

## 10. Project layout

```
backend/            FastAPI app
  routes/           13 routers (roast, auth, payments, settings, …)
  services/         pipeline: roast_writer, voice_orchestrator, dry_run, …
  data/personas.json 40 roasters
  assets/           sfx, fonts, persona portraits
  scripts/          offline test suites
  tests/            pytest suites
frontend/           React 19 + CRA/CRACO + Tailwind
  src/              pages, components, hooks, theater
  public/assets/    crowd SFX, intro stings, about-author media
  .env              committed, secret-free (proxy + preview flags)
docs/               design and deployment notes
scripts/            operator utilities
deploy/             Render/Heroku configs
setup.sh/.bat       local setup (use these)
install.sh/.bat     original Emergent installer (needs assets.emergent.sh)
HOW_TO_RUN.md       this file
```
