# Browser and API route map

Current source: `backend/server.py` → `/api` routers, with built React mounted last. Browser routes do not replace API endpoints. Release disables public Swagger/OpenAPI, development login, source download and the native-only session dispatch tunnel. See [environment](ENVIRONMENT.md) and [Render setup](RENDER_DEPLOYMENT.md).

## Browser routes / assets

| Route | Function |
| --- | --- |
| `/` | Animated branding, explicit 21+ disclaimer/Enter, managed Google/Explore and available email controls |
| `/auth-complete.html` | Static managed OAuth popup/redirect callback with origin/state/mode checks |
| `/auth/callback` | Legacy React OAuth callback |
| `/auth/verify`, `/auth/reset` | Single-use email token/password UI; missing/expired links show errors |
| `/studio` | Hot Seat, Heat & Language/duration, Showtime, Pick Roasters; draft/consent/generation, history/replay/share/reels |
| `/roasters` | Persona browser, profiles, all three authored samples, favorites/search/filter/sort |
| `/battle` | Entitled classic/rap battle setup, heat, rounds, consenting subjects, fighter selection, theater/score/share/reels |
| `/credits` | Genuine server-created Stripe **TEST** Checkout offers; preview purchases disabled |
| `/credits/success`, `/credits/cancel` | Server-verified session status or canceled checkout; URL alone never grants credits |
| `/settings` | Safe configured/not-verified flags and encrypted BYOK save/clear |
| `/r/:shareId` | Revocable capability link, 21+ screen; beta password still applies |
| `/static/*`, `/assets/*`, portrait files | Built/bundled frontend assets, not customer storage |

Account menu adds navigation, profile/credit balance, payment/usage history, help, optional real support/social links, lounge audio, narrated About Developer and logout. Unconfigured external contacts are hidden, not fake links. There is no public release source-download button.

## API inventory (derived from current route decorators)

All routes below require the **extra beta gate cookie** except GET/HEAD health/readiness and the signed Stripe POST webhook. The gate is an outer boundary, not account authorization. Login/status/catalog routes may be public *within* that boundary; private records/media/payment status/BYOK require normal account ownership. Public share endpoints require a valid revocable share ID; catalog previews contain no customer content.

| Module | Method | Exact path | Handler |
| --- | --- | --- | --- |
| `server` | GET | `/api/` | `root` |
| `server` | GET | `/api/audio/{filename}` | `serve_audio` |
| `auth` | POST | `/api/auth/session` | `create_session` |
| `auth` | GET | `/api/auth/me` | `me` |
| `auth` | POST | `/api/auth/logout` | `logout` |
| `auth` | POST | `/api/auth/dev-login` | `dev_login` |
| `auth` | POST | `/api/auth/preview-login` | `preview_login` |
| `battle` | GET | `/api/battle/access` | `battle_access` |
| `battle` | POST | `/api/battle/generate` | `generate_battle` |
| `diagnostics` | GET | `/api/health` | `health` |
| `diagnostics` | GET | `/api/ready` | `ready` |
| `diagnostics` | GET | `/api/diagnostics` | `diagnostics` |
| `download` | GET | `/api/download/source.zip` | `download_source` |
| `email_auth` | GET | `/api/auth/email/status` | `status` |
| `email_auth` | POST | `/api/auth/email/register` | `register` |
| `email_auth` | POST | `/api/auth/email/verify` | `verify` |
| `email_auth` | POST | `/api/auth/email/login` | `login` |
| `email_auth` | POST | `/api/auth/email/forgot` | `forgot` |
| `email_auth` | POST | `/api/auth/email/reset` | `reset` |
| `payments` | GET | `/api/payments/packs` | `list_packs` |
| `payments` | GET | `/api/payments/activity` | `account_activity` |
| `payments` | POST | `/api/payments/checkout` | `create_checkout` |
| `payments` | GET | `/api/payments/status/{session_id}` | `payment_status` |
| `payments` | POST | `/api/payments/webhook` | `stripe_webhook` |
| `personas` | GET | `/api/personas` | `list_personas` |
| `personas` | GET | `/api/personas/favorites` | `list_favorites` |
| `personas` | PUT | `/api/personas/favorites/{persona_id}` | `add_favorite` |
| `personas` | DELETE | `/api/personas/favorites/{persona_id}` | `remove_favorite` |
| `personas` | GET | `/api/personas/{persona_id}/voice-preview` | `voice_preview` |
| `reels` | POST | `/api/roast/{roast_id}/reel` | `create_reel` |
| `reels` | GET | `/api/roast/{roast_id}/reels` | `roast_reels` |
| `reels` | GET | `/api/reels/{reel_id}` | `reel_status` |
| `reels` | GET,HEAD | `/api/reels/{reel_id}/video.mp4` | `reel_video` |
| `reels` | GET | `/api/media/subject/{roast_id}/{index}.jpg` | `subject_photo` |
| `roast` | GET | `/api/roast/cost-quote` | `cost_quote` |
| `roast` | POST | `/api/roast/generate` | `generate_roast` |
| `roast` | GET | `/api/roast/history` | `history` |
| `roast` | POST | `/api/roast/{roast_id}/share` | `share_roast` |
| `roast` | DELETE | `/api/roast/{roast_id}/share` | `unshare_roast` |
| `session_tunnel` | POST | `/api/session/dispatch` | `dispatch` |
| `share` | GET | `/api/share/{share_id}` | `get_shared` |
| `share` | GET | `/api/share/{share_id}/audio/{index}` | `shared_audio` |
| `share` | GET | `/api/share/{share_id}/images/{index}.jpg` | `shared_image` |
| `voice_settings` | POST | `/api/voice-settings/keys` | `update_keys` |
| `voice_settings` | DELETE | `/api/voice-settings/keys` | `clear_keys` |

