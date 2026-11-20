# Render environment and API-key reference

Use `deploy/render.env.example` as the blank-secret template and `render.yaml` for the beta's non-secret defaults. Values in this document are settings/descriptions, **not credentials**. Keep filled files private and out of Git/ZIP/Docker context. Helpers read only the explicitly selected dotenv file without ambient-variable interpolation.

## Required server-side settings

| Variable | Required value / purpose |
| --- | --- |
| `APP_ENV` | `beta`; enables release guards plus the additional password gate |
| `APP_BASE_URL` | Exact actual HTTPS origin, no path/query/fragment; absent on default Render domain can use `RENDER_EXTERNAL_URL` |
| `ALLOWED_HOSTS` | Exact assigned hostname(s), comma-separated; no scheme/path or wildcard `*` |
| `MONGO_URL` | Actual owner-approved remote TLS URI; `mongodb+srv://...` or certificate-verified `mongodb://...?tls=true`; never expose it |
| `DB_NAME` | Authoritative database name, preserved unless a rename was explicitly approved |
| `JWT_SECRET` | **Existing persistent secret**, at least 32 characters for release. Do not rotate: saved BYOK encryption depends on it |
| `DATA_IMPORT_CONFIRMED` | `true` **only after** authoritative record/media/history reconciliation; false refuses Render startup |
| `STORAGE_BACKEND` | `vercel_blob` for this Free blueprint; `local` is refused on Render |
| `BLOB_READ_WRITE_TOKEN` | Static read-write token of the specifically approved **private** store, backend only |
| `BETA_ACCESS_PASSWORD_HASH` | Existing scrypt verifier or owner-created verifier from `scripts/create_beta_gate.py`; no plaintext password |
| `BETA_ACCESS_SIGNING_KEY` | Separate persistent gate key, at least 32 characters, **not JWT_SECRET** |
| `OPENROUTER_API_KEY` | Genuine hosted primary writer access to the approved model chain |
| `OPENAI_API_KEY` | Genuine hosted OpenAI speech and configured direct-backup writing |
| `STRIPE_API_KEY` | Existing **TEST** secret/restricted TEST key; live keys refused |
| `STRIPE_WEBHOOK_SECRET` | TEST endpoint signing secret for **this Render URL**; not an API key or old URL's signing secret |
| `STRIPE_TEST_ONLY` | `true` throughout this handoff; beta rejects disabling it |

A variable being present is not a real connectivity/credit/billing/entitlement check. The preflight also validates the private Blob token/verifier formats without printing values.

## Approved writer settings — retain these

| Variable | This beta |
| --- | --- |
| `AI_DEFAULT_PROVIDER` | `openai` for speech/default integration; does **not** replace the explicit writer provider |
| `ROAST_WRITER_PROVIDER` | `openrouter` |
| `ROAST_WRITER_PROFILE` | `multimodal` |
| `ROAST_OPENROUTER_MODELS` | `anthropic/claude-sonnet-4.5,openai/gpt-4.1,openai/gpt-4o` — same order for both tiers |
| `ROAST_BACKUP_PROVIDERS` | `emergent,openai`; only actually configured backups can be used |
| `ROAST_FREE_WRITER_ONLY` | `false` |
| `ROAST_ALLOW_PAID_WRITER_FALLBACK` | `true` for the approved eligible backup path; provider usage is billable |
| `ROAST_SPEED_PROFILE` | `quality` |
| `ROAST_TTS_CONCURRENCY` | `4` in the Free blueprint, not the larger native quality-profile default |
| `REEL_ENCODER_PRESET` | `ultrafast`; the only preset with current constrained probe evidence |

No Nemotron/Venice/Pollinations/free-model substitution is required or silently enabled. Legacy compatibility variables remain in source for native history; they are not this deployment's approved chain.

Advanced timing/token controls in `backend/config.py` are optional and should remain at their supported defaults unless separately measured: `ROAST_WRITER_DEADLINE_S`, `ROAST_WRITER_TIMEOUT_S`, `ROAST_WRITER_RETRY`, `ROAST_VISION_TIMEOUT_S`, `ROAST_VISION_MAX_TOKENS`, `ROAST_WRITER_MAX_TOKENS`, `ROAST_WRITER_TOKENS_PER_BEAT`, `ROAST_WRITER_TOKEN_BASE`, `ROAST_WRITER_TRUNCATION_RETRY`, `ROAST_REASONING_EFFORT`, `ROAST_TTS_TIMEOUT_S`, `ROAST_STREAM_TTS`, `ROAST_TTS_CACHE`. Undersized budgets can truncate longer shows; “fast” labels are not speed proof.

`ROAST_OPENROUTER_PROVIDER_ONLY` and `ROAST_OPENROUTER_ALLOW_FALLBACKS` optionally restrict upstream **providers**, distinct from the approved model fallback list. Provider availability/moderation/data handling remains external. Do not promise uncensored output or silently alter the user's approved models to work around a refusal.

## Explore and safety defaults — set as a group

```dotenv
ENABLE_PREVIEW_LOGIN=true
ALLOW_PREVIEW_HOSTED_AI=true
PREVIEW_UNLIMITED_CREDITS=true
PREVIEW_HOSTED_DAILY_SHOW_LIMIT=-1
PREVIEW_HOSTED_DAILY_VOICE_LIMIT=-1
ALLOW_DEV_LOGIN=false
ALLOW_SOURCE_DOWNLOAD=false
ENABLE_PAID_DIAGNOSTICS=false
```

