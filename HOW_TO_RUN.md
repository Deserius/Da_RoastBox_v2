# Da RoastBox — how to download and run this project

This is a **complete, standalone project** — the full source tree, every asset,
the launcher and the tests. It is **not** a patch; you do not apply it on top
of anything.

The short version: extract the zip, run `python install.py` once to set your
API keys, then double-click `RUN.bat` (or run `./run.sh`). That's it — no
MongoDB, Node.js, or Yarn required.

---

## 1. Get the project

**Option A — download the zip (fastest).** Unzip it anywhere. It extracts to
a folder named `Da_RoastBox_v2/`. Prefer a short local path, e.g.
`C:\RoastBox` on Windows, and extract *all* files first — don't run anything
from inside the ZIP viewer.

**Option B — clone from GitHub instead.**

```bash
git clone -b arena/4d7ffea2-da-roastbox-v2 https://github.com/Deserius/Da_RoastBox_v2.git
cd Da_RoastBox_v2
```

Both give the same project.

---

## 2. What you need installed first

| Requirement | Version | Why |
|---|---|---|
| Python | **3.11, 3.12, 3.13, or 3.14** | Runs everything — backend, launcher, key setup |

That's the whole list. Specifically, you do **not** need:

- **MongoDB** — the database is built in (`backend/db.py`), stores its data in
  `backend/local_storage/`, and needs nothing installed or running. If you
  specifically want a real MongoDB server (e.g. for multi-device sync), set
  `MONGO_URL` in `backend/.env` to a real `mongodb://` or `mongodb+srv://`
  connection string (a free [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register)
  cluster works well) — everything else stays the same.
- **Node.js / Yarn** — the frontend ships prebuilt (`frontend/build/`) and is
  served by the same Python process as the API. You only need Node/Yarn if you
  want to edit the frontend's *source* and rebuild it (see §8 below).
- **ffmpeg** — only needed for highlight-reel (MP4) export; the app otherwise
  works fine without it.

**On Windows 10?** MongoDB isn't officially supported there — irrelevant now
since you don't need MongoDB at all. See [`docs/WINDOWS_10.md`](docs/WINDOWS_10.md)
for the remaining Windows-specific notes (long paths, antivirus locks).

---

## 3. Set your API keys

```bash
python install.py          # Windows: python install.py  (or py install.py)
```

This opens a small desktop window — one row per service (OpenAI, OpenRouter,
ElevenLabs, Stripe secret key + webhook secret, Google OAuth client ID +
secret). For each one:

1. Paste the key.
2. Click **Verify** — this makes one real, lightweight call to that provider
   so you know immediately whether it works.
3. Click **Save** — writes it straight into `backend/.env`, which stays on
   your machine, is git-ignored, and persists across restarts and re-runs.

It needs nothing beyond a stock Python install (just the standard library +
Tkinter), so you can run it before setting up anything else. You can also
skip this step and come back to it later — the app runs in a local demo mode
without any keys — or use the in-app Settings console instead (passphrase
below) once the server is running.

**Google sign-in needs one extra one-time step in Google Cloud Console.**
Pasting a client ID/secret here only checks that Google *recognizes the
pair* — it can't catch the #1 cause of sign-in failing later with
`Error 400: redirect_uri_mismatch`. That error means the redirect URI Google
received doesn't exactly match one of the **Authorized redirect URIs** on
your OAuth client. For the default local run (`http://127.0.0.1:8001`), add
both of these on the OAuth client in Google Cloud Console → **APIs & Services
→ Credentials**:

- Authorized redirect URI: `http://127.0.0.1:8001/auth-complete.html`
- Authorized JavaScript origin: `http://127.0.0.1:8001`

Match the port you actually run on, and note that Google treats `localhost`
and `127.0.0.1` as different values — use whichever one is actually in your
browser's address bar. `install.py` shows this same hint next to the Google
fields, and the in-app Settings console shows it computed from the page's
actual origin.

**Optional: free local voice, no API key at all.** Without an OpenAI or
ElevenLabs key, voice generation fails with a 503. Run this once to add a
built-in, offline, natural-sounding voice fallback (Kokoro) instead:

```bash
python scripts/setup_local_voice.py
```

This installs one extra package and downloads its ~150MB of model weights
into `backend/models/kokoro/`. It needs Python 3.10–3.13 (a limit of the
`kokoro-onnx` package itself, not this project); on 3.14 the script prints a
clear note and the app keeps working exactly as before, still requiring an
OpenAI/ElevenLabs key for voice. Once installed, every comic persona speaks
with its own distinct assigned voice automatically — nothing else to
configure, and it is tried only after ElevenLabs and OpenAI are unavailable
or fail, so a configured paid key is always preferred when it works.

---

## 4. Run it

**Windows:** double-click **`RUN.bat`**.
**macOS / Linux:** run **`./run.sh`**.

The first run creates a `.venv` virtual environment and installs the backend's
Python packages (a couple of minutes). Every run after that starts in a few
seconds. Either script is equivalent to:

```bash
python server.py
```

`server.py` checks what it needs, fixes what it safely can, starts the server,
and opens the app in your default browser. It prints a specific message
instead of a traceback if something is missing:

```
  [ok]   Python 3.13.2
  [ok]   All 13 required packages import
  [ok]   backend/.env found
  [ok]   JWT_SECRET present
  [ok]   Port 8001 is free
  [ok]   Database: built-in, no installation needed (backend/local_storage/)
  [ok]   Frontend: serving prebuilt frontend/build from this same server
```

Useful flags (pass them to `RUN.bat`, `run.sh`, or `python server.py` directly):

