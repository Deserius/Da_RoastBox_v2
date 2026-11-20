# Workspace clone and local setup

This is the original Da RoastBox React/FastAPI/MongoDB source and bundled assets imported from the supplied MEGA folder. The export contained **example environment files only**: it did not include live provider keys, the original MongoDB database, or previously generated user media. The roster, artwork, crowd sounds, fonts, interface, and original integration code are retained.

## Current workspace preview

The live preview uses a separate local MongoDB database and local media storage. Check the 21+ disclaimer, then choose **Explore the preview** to enter an isolated guest account. Its credits and unlocked features are for testing, not purchases or real account entitlements. Google sign-in remains available separately.

- Preview accounts cannot make purchases. They may use a personal OpenAI key in **Settings**, or a hosted key if the operator explicitly enables `ALLOW_PREVIEW_HOSTED_AI`. Hosted preview attempts have shared UTC daily limits (defaults: five shows and ten uncached voice samples); these are attempt counts, not a dollar cap, and failed attempts may count. A cached sample can be replayed without another generation. An ElevenLabs key is optional. Settings shows whether credentials are present, not whether they are valid.
- The original export did not include paid-service credentials or the original database. A small hosted chat and speech call was verified after a key was supplied to this workspace; Stripe checkout and hosted object storage still require separate live verification. Google sign-in uses the original managed service; its sign-in screen and app-side flow were tested, but a real account's consent and completed login still need a user test. A personal key in Settings is encrypted before storage. Protect the backend and its `JWT_SECRET`; rotating that secret makes saved keys unreadable.
- The workspace database and `backend/local_storage` are development data, not a production backup. Do not put sensitive customer data in a public preview. Show media is owner-only or shared through revocable share-scoped routes; ensure the underlying storage is not separately exposed.

This workspace explicitly enables unlimited preview generation (`PREVIEW_UNLIMITED_CREDITS=true`, shared hosted attempt limits `-1`). Those settings are for this disposable preview only; they do not change real account entitlements or turn production provider usage into a free service.

## Phones, tablets and reel playback

Open the authenticated Arena **Live Preview** on your device. A bare preview host may require platform access credentials; the application cannot change those platform permissions. Check the 21+ agreement and choose **Explore the preview**. On a small screen, the Studio step labels jump to the corresponding section and the roster initially shows eight cards; **Show all roasters** reveals the rest. Selected comics stay visible when the list is collapsed. The camera/photo picker accepts JPEG, PNG and WebP up to 8 MB per image.

Some mobile browsers or embedded frames block audio after an asynchronous fetch. If a sample says **Tap to play**, tap it again; it reuses the loaded clip. If a show asks for a sound tap, tap **Tap to play sound** or choose captions only. Open **Recent shows → Reels** to restore an export without replaying the show. Completed reels open in a native-control player, and **Download MP4** starts a real authenticated save (also available with the player closed). The preview container itself must permit popups/downloads; app code cannot override a platform sandbox.

A reel's 30/60-second choice is a maximum, not a promise of an exact duration: only complete roast lines that fit are included. The current renderer adds animated cast entrances, a hot-seat reveal, moving camera/embers, highlighted captions, reaction stamps and a branded sign-off. Re-exporting a previously completed reel at the same length upgrades the style without charging for that length again; existing files remain accessible. These exports reuse the show's existing voice clips and do not make new AI/TTS calls. See [Reels: creation, playback and download](REELS.md) and [the new host-voiced lineup format](SHOW_FORMAT.md).

## About Developer storybook

**About Developer** opens exclusively from the signed-in hamburger/account menu without leaving the current page. It contains ten narrated chapters, page controls, an optional continuous-listening mode, and visible text. Sentence highlighting follows the audio approximately rather than using word-level timestamps. If a mobile browser blocks automatic playback, tap **Play**; if audio cannot load, the written chapters remain available. The generated artwork and narration are bundled in `frontend/public/assets/about-author/`, so opening or replaying the book does not call an AI or TTS provider. The user's source photo is not included in the public app assets.

## Account menu, history and support

Use the upper-right menu button when signed in to view your profile, current plan and credits, navigate the app, open About Developer, or sign out. Open **Payment history** or **Usage history** to load the latest stored records for the signed-in account (up to 20 in each category). A new preview account will normally show empty history, and preview accounts cannot purchase. The existing credit ledger may omit some refunds, so use the current balance as the authoritative total rather than adding the displayed ledger entries.

**Help & developer contact** includes a short guide. If you have a real support address you want users to see, set `REACT_APP_SUPPORT_EMAIL` in `frontend/.env` (see `.env.example`) and rebuild/restart the frontend; this value is public in the browser, not a secret. If it is unset or malformed, no address is invented. Instagram, Facebook, TikTok and YouTube currently link to generic platform homepages and are labeled as placeholders; replace the links in `frontend/src/components/AccountMenu.jsx` with verified official profiles when available.

## Google sign-in

