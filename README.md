# Da RoastBox — local app and Render Free beta

A same-origin React + FastAPI + MongoDB + FFmpeg application. **Keep the existing scaffold:** no SQL migration, serverless rewrite, second frontend deployment or paid Render disk is required by this handoff.

> **Run it locally:** extract the ZIP, then double-click **`RUN.bat`** (Windows) or run **`./run.sh`** (macOS/Linux) — same thing as `python server.py`. The first run creates a Python virtual environment and installs the backend packages; after that it starts instantly and opens your default browser. **No MongoDB, Node.js, or Yarn install is required** — the database is built in and the frontend ships prebuilt. Set your API keys (OpenAI, OpenRouter, ElevenLabs, Stripe, Google) any time with **`python install.py`**, a small window that verifies and saves each key straight into `backend/.env`. See [START_HERE.txt](START_HERE.txt) and [HOW_TO_RUN.md](HOW_TO_RUN.md).

## Start here

1. **[Render deployment guide](docs/RENDER_DEPLOYMENT.md)** — exact repository layout, setup, build/start commands, origins and launch checks.
2. **[Environment/key reference](docs/ENVIRONMENT.md)** — required, optional, public and unnecessary settings.
3. **[Preserve data before deploying](docs/DATA_PRESERVATION.md)** — authoritative records, media, encrypted BYOK keys, balances and migration helpers.
4. **[API and browser route map](docs/API.md)**.
5. **[Validation and remaining gates](docs/RELEASE_READINESS.md)** — what was actually tested versus what still needs the owner's real deployment.
6. **[Operations](docs/OPERATIONS_RUNBOOK.md)** and **[integration details](docs/INTEGRATIONS.md)**.

**Status:** source preparation for an owner-uploaded, owner-deployed, password-protected beta. This is not a claim that Render has been deployed, that Google accepts the new origin, or that Free hosting is production-ready. The recovered source is not a certified complete copy of a richer historical native v1.5.2 installation.

## Deployment shape

```text
Browser → https://YOUR-ASSIGNED-SERVICE.onrender.com
             ├─ React pages/static assets
             └─ /api → FastAPI, one Uvicorn worker
                         ├─ existing/owner-approved external TLS MongoDB
                         ├─ owner-approved PRIVATE Blob store
                         ├─ approved OpenRouter writer + configured backups
                         ├─ real OpenAI/optional ElevenLabs speech
                         └─ Stripe TEST only
```

`render.yaml` creates **one Free web service**, with manual deploys and no paid disk, database, worker or trial. Free filesystem data is disposable: external Mongo and private durable media are mandatory. Free hosting does not make AI/TTS usage free. Confirm external-service eligibility/quotas and billing controls; do not upgrade or start trials to bypass a gate.

## Entry points

| Purpose | File / command |
| --- | --- |
| Render deployment | `render.yaml`, `Dockerfile` |
| Container privilege drop | `deploy/entrypoint.sh` |
| Backend application | `backend/server.py`, ASGI `server:app` |
| Container start | `python -m uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1` from `backend/` |
| Frontend | `frontend/src/index.js` → `frontend/src/App.js`; `yarn build` |
| Private configuration template | `deploy/render.env.example` — never commit the filled copy |
| Local/native entry | `server.py` (Windows: double-click **`RUN.bat`**; macOS/Linux: `./run.sh`) — checks requirements, starts the server, opens the browser; preserves `.env`/data |
| API key setup | `install.py` — desktop key manager, verifies and saves straight into `backend/.env` |

The Docker build produces the frontend; FastAPI serves that build using `FRONTEND_BUILD_DIR`. The Render form does not need separate build/start commands when using Docker. Never run MongoDB in the Free web-service container.

## Content and behavior

- Supplied **40-persona / 120-sample** catalog preserved byte-for-byte against the owner's supplied JSON. Seven authored comedy fields, IDs, names, voice metadata and tiers remain governed by the catalog contract.
- Approved writer for **both tiers**: OpenRouter **Claude Sonnet 4.5 → GPT-4.1 → GPT-4o**; only configured Emergent/OpenAI provider backups. No silent free-model replacement.
- Eight-stage writing scaffold, personalized multimodal inputs, one original first-person self-roast introduction per comic, actual writer/TTS model receipts and separate Clean direction.
- Fresh Adult ON and strongest unlocked heat: INFERNO if entitled, otherwise FIRE. Explicit Clean, lower heat, off-limits, drafts and entitlements win.
- Extra beta password **plus** normal account authorization and explicit consenting-21+ subject attestation, including Clean shows. Self-attestation is not verified age or store approval.
- Explore has no app daily generation/preview cap with the supplied beta configuration. It is billable to configured providers; provider quotas, concurrency and hosting limits still exist. Preview cannot purchase.
- Stripe stays TEST; redirects alone never grant credits. New normal accounts get 25, **existing balances are never reset**.

Provider moderation and output quality cannot be guaranteed. Do not promise “never censored,” perfect off-limits classification or objectively best jokes.

## Safe local validation

Use a clean, disposable environment and a running test MongoDB. Do not start another database on a port already occupied or stop an existing database.

```bash
python -m venv .venv
# Activate the venv using the command appropriate for your OS.
python -m pip install -r backend/requirements-dev.txt
python scripts/test_offline.py
```

The allowlisted runner blocks providers/network and non-test database names, does not load `backend/.env`, and uses disposable test databases. **Do not run arbitrary historical scripts** against an original API: some old UI/QA scripts contact it. The previously authorized real AI generation and genuine 4242 TEST purchase are consumed; missing snapshot records never authorize a repeat.

Optional built-frontend browser wiring checks (all requests locally intercepted):

```bash
python -m pip install -r backend/requirements-browser.txt
python -m playwright install chromium
python scripts/test_render_ui.py --build frontend/build
```

Build `frontend/build` first with the public flags in the deployment guide. The measured Linux capacity probe is `python scripts/benchmark_free.py`; its 480 MiB workload guard must not be raised. It is synthetic evidence, not Render certification.

`.github/workflows/render-release.yml` is **manual `workflow_dispatch` only**, with no deployment or paid-provider checks. Review your included Actions minutes before choosing to run it. A sanitized flat archive can be built with `python scripts/package_source.py --flat /path/outside/repo/source.zip`.

## Preservation rule

Source ZIP/Git must never contain filled env files, tokens, Mongo exports, database files, generated customer media, private logs or dependency/build caches. **Do not overwrite an original installation with this recovered source**. Extract separately, retain your authoritative data and follow the preservation guide before connecting the new app.
