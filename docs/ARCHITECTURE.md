# Architecture

```
backend/
├── server.py              # app factory: router mounting, CORS, audio serving, index creation
├── config.py              # ALL env reads (fail-fast for required vars, flags default off)
├── db.py                  # Motor client, collections, ensure_indexes()
├── models.py              # Pydantic models (User, Session, CreditTransaction, PaymentTransaction, RoastRecord)
├── auth_deps.py           # get_current_user (app header, Bearer token, or session cookie)
├── crypto_utils.py        # Fernet encryption for BYOK keys (derived from JWT_SECRET)
├── data/personas.json     # single source of truth for persona text, tier, portrait, voice config
├── routes/
│   ├── auth.py            # Emergent Google session exchange, /me, logout, dev-login (flagged)
│   ├── personas.py        # catalog, account favorites, per-sample voice cache + Mongo lease
│   ├── roast.py           # cost quote, generate (vision → beats → TTS), history, share
│   ├── battle.py          # 1v1 Roast Battle + crowd scoring
│   ├── share.py           # public share payloads
│   ├── reels.py           # HD reel jobs (background render, storage, status)
│   ├── payments.py        # Stripe checkout, status, webhook, entitlements and scoped recent activity
│   ├── voice_settings.py  # BYOK OpenAI / ElevenLabs keys
│   ├── diagnostics.py     # /health, /diagnostics
│   └── download.py        # source zip (flagged)
├── services/
│   ├── pricing.py         # PRODUCT_CATALOG, ROAST_COSTS, compute_roast_cost()
│   ├── roast_writer.py    # personalized ensemble prompt, randomized turn plan, dialogue repair, voiced bookends, parser
│   ├── roast_engine.py    # shared gating, image prep, credit ledger, persistence
│   ├── storage.py         # local or Emergent Object Storage (audio, subject photos, reels)
│   ├── highlight_reel.py  # streamed Pillow frames + ffmpeg mix/encode
│   ├── preview_budget.py  # atomic shared daily caps for optional hosted preview AI
│   ├── openai_service.py  # gateway client + expressive TTS (gpt-4o-mini-tts w/ acting instructions → tts-1)
│   ├── elevenlabs_service.py
│   └── voice_orchestrator.py  # ElevenLabs v3 [emotion] tags → OpenAI expressive fallback, parallel show synthesis
├── scripts/
│   ├── generate_persona_portraits.py  # fills any missing persona portrait via Gemini Nano Banana
│   ├── generate_crowd_sfx.py          # comedy-club crowd SFX library via fal.ai ElevenLabs SFX v2
│   └── diagnose.py
└── tests/                 # pytest API suites (_env.py resolves base URL)

frontend/src/
├── App.js                 # routes and app-level auth/favorites providers
├── lib/                   # api, AuthContext, PersonaFavoritesContext, authenticated media
├── components/            # PersonaBrowser, AccountMenu, AboutAuthor, theater and dialogs
├── data/authorStory.js    # chapter copy and bundled author-media paths
├── styles/                # shared responsive persona, account-menu, theater and author-book styles
└── pages/                 # Studio, Battle, Roasters, Settings, Credits, Share, auth
```

## Roast flow
1. Studio calls `GET /api/roast/cost-quote` live as options change.
2. `POST /api/roast/generate` (multipart): gating (premium persona / voice → 402) → cost / daily free check →
   images resized → build a balanced, randomized speaker plan and personalized prompt using the guest's supplied details, heat/language and optional boundaries → LLM writes structured beats.
3. Before TTS, deterministic local checks reject obviously malformed, very short or excessively repetitive scripts, unknown/missing cast, some clean-language words, and exact comma/semicolon-separated boundary phrases. They cannot understand every paraphrase, content boundary or joke; model compliance is not guaranteed. A rejected script incurs no RoastBox credit debit, but an AI provider may bill its model request. There is no additional critique/rewrite model call; the existing fallback applies to failed/refused provider calls. The server conservatively interleaves only explicitly standalone lines when it can safely break a long run without changing comic attribution or splitting a reply/tag. It adds a voiced cast/guest welcome and a deterministic thank-you/motto closer; the final quarter is marked for quicker handoffs. Review generated content.
4. Beats are synthesized in parallel (up to 24 concurrent, 20s timeout per beat); credits are debited only after all voices succeed, then the roast is saved. The welcome is merged into the first beat, while the spoken sign-off adds one TTS beat.
5. The browser stages an animated cast/hot-seat reveal, then plays each voice with crowd reactions. Rapid-fire jokes ride the laugh more quickly; the last punchline can breathe before the finale. Older saved shows keep their original audio.

## Persona discovery
Studio, Battle, and Roasters use one shared card browser and profile dialog. Favorites are account-scoped `users.favorite_persona_ids`, loaded by a shared frontend provider and changed with idempotent authenticated endpoints. A profile plays either punchline on demand. Sample zero retains the original voice-preview cache; other samples have separate `(persona_id, sample)` records. Cached audio is reused, while uncached generation requires a session, available provider credentials and, for hosted preview accounts, a remaining daily voice allowance. Mongo leases serialize same-sample generation across workers. Deployments with multiple API servers must also share the backing media storage.