Check the 21+ disclaimer and select **Enter Da Roastbox**, then complete sign-in on Google's own page. The existing Emergent-managed Google provider is retained, so the app does not require a separate Google client ID or secret for this flow. Sign-in starts at the provider's working OAuth endpoint directly, avoiding the old wrapper page that may return a 404. The Google consent screen may identify `emergentagent.com` as the service. Never enter or share a Google password anywhere except Google's own page.

Google does not allow its sign-in page to run inside an iframe. When the app is embedded, sign-in therefore opens a separate window; allow pop-ups and return to the app after consenting. When the app is already in a regular browser tab, sign-in uses a normal redirect. If a popup is blocked or closed, the page displays a retry message. If a preview's sandbox or access controls prevent the popup from returning to the app, open the preview in a regular browser tab and try again.

The return URL must be reachable by the user's browser at the **same app origin** where sign-in began. Deploy `frontend/public/auth-complete.html` as `/auth-complete.html`, serve the React app on `/auth/callback`, and forward same-origin `/api` requests to the backend. Production deployments should use HTTPS and restrict `CORS_ORIGINS` to trusted frontend origins rather than `*`. The callback checks a fresh, time-limited state; the backend exchanges the provider's session ID and issues an independent app session. Existing accounts, balances, and unlocks in the configured MongoDB are preserved when the provider-returned email matches; an explicitly unverified email is rejected. Sessions issued before this change continue to work. If you started signing in before an update and see an expired-link message, start a new attempt.

The managed provider must be reachable and its service must accept the app's return URL. A real account login requires the account holder's interaction and has not been completed by the automated tests. This workspace uses a separate preview database, not the original customer database. Never use the disposable preview database for real customer data or purchases.

## Run a fresh copy

Install Python 3.11+, Node.js 20 with Corepack, and MongoDB 7/8. Start MongoDB locally, or provide a MongoDB URI in the backend environment.

```bash
# From the project root:
python -m pip install -r backend/requirements.txt
(cd frontend && corepack yarn install --frozen-lockfile --ignore-engines)
python scripts/init_env.py --preview
./scripts/run-preview.sh
```

Open `http://localhost:3000`. `init_env.py` creates a random `JWT_SECRET` and will **not overwrite** existing `.env` files. For an existing configuration, set `STORAGE_BACKEND=local`, `ENABLE_PREVIEW_LOGIN=true`, and `REACT_APP_ENABLE_PREVIEW_LOGIN=true` explicitly if an isolated preview is desired. Use a separate `DB_NAME` for it. Restart the backend and frontend after changing environment variables.

The frontend calls same-origin `/api`; its development proxy forwards requests to `API_PROXY_TARGET` (default `http://127.0.0.1:8001`). Set `REACT_APP_BACKEND_URL` only when the backend is intentionally hosted at a different public origin. Production deployments need a reverse proxy that serves the frontend and forwards `/api` to FastAPI.

The original exported requirements are retained as `backend/requirements.exported.txt` for reference. Use `backend/requirements.txt`: it points to the original pinned Emergent integration wheel on its own package index and avoids a conflicting duplicate `litellm` requirement.

## Enable the original services

Configure these in `backend/.env` or your deployment's secret manager; do not commit `.env` or paste secrets into public chat.

| Setting | Purpose |
|---|---|
| `MONGO_URL`, `DB_NAME` | Your actual MongoDB database. The export did not contain its data. |
| `JWT_SECRET` | Long random persistent secret used to encrypt saved BYOK keys. Back it up securely. |
| `EMERGENT_LLM_KEY` | Original hosted LLM, speech, and Emergent object storage. Takes precedence over a hosted direct OpenAI key. |
| `ALLOW_PREVIEW_HOSTED_AI` | Explicitly permit preview accounts to use hosted AI; defaults to false. Disable preview login for production. |
| `PREVIEW_HOSTED_DAILY_SHOW_LIMIT`, `PREVIEW_HOSTED_DAILY_VOICE_LIMIT` | Shared per-UTC-day attempt caps across all preview accounts; defaults are 5 and 10. These are not dollar-denominated limits. |
| `OPENAI_API_KEY` | Optional direct hosted OpenAI key for writing and speech when the Emergent key is absent. Users can instead add their own OpenAI key in Settings. |
| `ELEVENLABS_API_KEY` | Optional hosted ElevenLabs voices. Users may instead supply their own in Settings. |
| `STRIPE_API_KEY` | Original Stripe Checkout integration. Use a test key while testing. |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret. Unsigned webhooks are rejected; point Stripe to `/api/payments/webhook`. |
| `STORAGE_BACKEND` | `emergent` preserves the original object store; `local` stores generated media under `backend/local_storage`. Local files require backup and shared storage if using multiple servers. |
| `INTEGRATION_PROXY_URL`, `TTS_MODEL` | Optional overrides for the original integration proxy and voice model. |
| `CORS_ORIGINS` | Allowed browser origins for direct cross-origin API access. Same-origin proxying is recommended. |

