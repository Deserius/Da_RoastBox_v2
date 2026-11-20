# GitHub → Render Free: owner deployment guide

## 1. Scope and non-negotiables

This handoff keeps Python/FastAPI, MongoDB, FFmpeg and React. The owner uploads/deploys; no cloud resource, migration, secret or public app URL was created by the preparation work. Leave original applications/databases and older projects untouched.

- **Free web-service compute only**; no paid instance/disk/worker, trial or automatic upgrade.
- **Stripe TEST only**. Existing approved real-generation and 4242 TEST-checkout permissions have been consumed. None of the commands below require repeating them.
- Preserve current users, balances, unlocks, transactions, sessions, history, encrypted keys and original media. New normal accounts receive 25; never reset old accounts.
- Additional beta password is mandatory, not a substitute for normal account protection or 21+ consent.
- Configure real providers; do not substitute mock output or unapproved free models.

**Read [DATA_PRESERVATION.md](DATA_PRESERVATION.md) before connecting any database.** This workspace snapshot predates some authorized real QA. A missing purchase/show here is not permission to recreate it or add credits.

## 2. Repository layout and entry points

Extract the **flat sanitized ZIP into a NEW folder**. These paths must be at the GitHub repository root:

```text
Dockerfile                  # Node 22.23.4 frontend stage → Python 3.13 runtime
render.yaml                 # one Free Docker web service; manual deploys
backend/server.py           # ASGI app: server:app
backend/requirements-runtime.txt  # pinned runtime closure
frontend/package.json
frontend/yarn.lock
frontend/src/index.js       # React entry → App.js routes
frontend/public/            # bundled portraits, soundtrack, story, callback HTML
scripts/                    # guarded checks and owner-operated migration tools
deploy/entrypoint.sh        # drops privileges to roastbox uid 10001
deploy/render.env.example   # blank-secret template
.github/workflows/render-release.yml # optional manual-only checks
```

Do not upload a ZIP as the only GitHub file: extract its contents first. GitHub's browser uploader may require batches; Git/GitHub Desktop is easier for the full tree. Use a **new owner-selected repository**, not an existing V3/V4 deployment. Before committing, inspect staged filenames. Do not copy `backend/.env`, `.data`, `.private`, customer media or an original installation's caches into this clean folder.

With Git installed, the owner may initialize this clean extracted folder, commit it, add their actual repository URL and push. No repository/account is created by these instructions. The included workflow does **not** run on upload/push; it is opt-in to avoid surprise CI usage.

## 3. External durable services — no SQL rewrite

Render Free has no persistent disk. Use:

1. **Existing/owner-approved external MongoDB with TLS**. Keep the authoritative database and `DB_NAME`, or perform the explicit empty-target copy in the preservation guide. If using Atlas Free, verify its actual current plan, storage and network rules. Never select a paid tier/trial or replace Mongo with expiring Free Postgres.
2. **An owner-approved PRIVATE Blob store** with `BLOB_READ_WRITE_TOKEN`. This Python adapter works outside Vercel; a second Vercel app deployment is not needed. Never select a public store for customer images/audio/reels. Do not overwrite another app/store.
3. Existing OpenRouter/OpenAI and Stripe TEST credentials, supplied privately in Render. Optional configured ElevenLabs/Emergent backups remain optional.

**Free eligibility is a launch gate, not an assumption.** Vercel Hobby restricts use to personal/non-commercial projects. A branded or revenue-oriented beta does not automatically qualify merely because payments are TEST. Confirm eligibility before using it; if not eligible, stop and choose an expressly approved compatible alternative. Do not start a paid plan or rewrite storage silently. No store or new account was provisioned here.

The app's first release startup performs a small private-storage write/read canary if needed. This consumes storage operations, not AI/TTS generation. No remote canary was run during source preparation.

## 4. Prepare private configuration

Copy `deploy/render.env.example` **outside Git** (for example `.private/render.env` in the clean local folder). Populate it from the correct existing private configuration; do not paste keys into chat or a browser build variable.

Required details are in [ENVIRONMENT.md](ENVIRONMENT.md). In particular:

