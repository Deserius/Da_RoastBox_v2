# 21+ adult roast pipeline — 7.2

## Models and normal path

The user-confirmed chain remains **OpenRouter Claude Sonnet 4.5 → GPT-4.1 → GPT-4o**:

1. `anthropic/claude-sonnet-4.5`
2. `openai/gpt-4.1`
3. `openai/gpt-4o`

Both tiers use this chain. Existing configured Emergent/direct OpenAI providers
remain sequential backups, with separate credentials. No incompatible legacy
Nemotron/Venice endpoint pin is applied to Claude/GPT. Account budgets still apply:
these are paid models, even when local preview app credits are unlimited.

One successful request handles photos, original guest jokes and separate comic
lineup jokes together. There is no mandatory extra vision call, competing-writers
ensemble, paid critic or automatic reroll after every successful generation.

## Creative direction

`services/comedy_direction.py` versions the static direction as
`21plus-punchup-v1`. The duplicate writing instructions were consolidated: the
system prompt is 7,483 characters versus 11,550 previously (35.2% fewer characters;
this is not a measured model-specific token/cost/latency percentage).

- Select concrete, permitted evidence from each photo and the supplied anecdotes.
- Find a contradiction or absurd consequence, not a generic appearance insult.
- Make the joke pass the transplant test: would it work unchanged for anybody?
- Prefer a concrete unexpected payoff; put the hardest noun/verb at the end.
- Each show gets a locally varied joke-device plan attached to its existing
  balanced comic turn order. Devices include comparisons, false concessions,
  status reversals, mock ads/advice, comic misreadings and escalating consequences.
- Replies top the preceding comic; callbacks change a planted detail instead of
  simply repeating it. The final slot gets the strongest new payoff.
- Rewrite weak slots rather than deleting a third of the requested show.
- Distinct fictional character voices, short playable delivery notes, compact JSON
  and varied reaction metadata are preserved. The exact welcome, host lineup
  introductions, guest reveal, thanks and motto remain app-staged bookends.
- Source persona samples are limited to one short style reference per comic,
  never reusable punchlines. Clean mode omits adult samples entirely.

FIRE/INFERNO explicitly encourage cocky, audacious, disrespectful club comedy,
unbleeped profanity, non-graphic sex/relationship jokes, party/drug references
and clearly fictional dark-comedy comparisons. These tools should serve a real
punchline, not become a quota or a repetitive sex/drug gimmick. No automatic
wholesome compliment is appended to soften the original set.

The selected heat remains a ceiling. MILD/HOT stay lighter; Inferno still respects
the existing entitlement. **Clean mode and off-limits topics override everything**.
Adult mode does not permit protected-trait slurs, threats, doxxing, erotic/graphic
sex scenes, sexualizing minors/uncertain-age subjects, or invented factual claims
about the guest's health, private sexual behavior, drug use or criminal history.

## 21+ consent

The splash disclaimer, protected/share gates, footer, mature-language control,
page metadata and newly rendered reel branding now say **21+**. The tab-session
key changed to `roastbox_adult_consent_21_v2`; an older 18+ choice is not silently
converted. No authentication, saved drafts, customer data or existing show is
removed by this change.

The explicit checkbox covers the user's 21+ age and permission to submit
consenting real adults 21+. Both generation forms send
`adult_subjects_confirmed=true`. Adult-mode API requests without this explicit
attestation return 422 **before AI work or a show debit**; old open browser tabs
should reload and accept the new disclaimer. API clients must send the flag too.

This is **self-attestation, not verified age/identity or a compliance guarantee**.
If the writer detects material contradicting the required adult/consent context,
it returns a terminal content error. That error is not retried across models.
Have qualified counsel review age screening, terms, privacy and durable consent
requirements before a production launch.

## Reliability, latency and speech

- Local checks reject incomplete casts/sets, excessive exact repeats, extreme
  repeated openings, near-identical long jokes, stock boilerplate and overlong
  beats. Conservative clean/boundary phrase checks remain. These checks do not
  understand every paraphrase or prove that a joke is funny or safe.
- A quality failure gives the next configured writer a short reason, not a paid
  critique call or the discarded draft. A genuine token-limit failure can still
  trigger the existing bounded recovery request.
- `ROAST_WRITER_DEADLINE_S` defaults to **75 seconds across writer attempts**.
  This is a failure-time budget, not a promise of end-to-end show speed; speech,
  storage and network cleanup are separate. Provider requests already made may
  still be billed after local cancellation. Request-owned writer clients close.
- Early streamed TTS rejects obvious clean/boundary failures, unknown speakers,
  duplicate beats and excess provisional lines before spending on those clips.
- The voice cache now checks **before** a speech-provider call, rather than after
  paying for identical audio. Cache keys include provider, real voice settings,
  acting direction and a one-way credential scope. Different BYOK accounts/voices
  do not share cache entries. Missing/pruned local files produce a cache miss.
- Early/final voice reuse is keyed by speaker, text, acting direction and rap
  mode, not text alone. Two comics saying the same words keep distinct voices.
  Rap warmup uses rap acting from the start. Final stage metadata is not replaced
  by provisional streaming metadata.

No saved show, transcript, encoded reel or past purchase is rewritten/recharged.
New shows/renders use the update; playing/exporting an old show reuses its saved
content and speech.

## Windows update

Extract the entire updated source over the existing project, preserving `.env`,
`.data/mongo` and media. Close only its web-server launcher, **not MongoDB**, then
double-click **`upgrade_21plus.bat`** once. It prepares dependencies, explicitly
applies the requested non-secret Claude/GPT settings, builds the 21+ frontend,
starts API 8001/UI 3000 and opens the default browser after readiness checks.
Later launches use `start.bat` normally.

The upgrade preserves credentials, database/storage locations and unrelated
settings. It deliberately enables the selected paid model chain; it is not a
free-provider migration. No paid generation/payment call is made by setup itself.
The v1.2.1 project-local temp/cache and disk-space installer fix is retained.

## Verification

```sh
python backend/scripts/test_adult_roast_pipeline.py
python backend/scripts/test_multimodal_writer.py
python backend/scripts/test_lineup_roasts.py
python backend/scripts/test_roast_showrunner.py
python backend/scripts/verify_workspace.py
python scripts/test_21plus_ui.py
```

Provider, speech and generation calls are mocked in these regressions; the
workspace verifier uses a throwaway DB/media store and local provider stub.
Browser checks intercept generation, test desktop/mobile 21+ renewal and
multipart controls, and can target an isolated app with `ROASTBOX_TEST_ORIGIN`.
No paid live roast-quality or provider speed benchmark was performed. Humor is
subjective and output varies: the update improves direction/controls/efficiency,
not a guarantee of the funniest or most disrespectful result every time.