## About Developer
Only the signed-in hamburger/account menu opens the Radix dialog without navigating or resetting the underlying app. Ten chapter records and static WebP/MP3 assets are served by the frontend; chapter changes clean up the previous `Audio` instance. Playback, pause, replay, volume, optional auto-advance and a readable-text fallback require no runtime TTS or image-generation calls. Sentence highlighting is an approximate progress-based aid, not word-level forced alignment.

## Account menu and recent activity
The top-right Radix drawer retains the existing routes and logout and shows the authenticated `/auth/me` profile, plan and balance. Its payment and usage panels share an on-demand request to `GET /api/payments/activity`, with loading, empty and retry states. The backend scopes each Mongo query to the authenticated user, explicitly projects only display fields, limits each of payments, credit events and shows to the latest 20, and returns `Cache-Control: private, no-store`. It never exposes provider session IDs, user IDs, transcripts, personal context or photos through this endpoint. The existing ledger does not record every refund; the current profile balance is authoritative. Closing the drawer clears cached history. Help is available without a configured contact, and the optional public `REACT_APP_SUPPORT_EMAIL` enables a mail link. Social links are labeled generic platform-homepage placeholders, not claimed as official profiles.

## Payments
The catalog and prices are server-authoritative. A paid checkout's entitlement and a per-session marker are written atomically to the user document. A deterministic ledger entry and the final paid status follow and can safely be retried after interruption; duplicate status polls and webhooks do not double-grant. Concurrent pass extensions use optimistic checks against the previous tier and expiry. New pass privileges are derived from the active tier instead of setting permanent bundle flags. Existing paid transactions and unlock flags remain unchanged for compatibility; audit historical purchases before migration. New reel debits/refunds similarly use per-job atomic markers and deterministic ledger records, with pending refund recovery on restart. Roast/battle results are staged before the atomic debit marker; interrupted ledger/publication writes are reconciled on restart or after a short delay. This is not a multi-document transaction or a durable queue, and a newly resubmitted request after a lost response can create another charge. Reels still require one worker; add end-to-end request idempotency, reconcile historical transactions, and test real Stripe fulfillment before live payments.

## Collections
`users`, `sessions`, `roasts`, `credit_transactions`, `payment_transactions`, `voice_previews`, `voice_preview_samples`, `voice_preview_leases`, `preview_usage`, and `reels` store account, generation, cache and quota state. Indexes are created on startup; leases use TTL expiration for crash recovery.

## Comedy timing & crowd engine
Each beat carries `type` (incl. `tag`, `crowd_work`), `emotion`, `delivery`, `laugh_after`, `reaction`, pauses.
- **Voice:** `acting_instructions()` combines the persona's `voice_direction` with the beat's emotion + delivery note
  and sends it to `gpt-4o-mini-tts` (or ElevenLabs v3 audio tags when a key is available).
- **Crowd (browser, `lib/crowdEngine.js`):** Web Audio room-tone bed, intro cheer and 14 generated crowd samples with random variation/pitch/pan, layered banks (e.g. big = big laugh + medium layer), and `ooh`/`groan`/`cheer` reactions. Laughs land 90-320 ms after the punch; tags and rapid-fire handoffs ride the laugh. A slightly softer shared crowd bus is reduced to 8% during speech with a 60 ms attack and 240 ms release; it also covers delayed/newly scheduled reactions. The finale gets applause plus a local synthesized stinger.
- **Reel (server, `highlight_reel.py`):** chooses complete highlights within the requested 30/60-second maximum, streams animated scene/caption keyframes to temporary files, and uses ffmpeg for continuous camera motion, voice/crowd mixing and H.264/AAC encoding. A matching envelope ducks the mixed crowd bus during each voice interval and smoothly restores it afterward. It does not retain every full-HD frame in Python memory or make new AI calls. Current-style exports are cached; a completed legacy export can be upgraded at the same length without another charge.
- **Responsive/audio recovery:** Studio steps are jump links, small screens can expand the roster, photo inputs use native accessible labels, and layouts constrain grids and dialogs to their viewport. A blocked browser audio play waits for a gesture and reuses the loaded clip, with a captions-only theater fallback.

### Photo-grounded joke planning and performance
The roast/battle writer sends normalized, metadata-stripped images in upload order with high-detail multimodal input. The single existing script-generation request instructs the model to privately rank clear, permitted visual choices, connect them to supplied context where supported, brainstorm varied angles, and edit for character, timing and boundaries before returning only the script. No separate vision or critique request is made; provider model fallback on failure can still incur additional requests. Photo indices in beats are model-supplied, not independently verified. Ambiguous images and multiple people may produce less-specific jokes. The model is instructed not to infer sensitive traits or private facts, but model output and exact-phrase boundary checks cannot guarantee compliance, grounding or comic quality. Obvious repeated templates can cause local rejection before TTS or RoastBox credit charging; the AI provider may still bill the writer request.

Performance metadata controls emotion and inter-beat pauses; OpenAI expressive TTS receives persona and per-beat acting notes, while ElevenLabs uses its supported emotion tags. The fallback TTS may not follow acting directions. Actual comedic pauses inside a spoken line and loudness vary by voice/provider. No real-person impersonation is requested.