Before production, set `ENABLE_PREVIEW_LOGIN=false`, `ALLOW_DEV_LOGIN=false`, `ALLOW_SOURCE_DOWNLOAD=false`, and `REACT_APP_ENABLE_PREVIEW_LOGIN=false`. Configure real authentication, database backups, HTTPS, a persistent secret, provider credentials, and a verified Stripe webhook. The original source describes Plus/VIP as 30-day one-time purchases, not auto-renewing subscriptions.

## Validation without spending money

```bash
# Requires the local MongoDB from above. Uses a temporary database and mocked paid providers.
python backend/scripts/verify_workspace.py
python backend/scripts/test_roast_showrunner.py       # turn plans, boundaries, pacing and bookends
python backend/scripts/test_reel_streaming.py          # real 30/60-limit local ffmpeg renders
python backend/scripts/test_reel_streaming.py --smoke --battle  # short winner-outro render

# Frontend production compile:
(cd frontend && CI=false GENERATE_SOURCEMAP=false NODE_OPTIONS=--max-old-space-size=512 corepack yarn build)

# Optional: with the preview running and Python Playwright + Chromium installed:
python scripts/test_google_login_ui.py             # provider and account mocked
python scripts/test_google_login_full_stack.py     # real API + temporary MongoDB, local provider stub
python scripts/test_persona_browser.py              # real preview API/Mongo; all voice requests mocked
python scripts/test_preview_navigation.py           # navigation and stripped-header transport
python scripts/test_responsive.py                   # phone/tablet/desktop, touch, audio and reel UI
python scripts/test_about_author.py                 # storybook, bundled audio, navigation and focus
python scripts/test_account_menu.py                 # menu, mocked history, help, routes and focus
python scripts/test_theater_display.py               # Studio, Battle, Share, mobile and replay
LIVE_GOOGLE_SMOKE=1 python scripts/test_google_login_ui.py  # also opens the real Google sign-in screen
```

The offline check covers managed-auth exchange, account-isolated favorites and private bounded account activity, both cached persona samples and concurrent-worker generation, preview limits, encrypted BYOK storage, personalized roast prompts and voiced bookends, mocked roast/battle generation, a real OpenAI-compatible client against a local HTTP stub, private and shared media, reel upgrade billing, failed-render refunds and concurrent retry requests, mocked checkout, and Stripe webhook verification/idempotence. The browser suites use a real preview API and database but intercept voice and generation requests, so they spend no provider balance. Responsive tests emulate viewports from 200 px through ultrawide desktop, including Pixel 7 touch, an embedded Google popup, photo choosers, forced autoplay restrictions and mocked reel downloads. They are not physical-device tests. The reel tests encode and fully decode local 1080×1920 H.264/AAC files for both limits with bundled audio and verify motion between keyframes; they do not call a paid service. Automated tests do not complete Google consent or prove that third-party credentials or the original Google/Stripe accounts are valid. Some original integration tests make live provider calls and can incur costs; review them before running.

## Preview binding

If the preview reports "port 3000 is bound to localhost — a server must listen on 0.0.0.0", the dev server was started without `HOST=0.0.0.0`. `frontend/.env` now sets `HOST=0.0.0.0` and `PORT=3000`, so `yarn start` binds all interfaces. Verify with:

```bash
ss -ltnp | grep :3000    # expect 0.0.0.0:3000, not 127.0.0.1:3000
```

Remove those two lines from `frontend/.env` if you want the dev server reachable only from the machine itself. The API is started with `--host 0.0.0.0 --port 8001`; MongoDB intentionally stays on `127.0.0.1:27017` because it should never be exposed publicly.


## Low-memory preview (used by this workspace)

The optimized React build can be served without keeping the webpack development
compiler in memory. This helps a 2 GB workspace handle a browser and the full-HD
video encoder at the same time. Keep MongoDB and the API running; **do not stop
or remove the database to rebuild the frontend**.

```bash
(cd frontend && NODE_OPTIONS=--max-old-space-size=768 CI=true corepack yarn build)
node scripts/serve-preview.cjs
```

This server binds `0.0.0.0:3000`, accepts the Arena preview host, serves SPA routes,
and proxies `/api` to `http://127.0.0.1:8001`. Set `PORT` or `API_PROXY_TARGET` to
override those defaults. Browser-facing requests remain same-origin. Unlike the
development server, source edits require another frontend build; building/replacing
frontend files does not touch the database or private generated media.

## 21+ writer and embedded reel update (7.2)

The live preview uses the requested single-call OpenRouter Claude/GPT pipeline with stronger 21+ creative direction, local quality checks and speech-cache fixes; see [21+ pipeline](ADULT_ROAST_PIPELINE.md) and [AI pipeline](AI_PIPELINE.md). Reload an already-open tab and explicitly accept the renewed 21+ disclaimer. Existing Windows source installations can close only their web launcher, leave MongoDB running, extract the update over the project and double-click `upgrade_21plus.bat` once. Existing `.env`, credentials, database and media are preserved, not replaced or deleted. Reels retain owner-scoped expiring native streaming/download links, a compatibility player and an explicit outside-preview fallback; see [Reels](REELS.md). Existing shows are not rewritten or recharged.