| Flag | What it does |
|---|---|
| `--check` | Diagnose only; starts nothing |
| `--fix` | Regenerate `backend/.env` if it's missing/broken, then start |
| `--port 8002` | Use a different port |
| `--no-browser` | Don't open a browser automatically |
| `--dev` | Use the Node/Yarn frontend dev server on :3000 instead of the prebuilt build (for editing frontend source) |

---

## 5. First-run checklist

1. Click **"Browse as guest"** on the sign-in screen — unlimited credits in
   preview mode.
2. If you haven't already run `install.py`, open **Settings** in the app and
   enter the console passphrase: **`roastbox`**. From there you can paste and
   verify the same keys `install.py` manages.
3. Once you've added a real OpenRouter or OpenAI key, turn off demo mode (see
   §6) to get live AI-written shows and real speech.

---

## 6. About `ROASTBOX_DRY_RUN`

`backend/.env` is generated with `ROASTBOX_DRY_RUN=true`. In that mode, roast
scripts and audio are generated by a local stand-in, so the whole app works
**with no internet and no API keys** — useful for checking the UI, cast,
timing, credits and playback. The audio in this mode is a quiet tone, not
speech, and the jokes are generic filler.

Set it to `false` once you've added a real key, in `backend/.env`:

```ini
ROASTBOX_DRY_RUN=false
```

Then restart the server.

---

## 7. Verify the install

```bash
cd backend
..\.venv\Scripts\python scripts/test_pipeline_port.py     (Windows)
../.venv/bin/python scripts/test_pipeline_port.py          (macOS/Linux)
```

Related suites, same pattern: `test_byok_generation.py`, `test_settings_console.py`,
`test_rap_battle.py`, `test_lineup_roasts.py`, `test_roast_showrunner.py`,
`test_preview_limits.py`, `test_voice_first_mix.py`, `test_voice_leveling.py`,
`test_key_persistence.py`, `test_stripe_direct.py`.

You can also run the original pytest suites in `backend/tests/`:

```bash
pip install -r requirements-test.txt
python -m pytest backend/tests -q
```

---

## 8. Optional: editing the frontend source

The app runs entirely from the prebuilt `frontend/build/` folder — you don't
need this section unless you want to change the frontend's React source and
see your changes. That still needs Node.js and Yarn (the repo's dependency
tree is yarn-only; npm will not build it — see `setup.sh`/`setup.bat` for
why). Once you have them:

```bash
cd frontend
yarn install --ignore-engines
yarn start            # dev server on :3000, auto-reloads on save
# when you're happy with your changes:
CI=false yarn build    # writes the new frontend/build/
```

`setup.sh` / `setup.bat` automate the Yarn install (including a couple of
known Windows/registry workarounds); run them only if you're doing frontend
development. `RUN.bat` / `run.sh` do **not** need them.

For Render or another always-on host, `render.yaml` and `deploy/` are
included; see `docs/RENDER_DEPLOYMENT.md`.

---

## 9. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "Refusing to start: MONGO_URL points at localhost but nothing is listening" | `backend/.env` was pointed at a real local MongoDB that isn't running. Set `MONGO_URL=embedded` in `backend/.env` to go back to the built-in database (no install needed), or start that MongoDB. |
| `ModuleNotFoundError: No module named 'emergentintegrations'` | You're on an old download. This build calls Stripe directly — update to the current `backend/services/stripe_checkout.py`. |
| `ModuleNotFoundError` for anything else | A package is missing: `cd backend && ..\.venv\Scripts\python -m pip install -r requirements.txt` |
| A key you saved keeps getting rejected | Re-run `python install.py`, click Verify on that row — it tells you exactly what the provider said. If Verify passes but the app still complains, check `backend/.env` doesn't have the same key set twice. |
| `KeyError: 'JWT_SECRET'` or similar on startup | `backend/.env` is missing or incomplete. Run `python server.py --fix`, or `python install.py` (it creates `.env` automatically). |
| Backend starts but the page is blank/404 | `frontend/build/index.html` is missing. Either use the download as-is (it ships prebuilt), or see §8 to build it. |
| Roasts fail with a connection error | No reachable AI provider. Add a real key with `install.py` and set `ROASTBOX_DRY_RUN=false`, or keep dry-run on to demo offline. |
| Reel/MP4 export fails | `ffmpeg` is not installed or not on `PATH`. |
| "This panel is limited to specific operator accounts" | `RUNTIME_SETTINGS_ADMINS` is set in `backend/.env`; remove it or add your email. |

---

## 10. Project layout

```
server.py            double-click entry point: checks, fixes, starts, opens the browser
install.py           desktop API key manager -> writes straight into backend/.env
RUN.bat / run.sh      thin Windows/Unix wrappers around server.py (create .venv on first run)
backend/
  server.py           the FastAPI app (ASGI "server:app")
  run_server.py       the launcher behind server.py (diagnoses, then serves)
  db.py               built-in database (embedded mode) + real-MongoDB fallback
  routes/             routers (roast, auth, payments, settings, …)
  services/           pipeline: roast_writer, voice_orchestrator, stripe_checkout, …
  data/personas.json  40 roasters
  assets/             sfx, fonts, persona portraits
  local_storage/       built-in database file + local media (gitignored)
  scripts/            offline test suites
  tests/              pytest suites
frontend/
  build/              prebuilt static site - this is what actually runs
  src/                React source (only needed if you edit the frontend)
docs/                 design and deployment notes
scripts/              shared setup/operator utilities
deploy/               Render/Heroku configs
setup.sh / setup.bat  optional: Node/Yarn frontend-dev setup (not needed to run the app)
HOW_TO_RUN.md         this file
```