- Keep **the original `JWT_SECRET`**. Changing it breaks decryption of saved BYOK keys.
- Set `APP_ENV=beta`, exact HTTPS origin and host, TLS Mongo settings and private Blob token.
- Obtain the beta gate only if you do not already have one. The owner runs:

  ```bash
  python scripts/create_beta_gate.py --output .private/beta-gate.env
  ```

  This prompts locally, writes the verifier/signing key exclusively, and never rotates JWT. Copy the two values into Render **without dotenv quote characters**. Do not rerun to replace an existing gate. This helper was tested with mocked, invalid fixture values only; no live gate credential was generated here.

- Keep `STRIPE_TEST_ONLY=true`; use your existing TEST secret key. A webhook signing secret belongs to its particular endpoint. The new Render endpoint needs its own correct TEST `whsec_...` value from Stripe's dashboard, not the old endpoint's signing secret.
- Keep the approved writer order and unlimited-preview beta defaults in the template. Provider usage is still billable; this is not unlimited free AI.
- Keep `DATA_IMPORT_CONFIRMED=false` until the data/media and missing-history reconciliation are actually complete. **Do not set true merely to make startup pass.**

Static no-network check, using your clean Python environment:

```bash
python scripts/render_preflight.py --env-file .private/render.env --check-runtime
```

Use `--origin https://ACTUAL-ASSIGNED-HOST.onrender.com` if the actual origin is not yet saved in the private file. This prints error codes, not secret values. Passing is a configuration check, not proof of Mongo/provider/storage connectivity or plan eligibility.

## 5. Create the Render service yourself

Use either path, not both:

### A. Blueprint

Connect the intended GitHub repository and choose **New Blueprint** using root `render.yaml`. Review the proposed resources before approving: exactly one `web`, `runtime: docker`, `plan: free`, one instance, **no disk/database/worker**. Fill `sync: false` values privately. Autodeploy is off; deployment is manual.

### B. Manual Web Service

| Render setting | Value |
| --- | --- |
| Source | Your intended GitHub repo/branch |
| Service type | Web Service, not Static Site |
| Runtime | Docker |
| Root Directory | Empty / repository root |
| Dockerfile Path | `./Dockerfile` |
| Docker Build Context | `.` |
| Instance type | **Free** |
| Instances / Uvicorn workers | **1 / 1** |
| Health Check Path | `/api/ready` |
| Auto deploy | Off / manual |
| Persistent disk | **None** |
| Build / Start command fields | Leave Docker defaults; do not override |

Use the environment template for both paths. With manual creation, also set the non-secret defaults from `render.yaml`; Docker alone defaults the public Explore button to false, so set `REACT_APP_ENABLE_PREVIEW_LOGIN=true` and its server-side beta flags deliberately.

Render assigns the real public hostname; **do not assume the suggested service name is available**. If the first build/start is refused because data/origin values are incomplete, leave the guard in place, copy the assigned URL from the dashboard, complete settings, then manually deploy. Do not use `ALLOWED_HOSTS=*` or disable the gate to bypass this.

Set:

```dotenv
APP_BASE_URL=https://ACTUAL-ASSIGNED-HOST.onrender.com
ALLOWED_HOSTS=ACTUAL-ASSIGNED-HOST.onrender.com
```

For the assigned default domain, the backend can derive its origin from Render's `RENDER_EXTERNAL_URL`; explicit `APP_BASE_URL` is preferable when setting a custom domain. Do not type scheme/path/port into `ALLOWED_HOSTS`.

## 6. What the container runs

Build stages, already encoded in Dockerfile:

```text
frontend: yarn install --frozen-lockfile --ignore-engines --non-interactive
          yarn build
backend:  python -m pip install --no-cache-dir -r requirements-runtime.txt
```

Docker uses public build arguments only. Keep:

```dotenv
REACT_APP_BACKEND_URL=
REACT_APP_ENABLE_PREVIEW_LOGIN=true
REACT_APP_SOURCE_DOWNLOAD_ENABLED=false
REACT_APP_ENABLE_SESSION_TUNNEL=false
```

Blank backend URL means **same-origin `/api`**. Never put localhost, port 8001, the workspace URL or an old deployment URL here. Never put a secret into `REACT_APP_*`; those values are public and baked into JavaScript. Changes require a rebuild. On Render, the disabled iframe session-tunnel flag preserves ordinary 401 responses; native installs retain their compatible absent-flag behavior.

The startup working directory is `/app/backend`. After a non-root privilege drop:

