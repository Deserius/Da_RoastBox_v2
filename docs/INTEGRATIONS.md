# Integration status and actual-origin checks

The active path is **GitHub → Render Free**, not an older Vercel deployment. Source code/configuration exists, but an environment variable or local mock is not live connectivity. See [Render setup](RENDER_DEPLOYMENT.md), [keys](ENVIRONMENT.md) and [readiness](RELEASE_READINESS.md).

## Existing managed Google

The working managed Google flow is retained. The frontend starts `https://demobackend.emergentagent.com/auth/v1/env/oauth` with an encoded same-origin `/auth-complete.html` callback, state and popup/redirect mode. The API exchanges the one-time ID at the managed provider, validates the response and creates a separate revocable local session; `/auth/callback` remains a legacy route. Explicitly unverified provider emails are rejected. If the provider omits the verification flag, this still relies on its identity assertion.

No invented Google client ID/secret is needed for this managed integration. It remains an external managed-service dependency; portability of the new HTTPS origin must be confirmed. Keep existing accounts/credits when linking, do not automatically merge ambiguous case-duplicate accounts, and do not ask again whether Google/Explore worked on the original preview: they did. That does not certify the new Render origin or a physical browser.

Popup-blocked/mobile redirect, canceled consent, logout, existing-account preservation and callback origin/state require actual-origin acceptance when authorized. Mock browser tests are not that acceptance.

## Genuine writer/speech

Both tiers use the approved OpenRouter Claude Sonnet 4.5 → GPT-4.1 → GPT-4o chain, then only configured approved provider backups. The source uses the supplied 40-persona catalog, separate Clean directions, explicit 21+ subjects, eight-stage writing directions and personalized photo/context/boundary inputs. Multimodal primary/eligible backups can receive guest photos; Studio/Battle disclose this. Provider retention/moderation policies remain external.

The UI records requested versus actually reported writer model and actual speech vendor/model. A provider that does not report the actual model is labeled unreported; old cached speech may lack metadata. Receipts are not independent quality ratings or proof of uncensored output.

OpenAI speech is real; optional entitled ElevenLabs/BYOK is real when configured. Premium-provider failure can remove the voice addon before charging the delivered standard result. It does not refund provider usage, unlock premium ownership or make inference free. First-time catalog samples synthesize only on explicit play and can bill; cached matches avoid regeneration. The previously authorized real generation is consumed and must not be repeated for this handoff.

## Private media

The Python Blob adapter uses an explicit approved read-write token/session outside Vercel, validates private store/host/access, and does not select ambient OIDC or another project. It never hands customer public-store URLs to the browser. Ownership/share-scoped API routes deliver images/audio/reels. Missing remote saves fail instead of pretending ephemeral cache is durable.

A small stable private write/read startup canary validates the selected store when actually deployed; none was run against a cloud store here. Migrate approved original bytes using [DATA_PRESERVATION.md](DATA_PRESERVATION.md), never regenerate them. Confirm Hobby personal/non-commercial eligibility and quotas rather than assuming TEST payments make a commercial app eligible.

## Stripe TEST

Only server-hosted, card-only, one-time TEST Checkout is supported in this handoff. A browser publishable key is unnecessary. Plus/VIP offers in the current source are one-time 30-day passes, not auto-renewing subscriptions. Historical unlock flags are retained where old purchases do not distinguish permanent bundles from past passes; do not automatically downgrade old users.

Configure this origin's TEST webhook signing secret and `/api/payments/webhook`. Session retrieval validates tracked ownership/product, cents/currency, payment and `livemode=false`; webhook signatures and settlement markers protect fulfillment. Returning to `/credits/success` alone grants nothing. Current request-level jobs/outage handling are not a production durability guarantee.

The already-authorized genuine 4242 TEST purchase and idempotent fulfillment were consumed earlier. Do not create a fresh checkout or regrant a missing snapshot record. No live key switch, refunds/chargebacks/tax/subscription system, app-store billing or commercial payment launch is authorized/proven by this source handoff.

## Optional email on Free Render

Keep disabled unless deliberately configured:

```dotenv
EMAIL_AUTH_ENABLED=true
EMAIL_TRANSPORT=resend
RESEND_API_KEY=
EMAIL_FROM=
```

The blank fields above need real server-private values and an appropriate verified sender/domain. Do not execute with placeholders. HTTPS delivery is used because Free Render blocks SMTP 25/465/587; existing native TLS-SMTP compatibility is not the Free deployment recipe.

Registration/recovery capability is reported truthfully and unconfigured controls are not shown as successful mail delivery. Already-verified email login capability is distinct from mail delivery. Verification/recovery links are short-lived/single-use; mailbox ownership is established before choosing a password; passwords are salted scrypt, not plaintext. Reset revokes sessions. Linking preserves an unambiguous existing account rather than granting a new balance.

Real sender/inbox/deliverability, trusted proxy/client-address behavior and account-linking acceptance remain external tests, not performed here. Do not invent an SMTP/Resend key or send real mail as part of the offline suite.

## Launch/UI assets

Bundled portraits, supplied branding, original generated instrumental/effects and illustrated/narrated developer story remain local source assets. Autoplay is browser-controlled: sound may require the user's gesture or audio-resume control. Lounge/sample/story/show/reel playback coordinates audio focus; physical audibility/volume and mobile/iframe policies are not certified by emulation.

Support/social links are optional real build-time destinations; absent values hide links rather than opening fake placeholders. The release source-download/development/session-tunnel controls are disabled on Render. Existing native iframe compatibility remains distinct.

## Safe tests

Use `python scripts/test_offline.py` and the fully intercepted `scripts/test_render_ui.py` with a local production build. They do not contact the original API or providers. Do not use historical real-QA scripts or old UI helpers that perform preview login/`route.fetch` against a running original server. Optional manual CI has no deployment, generation, email, cloud-canary or checkout step.
