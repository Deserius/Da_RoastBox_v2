# Da RoastBox — PRD

## Original Problem Statement
"Recreate this app just how it is and clone it (https://go-live-prep-10.preview.emergentagent.com) ... add 10 new premium personas and 5 new regular personas; make sure all API keys are working; app cleaned and modularized with documentation, tests and diagnostics; SaaS/production ready." Follow-ups: build all suggested enhancements (HD premium voices, Roast Battle, Persona showcase, shareable clips), more authentic joke writing with pauses/emotion, realistic perfectly-timed comedy-club crowd; finish HD social reel generator + 1v1; restore ORIGINAL uncensored LLM model & logic.

## Architecture
React + FastAPI + MongoDB. Script: ORIGINAL v5 head-writer prompt (verbatim) + performance addendum, Claude Sonnet 4.5 → GPT-4.1 → GPT-4o (Emergent key / BYOK). Voice: ElevenLabs v3 (if key) → gpt-4o-mini-tts with acting instructions → tts-1. Crowd: 14 fal.ai-generated club samples + Web Audio engine. Media in Emergent Object Storage. Reels: Pillow + ffmpeg (imageio-ffmpeg). Stripe Checkout. See /app/docs.

## Implemented
- 2026-11-03 v6: faithful clone, 40 personas (25 free / 15 premium), modularization, diagnostics, docs, Stripe SSL fix, atomic purchases
- 2026-11-03 v7:
  - Original uncensored prompt/model chain restored; beats now carry emotion, delivery, reaction, tag/crowd_work types
  - Expressive per-persona voice direction (gpt-4o-mini-tts instructions); ElevenLabs v3 emotion tags when key present
  - Crowd engine: room tone, intro cheer, layered randomized laughs, ooh/groan/cheer, laugh landing offsets, tags ride the laugh, ducking, outro applause
  - Roast Battle 1v1 (/battle): gated by unlock, 2-4 rounds, optional victim/photo, live scoreboard, winner reveal
  - Roasters showcase (/roasters) with bios, kill shots, cached voice previews
  - Public share links (/r/:id) for roasts & battles
  - HD Social Reel: 1080x1920 H.264/AAC MP4 with captions, avatars, voices + crowd mix; background render, refund on failure
  - Object storage for audio/subject photos/reels; 111 pytest passing; UI E2E verified (iteration_2)

## Backlog
- P1 Add ELEVENLABS_API_KEY for hosted HD voices (currently expressive OpenAI voices)
- P1 Set ALLOW_DEV_LOGIN / ALLOW_SOURCE_DOWNLOAD false before production
- P2 Battle history / leaderboard; reels for shared links; Stripe recurring subscriptions
- P3 Local-time daily free window