These remove app daily generation/voice-preview and credit blocking **for Explore accounts**, not provider quotas/billing, host limits, entitlement checks or normal-account credit prices. Preview is not a free-model substitute and cannot purchase. Unlimited settings do not reset real accounts to 25, recharge them or grant premium ownership. Keep the extra beta password and owner-side provider spending controls; no paid QA or checkout is triggered by the safe test runner.

## Optional genuine services

| Variable | When needed |
| --- | --- |
| `ELEVENLABS_API_KEY` | Optional hosted premium voices, or an entitled user's saved ElevenLabs BYOK. Without it, actual OpenAI fallback is reported and the premium voice addon is removed before debit when appropriate |
| `EMERGENT_LLM_KEY` | Only if using the existing configured gateway backup; preserve an existing correct value rather than inventing a replacement |
| `INTEGRATION_PROXY_URL` | Optional existing Emergent integration endpoint override; not needed for direct Stripe or the private Blob adapter |
| `TTS_MODEL` | Supported real OpenAI speech model; default `gpt-4o-mini-tts`, with reported `tts-1` fallback on failure |
| `VOICE_LEVELING_ENABLED` | Default `true`; local mastering, no paid generation |
| `VOICE_TARGET_RMS_DBFS` | Default `-19`, bounded to `-27…-16`; original media stays intact |
| `EMAIL_AUTH_ENABLED` | Default `false`; optional first-party email/password login alongside managed Google |
| `EMAIL_TRANSPORT` | `resend` for Render Free email; default native SMTP is unsuitable on blocked ports |
| `RESEND_API_KEY`, `EMAIL_FROM` | HTTPS Resend account/key and verified sender/domain when email delivery is deliberately enabled |
| `CORS_ORIGINS` | Normally empty for same-origin deployment. If needed, exact trusted origins only, never credentialed `*` |
| `DIAGNOSTICS_ADMIN_USER_IDS` | Optional explicit administrator IDs; does not override `ENABLE_PAID_DIAGNOSTICS=false` |

First-party email registration/recovery buttons follow actual server capability status; there is no fake successful email send when delivery is unconfigured. Existing verified email-login capability is separate from mail delivery. Sending real mail/origin checks is not certified here.

## Runtime-managed: do not normally enter these

| Variable | How set |
| --- | --- |
| `PORT` | Render; Docker start uses it with a local default of 10000 |
| `RENDER`, `RENDER_EXTERNAL_URL` | Render platform |
| `FRONTEND_BUILD_DIR` | Docker: `/app/frontend/build` |
| `TMPDIR` | Docker: `/app/backend/media_tmp`; disposable encode/spool work, not persistent media |
| `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, `MKL_NUM_THREADS` | Docker: `1`, to limit native thread/memory growth |
| `AUDIO_CACHE_DIR` | Optional ephemeral cache path; not authoritative remote storage |
| `LOCAL_STORAGE_DIR`, `PERSISTENT_STORAGE_CONFIRMED` | Only non-Free/local native storage arrangements; **not** this Free blueprint |

Do not turn off TLS/certificate checks. Do not use local Mongo, a public Blob store, local-only media or more than one Uvicorn worker to make a configuration pass.

## Public frontend build-time settings

These are **not secret** and require a rebuild after changes:

| Variable | Beta setting |
| --- | --- |
| `REACT_APP_BACKEND_URL` | Empty: same-origin `/api` |
| `REACT_APP_ENABLE_PREVIEW_LOGIN` | `true`, matching enabled backend Explore |
| `REACT_APP_SOURCE_DOWNLOAD_ENABLED` | `false` |
| `REACT_APP_ENABLE_SESSION_TUNNEL` | `false` on Render; preserves 401 instead of an iframe-only tunnel retry |
| `REACT_APP_SUPPORT_EMAIL` | Optional actual support address; absent hides the link |
| `REACT_APP_INSTAGRAM_URL`, `REACT_APP_FACEBOOK_URL`, `REACT_APP_TIKTOK_URL`, `REACT_APP_YOUTUBE_URL` | Optional actual HTTPS profile links; absent hides them |
| `GENERATE_SOURCEMAP` | Docker/CI: `false` |
| `CI`, `NODE_OPTIONS` | Build tooling, not provider credentials; Docker uses strict CI build and a bounded Node heap |

Never put Mongo URIs, JWT, beta keys, Stripe secret, Blob token, OpenRouter/OpenAI/ElevenLabs/Resend keys or an old server URL into `REACT_APP_*`.

## Not needed for this architecture

- `DATABASE_URL`, SQL/Postgres credentials, Supabase URL/service-role/anon keys: no Supabase/SQL backend is used.
- A separate Vercel deployment, Vercel account API token, `VERCEL_OIDC_TOKEN` or `BLOB_STORE_ID`: this outside-Vercel adapter explicitly uses the approved store's read-write token.
- Google OAuth client ID/secret in this app: the existing **managed** Google flow is retained. New-origin acceptance is still an external requirement, not proof that managed auth is vendor-independent.
- Browser Stripe publishable key/Stripe.js: server-hosted Checkout redirect is used. Do not add live keys.
- Paid Render disk/worker, Redis or a paid database as a prerequisite for this private Free beta. Durable production jobs remain a separate launch gate.
- `SMTP_*` for this Free deployment: outbound 25/465/587 are blocked. Native TLS-SMTP compatibility remains in code, but use configured HTTPS delivery or leave email off here.
- Ngrok account/token, unrelated cloud secrets, `ROASTBOX_BENCHMARK` (test-only), or arbitrary new API keys.

See [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md) for setup and [API.md](API.md) for routes. Do not request credential resubmission merely because the handoff intentionally excludes secrets.