The beta form itself is `GET/POST /_beta/access` (middleware, not an `/api` router). The verifier and separate signing key grant a short-lived HttpOnly/Secure gate cookie; account login and 21+ consent are still required where applicable. Gate credentials never belong in JavaScript.

## Important request/response contracts

### Roast generation — multipart, potentially billable

`POST /api/roast/generate` accepts:

- `persona_ids`: comma-separated selected catalog IDs, unique and within the server's allowed lineup size.
- Optional `subject_name`, `user_context`, `off_limits`, `comedy_styles` (JSON list).
- `duration_minutes` (default 3), `roast_tier`, `use_premium_voice`, `hd_export`, `heat`, `adult_language`.
- **`adult_subjects_confirmed=true`**, including Clean requests. Default false fails before AI/credit charging.
- `images`: actual JPEG/PNG/WebP uploads subject to byte/dimension/count validation, EXIF orientation and metadata stripping. No image means no fabricated appearance observations.

A successful response includes `roast_id`, accepted transcript/audio URLs, selected persona IDs, image routes, actual spending/remaining balance, fallback/free flags and generation metadata. Receipt fields distinguish `requested_model` from provider-reported actual model and per-beat `audio_vendor` / `audio_model`. A missing provider result is an error, not a catalog-joke success substitute. Lost responses must be checked in history before resubmission; full request idempotency is still a launch gate.

### Battle — multipart, potentially billable

`POST /api/battle/generate`: distinct `persona_a`/`persona_b`, rounds, `battle_style=classic|rap`, optional guest/context/off-limits/styles/photo, heat/language and explicit 21+ subjects. Battle access, persona entitlements and price are enforced server-side. Rap is spoken-word over a beat, not singing. Accepted responses include show/transcript/receipt and battle result. A mock scoreboard in UI tests does not prove real model judging quality.

### Reels and private media

Create via `POST /api/roast/{roast_id}/reel` with JSON `{"length":30,"regenerate":false}` or length 60; use the returned job ID rather than duplicate submissions. Owner status, prior-reel list and authenticated MP4 GET/HEAD/download routes are in the table. The UI fetches protected bytes and automatically saves a completed MP4. A pending/failed response is not a completed export. Photo/audio access is owner-scoped; revoked shares lose their dedicated media route access.

### Payments

`POST /api/payments/checkout` creates only tracked TEST Checkout for an eligible signed-in nonpreview account/product. `GET /api/payments/status/{session_id}` verifies the tracked owner and retrieves server-side Stripe state. `POST /api/payments/webhook` accepts Stripe-signed raw bodies up to 1 MB. It handles Checkout completion/eligible asynchronous-success fulfillment; unrelated events do not grant value. Amount/currency/product/owner/TEST checks and settlement markers prevent redirect/replay regrant. No live payment, checkout rerun or browser-supplied credit grant is authorized by this API reference.

### Auth, capabilities and errors

- Managed one-time session exchange: `/api/auth/session`; ordinary account `/me` and `/logout` are distinct from the extra gate.
- Email `/status` reports login/registration/recovery capability. Unconfigured mail does not produce fake registration/recovery success; anti-enumeration responses do not prove an email was delivered.
- `GET /api/diagnostics` in release returns authenticated safe flags/readiness only. Deep paid checks remain disabled even for an administrator unless explicitly reconfigured outside this task.
- `/api/health` is process/version, `/api/ready` Mongo only. Neither proves Google, Stripe, AI, Blob or app-store readiness.
- Typical errors: 401 missing/expired login; 403 entitlement/authorization/gate; 404 unknown/not-owned/release-disabled resource; 409 in-progress/history/ambiguous state; 422 consent/validation; provider/storage/network failures fail explicitly. Do not treat an error as permission to bypass ownership or reset data.

## Implementation entry points

`backend/routes/{auth,email_auth,personas,roast,battle,share,reels,payments,voice_settings,download,diagnostics,session_tunnel}.py`; orchestration/compiler/real provider/storage/media helpers under `backend/services/`; frontend request client `frontend/src/lib/api.js`. Public `REACT_APP_BACKEND_URL` is blank on Render so every API URL stays same-origin.

This inventory documents behavior; it is not instructions to rerun the consumed real AI generation or Stripe TEST purchase.