```sh
exec python -m uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1
```

`FRONTEND_BUILD_DIR=/app/frontend/build` mounts the SPA after the `/api` routes. `TMPDIR=/app/backend/media_tmp` is disposable working space, **not durable storage**. Single threads, shared media/generation capacity and `REEL_ENCODER_PRESET=ultrafast` bound memory; do not add workers or switch codecs without a new constrained test.

## 7. Domain-dependent integrations — keep real tests separate

- **Managed Google:** existing popup/redirect flow is preserved, not replaced with a new Google client. It uses the managed provider under `demobackend.emergentagent.com`, `/auth-complete.html` with state/mode, plus legacy `/auth/callback`. Confirm the provider accepts the new HTTPS origin/callbacks. Google and Explore already worked on the existing preview; that does not certify this new origin.
- **Stripe TEST webhook:** `https://YOUR-REAL-HOST/api/payments/webhook`; subscribe to the Checkout events handled in [API.md](API.md). The signed server webhook is exempt only from the extra beta page gate, not from Stripe signature/amount/ownership/TEST validation. Do not create a fresh checkout as a deployment check in this task.
- **Optional email:** Free blocks SMTP 25/465/587. Keep email disabled unless you configure `EMAIL_TRANSPORT=resend`, HTTPS Resend delivery, `EMAIL_FROM` and any required verified sender/domain. No real email-delivery claim is made.
- **Support/social links:** optional real public destinations, absent links hidden. Do not insert placeholder profiles.

## 8. Non-billable first checks

After authorized data setup/deployment, visit the assigned URL externally, not inside a third-party iframe. Check the beta password page, then 21+ consent, then account sign-in/Explore. Only use accounts and actions within the owner's authorization.

Read-only readiness:

```text
GET https://YOUR-REAL-HOST/api/health  → process/version only
GET https://YOUR-REAL-HOST/api/ready   → Mongo readiness only
```

These do not call paid writer/TTS/Stripe probes. `ready` is not a claim of end-to-end integrations. Settings shows **configured/not verified** capability flags. `ENABLE_PAID_DIAGNOSTICS=false` remains in force.

Use existing shows for navigation, transcript/replay/share/reel-status checks; do not regenerate historical shows, recreate an absent consumed purchase, top up a user or click a voice sample expecting it to be cost-free. First-time sample synthesis and reel storage/transfers consume provider/quota resources even when app preview credits are unlimited.

## 9. Free-tier reality and remaining gates

Render documents idle sleep after 15 minutes, roughly minute-long wake-up, loss of local files on sleep/restart/redeploy, 750 shared Free workspace hours/month, no Free disk/SSH/one-off jobs, and possible outbound-traffic suspension. Bandwidth/build overages may bill when a payment method is present or suspend/disable service otherwise. Review current limits and spend controls; this handoff does not guarantee a zero bill or bypass limits with keepalive traffic.

The local synthetic capacity probe passed below its unchanged **480 MiB API/media RSS guard** (latest 470.2 MiB workload; 483.4 MiB including the offline coordinator; two consecutive earlier runs also passed). This is **not** Render cgroup, cold-start, concurrency or remote-provider certification. 1080×1920 ultrafast MP4s were large: about 27.6 MB / 66.1 MB in the 30/60-second-budget fixtures. Free storage and transfer can fill quickly.

Sleeping/restarted processes cannot guarantee ongoing jobs or webhook delivery. Production/live payments/store release still need durable/idempotent jobs, recovery/monitoring, restore rehearsal, privacy/deletion/reporting flows, real-origin integrations, commercial-hosting eligibility and physical-device testing. **Free beta is not production-ready; 21+ alone does not grant Play Store approval.**

Official references: [Render Free](https://render.com/docs/free), [first deploy](https://render.com/docs/your-first-deploy), [Blueprint specification](https://render.com/docs/blueprint-spec), [Blob Python SDK](https://vercel.com/docs/vercel-blob/python-sdk-reference), [Blob private stores](https://vercel.com/docs/vercel-blob/using-blob-sdk), [Blob pricing](https://vercel.com/docs/vercel-blob/usage-and-pricing), [Hobby eligibility](https://vercel.com/docs/plans/hobby), [Stripe fulfillment](https://docs.stripe.com/checkout/fulfillment).
