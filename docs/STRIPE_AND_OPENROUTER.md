# Local OpenRouter and Stripe test setup

Your private configuration is `<project folder>/backend/.env` (on the supplied Windows path: `E:\Projects\da_roastbox_source_with_video_roasts_11.05.2026_v.1.1\da_roastbox\backend\.env`). Windows can hide dot-files. `backend/.env.example` is a template, not the private active configuration. The installer creates `.env` if missing and deliberately does not overwrite an existing one. Restart the launcher after edits. Do not send or publish this file.

## OpenRouter roast writing

The default is now a **single multimodal photo + joke-writing call** using the
app's OpenRouter key, in this order:

1. `anthropic/claude-sonnet-4.5`
2. `openai/gpt-4.1`
3. `openai/gpt-4o`

Only after that chain fails are the configured Emergent and direct OpenAI/BYOK
backups attempted. Voice synthesis remains a separate ElevenLabs/OpenAI layer.
For exact source functions, configuration, credential isolation and tests, see
[Current AI pipeline](AI_PIPELINE.md).

For existing `.env` files, run from the project root:

```bash
python backend/scripts/configure_writer.py --apply
```

The migration changes only writer settings, not your private keys, storage or
MongoDB configuration. Restart the backend on **8001**. Do not delete database
files. The live preview is already migrated.

These are **paid models**, including when preview app credits are unlimited.
Per-token ceilings of $3 input / $15 output per million tokens allow the requested
models; they are not total spending caps. Configure account/key budgets at each
provider. No paid live generation was triggered to test this change. Model IDs
and image support were checked using the public model catalog; model order,
failover and privacy were tested offline with provider mocks.

The older separate-observation `free` and `creative` profiles are opt-in legacy
paths, not the current default. Nemotron/Venice-only pins and reasoning overrides
are ignored in the requested multimodal profile. Leave pins empty for the new
chain. Streaming can start TTS while writing continues, but no fixed generation
speed or guaranteed comedy quality/refusal behavior is promised.

## Preview-mode limits

Preview accounts are throttled by three separate things, each switched off here:

- `PREVIEW_HOSTED_DAILY_SHOW_LIMIT` and `PREVIEW_HOSTED_DAILY_VOICE_LIMIT`: `-1` means unlimited (usage is still recorded in the `preview_hosted_usage` collection for visibility), `0` disables hosted preview AI entirely, and any positive number is a per-day cap shared by all preview accounts.
- `PREVIEW_UNLIMITED_CREDITS=true` bills preview shows at zero credits. It is deliberately *not* routed through the daily free roast, so the once-per-day allowance is left untouched and generation is not capped. Preview accounts cannot buy credits, so without this they run out.

These are cost controls on the hosted key, not a dollar spending cap: unlimited generation spends real money on whatever OpenAI/Emergent/OpenRouter key is configured, and the only remaining safety net is the budget you set with each provider. Keep them at their defaults for any deployment that bills real users, and leave `ALLOW_PREVIEW_HOSTED_AI` off outside a disposable demo. One concurrency guard stays in place by design: a single account can only run one generation job at a time.

## Legacy OpenRouter endpoint pins

`ROAST_OPENROUTER_PROVIDER_ONLY` and `ROAST_OPENROUTER_ALLOW_FALLBACKS` apply only
to the explicitly selected legacy `free`/`creative` writer profiles. Pins must
actually exist for that model/variant. Do not apply a Nemotron Venice pin to the
new Claude/GPT multimodal chain. The migration clears old pins.

## Stripe test payments

This code has Stripe Checkout and signed webhook handling, but it cannot be made live or verified without your own Stripe account and credentials. In the Stripe dashboard switch to **test mode**, obtain the test secret key, and add these to `backend/.env` (do not commit or share this file):

```
STRIPE_API_KEY=your_test_secret_key
STRIPE_WEBHOOK_SECRET=your_test_webhook_signing_secret
STRIPE_TEST_ONLY=true
APP_BASE_URL=http://127.0.0.1:3000
```

For local webhook forwarding, install the official Stripe CLI, sign in, and run `stripe listen --forward-to http://127.0.0.1:3000/api/payments/webhook`. Copy the CLI's `whsec_...` signing secret into `STRIPE_WEBHOOK_SECRET`, then restart the app. Leave the CLI running; a dashboard endpoint secret is different from the CLI listener secret. Use the actual launcher port/origin if changed. For remote deployment configure a public HTTPS webhook and use its matching signing secret and public origin. Use a verified app account: disposable preview accounts cannot purchase.

In Stripe-hosted Checkout, use the standard **16-digit** test number `4242 4242 4242 4242`, any future expiry, any three-digit CVC and a valid test postal code. Stripe test mode must be enabled for the key and no real money should be charged. Verify the success page, account entitlement, Stripe test event and signature-verified webhook. This setup has not been verified against a real Stripe account. See Stripe documentation for other required fields and current test-card behavior.
