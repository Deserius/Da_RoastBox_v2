# Current approved writing, speech and show pipeline

This document supersedes older free/Nemotron/Venice model suggestions. Both current tiers use the same approved OpenRouter model order; tier/voice entitlements and pricing are separate. Exact settings: [ENVIRONMENT.md](ENVIRONMENT.md). Offline checks are not a new genuine provider-quality certification.

## Inputs, consent and mode

Studio takes the selected fictional comics, optional guest name/context, actual guest photos, off-limits, comedy styles, duration, tier/voice/export options and heat/language. Battle adds two distinct fighters, rounds and classic/rap style. Request limits and entitlements are validated server-side.

Every show, **including Clean**, requires explicit consenting-21+ subject attestation. No-photo requests must not invent visual observations. Photo evidence can support jokes about actual visible fit/clothes/grooming/expression/props; context is user-supplied, not proven private fact. The multimodal writer/eligible backups may receive these inputs, as disclosed in the UI. Skip sensitive personal information and review before sharing.

Fresh defaults: Adult ON, INFERNO with the actual Brutality+/Founder entitlement, otherwise FIRE. Explicit Clean/lower heat, tab draft, boundaries and entitlements prevail. 21+ is attestation, not verified age or store permission.

## Exact persona source

`backend/data/personas.json` matches the supplied 192,714-byte 40-persona JSON exactly (SHA-256 `ac6b02daedfebbfb3870d43622c472a8fd0afa85d0db4bd8a8ec576ef785ac6d`). All 120 authored samples and the seven comedy fields are preserved alongside IDs/names/tiers/voice/other metadata. The older foundation catalog was intentionally replaced with that requested supplied file; customer shows/media were not rewritten.

`services/persona_direction.py` compiles only selected personas into bounded data. Adult uses the authoritative flat authored fields; obsolete structured fields cannot replace them. A short sample is a **style reference, never a replacement joke or guest fact**. Clean compiles its separate Clean source, not the adult lingo/samples/acting commands. The request-local speech metadata also uses separate Clean direction without mutating the master catalog.

## Eight-stage writing scaffold

`services/comedy_direction.py` supplies eight review/delivery sections for evidence, character-specific mechanisms, concrete angles, escalation, original punchline/tag/callback work, stage-ready spoken delivery, boundaries and final structured-output checks. The recovered source's current eight-stage implementation is tested as a scaffold; there is no claim of a byte-for-byte recovery of an unavailable older eight-section document or a complete historical native release.

The app asks for final structured JSON only, not visible planning/review. Speech avoids generic hype, repetitive catchphrases, copied supplied samples, false guest facts and a soft compliment replacing a strong payoff. Adult FIRE/INFERNO encourages the authorized original disrespectful/non-graphic adult style while boundaries and provider policies still apply. Off-limits pruning is conservative, not perfect semantic classification.

## Real approved provider chain

1. OpenRouter `anthropic/claude-sonnet-4.5`.
2. OpenRouter `openai/gpt-4.1` if the previous attempt fails/rejects the local output contract.
3. OpenRouter `openai/gpt-4o`.
4. Only configured approved Emergent/OpenAI provider backups, according to `ROAST_BACKUP_PROVIDERS`.

The writer remains OpenRouter primary even when `AI_DEFAULT_PROVIDER=openai` is used for speech. An unconfigured backup is skipped, not replaced by an unapproved model. Requests use the appropriate multimodal inputs and bounded deadlines/token budgets. Provider selection within OpenRouter is distinct from changing the model list.

Accepted generated output must satisfy schema, selected speaker IDs, speech/beat requirements and the complete original `lineup_roasts` map. Each selected comic gives **one first-person self-roast punchline about their own fictional name/gimmick**, separate from the core guest set; the app adds the name prefix. Missing/partial/duplicate/inappropriate lineup text fails rather than silently substituting static sample jokes. Early TTS is guarded against incomplete/invalid early lineup.

There is no guarantee of “never censored,” an objectively best result or success through a provider policy refusal. Failed/backup attempts may still consume real provider usage. Neither a local mock nor a receipt proves independent quality.

## Real speech and media provenance

`voice_orchestrator.py` / `speech_result.py` carry actual speech vendor/model through staging, cache and fallback. Standard uses genuine OpenAI speech (default expressive model, actual `tts-1` fallback when necessary). Optional entitled ElevenLabs/BYOK uses the persona mapping when configured. If premium delivery fails, fallback is reported and the voice addon is removed before first debit when appropriate; it is not disguised as premium success. Provider costs are not necessarily refunded.

Progressive writing/speech and bounded concurrency can reduce overlap latency, but this is not an ~90-second label or an SLA. Current Free configuration bounds TTS concurrency to 4. Local content-addressed mastering levels playback and mixes voice-first crowd effects; original clips remain unchanged. Cache identity includes actual voice/config/text/delivery/mode. Missing historical speech metadata is shown as missing rather than invented.

## Show assembly

`services/roast_writer.py` showrunner helpers construct the formal host/lineup/guest opening and closer around accepted core writing. The exact requested opening is retained:

> Welcome to Da RoastBox! Where we have a New Victim tonight that we are gonna hit with the flame thrower. Lets introduce the line up of your favorite comics that know how to cook and always bring that heat

The theater presents comics sequentially with large portraits/self-roast introductions, then the guest. Rap battles use spoken-word TTS over original instrumental timing, not singing. User/browser audio gestures and autoplay policy still apply.

## Storage, billing and history

Images/audio/reels must durably save to approved private storage in release mode. An unavailable save is not an ephemeral-success clip. Account/entitlement/pricing checks, staged billing and recovery markers preserve known one-time debit/refund paths; new normal users receive 25 and existing balances stay unchanged. Explore uses explicit unlimited app-preview settings, not fake inference or a reset of normal credits.

Historical shows/transcripts/voices are replayed from saved data, not regenerated when the persona catalog or renderer changes. Source migration copies existing bytes and records only under explicit owner scope. Sleeping Free hosting/current request-driven jobs do not provide end-to-end durable/idempotent production processing.

## Receipts and validation

Accepted shows persist provider, requested model, actual reported model when available, timing, prompt revision and reported usage, plus actual per-beat speech vendor/model. The UI does not infer an actual model from a requested one. Writing time excludes speech, storage, cold starts and other pipeline stages; it is not full-generation latency.

Use the guarded `scripts/test_offline.py` suite for contract regressions. The previously consumed genuine generation is historical, not current-Render proof and not authorization to rerun. See [RELEASE_READINESS.md](RELEASE_READINESS.md) for measured scope and external launch gates.
