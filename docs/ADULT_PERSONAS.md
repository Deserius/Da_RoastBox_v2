# Supplied adult persona catalog and maximum defaults — 7.4

## Authored copy and preserved identity

**`backend/data/personas.json` is the source of truth.** The user's seven supplied fields are merged exactly for all 40 IDs (`persona_1`–`persona_25`, `persona_p1`–`persona_p15`):

- `tagline`, `description`, `quirks_prompt`
- `lingo`, `punchlines` (three each, 120 total), `topics`
- `voice_direction`

Names/display names, IDs, portraits, ages, genders, free/premium tiers, voice assignments, speech rates/timing and all other protected non-comedy metadata remain unchanged. The portable SHA-256 contract in `backend/scripts/fixtures/usercut_persona_contract.json` verifies both the exact seven-field copy and the protected metadata of every record.

The revision is **`adult21-usercut-v3`**. A separate `clean_quirks_prompt` and refreshed `comedy_profile` provide Clean/Adult integration without altering the seven supplied fields. Raw supplied delivery text is preserved even where it references a performer. Only the effective writer/TTS instructions normalize those references into original-character direction; the app is not instructed to imitate or quote a real comedian.

## Actual writer and speech integration

`services/persona_direction.py::profile_brief` compiles only selected characters into bounded, JSON-encoded data. The new flat `quirks_prompt` is authoritative for Adult requests; an obsolete structured adult voice cannot override it. Adult briefs can include permitted topic/lingo choices and one short, locally varied sample explicitly marked **STYLE REFERENCE ONLY — NEVER COPY**. Samples are not guest facts or reusable jokes.

Clean briefs use **only `clean_quirks_prompt` or a separate clean-profile branch**. They never fall back to the adult description, quirks, topics, lingo or punchlines. Legacy/custom catalogs without a Clean source receive a neutral Clean fallback. Boundary pruning is conservative; it is not semantic classification.

Both generation routes also build request-local voice metadata with `voice_meta_for_mode`. Clean shows replace the effective acting direction with their separate Clean source, so adult commands such as “curse naturally” do not reach the OpenAI speech adapter. The master catalog remains unchanged. Actual voice IDs, speech rates and provider quality settings are retained; Clean/Adult acting has distinct scoped cache identities. Catalog sample playback remains explicitly 21+/Adult and is not a Clean demonstration.

A simplified schema (illustration, not replacement copy):

```json
{
  "quirks_prompt": "The user's exact Adult writing brief",
  "voice_direction": "The user's exact authored delivery",
  "clean_quirks_prompt": "Separately authored Clean mechanism and delivery",
  "comedy_profile": {
    "revision": "adult21-usercut-v3",
    "comic_engine": "Character-specific setup-to-reversal mechanism",
    "targets": ["permitted inspection lanes, not observations"],
    "rebuttal": "How this fictional comic tops another turn",
    "adult": {"voice": "Compatibility copy of the new Adult brief"},
    "clean": {"voice": "Separate Clean branch"}
  }
}
```

## Personalization and intensity

Locally varied inspection lanes cover actual visible clothing, fit, prints, grooming/hair, ordinary facial features/expression, pose, accessories and props, plus supplied anecdotes. **Lanes are not observations or quotas.** Missing, ambiguous, covered, sensitive or off-limits details must be skipped. No photos means no invented appearance. The hot-seat guest remains the main target when usable guest evidence exists; comic banter must return to it with a fresh angle.

FIRE/INFERNO direction encourages original, highly disrespectful adult clowning, unbleeped profanity, non-graphic sex/dating/stamina humor and absurd party/drug comparisons. It discourages repetitive dirty keywords, stock “you look like” formulas, discount/Wish filler, copied samples and an entire set built from one sex/drug joke. Sex/drug comparisons must read as theatrical exaggeration, not factual allegations about a guest. Protected-trait attacks, threats, private contacts, uncertain-age/minor sexualization, assault trivialization and invented health/crime/abuse/private-life claims remain prohibited.

Fresh shows default to **Adult ON + the strongest unlocked heat**: INFERNO with Brutality+/Founder, otherwise FIRE. Explicit Clean, lower heat and off-limits choices prevail, including deliberate tab drafts and shared Studio/Battle choices. Premium entitlements are not bypassed. Adult API work requires explicit `adult_subjects_confirmed=true` for the consenting 21+ context. This is attestation, not verified age.

## UI, samples and preservation

Profile dialogs show each mechanism, target lenses and all three samples. Opening a profile/help bubble makes no voice-generation request. A sample is synthesized only on explicit first play, subject to keys/provider billing; subsequent matching plays reuse its cache. Cache/lease identity includes exact sample text, delivery revision and real voice configuration. Changed text/delivery does not silently play an older sample by index.

Old preview files, customer shows/transcripts/audio, reels, favorites, accounts, credits and credentials are not deleted, rewritten or recharged. Local saved audio is not pruned merely because it is old. Changing the catalog affects new writing and newly requested samples, not old shows.

## Verification and updating

```sh
python backend/scripts/test_usercut_speed.py
python backend/scripts/test_adult_personas.py
python backend/scripts/test_adult_roast_pipeline.py
python backend/scripts/test_multimodal_writer.py
python backend/scripts/test_lineup_roasts.py
python backend/scripts/test_roast_showrunner.py
python backend/scripts/verify_workspace.py
ROASTBOX_TEST_ORIGIN=http://your-isolated-blank-key-preview python scripts/test_setup_help_ui.py
ROASTBOX_TEST_ORIGIN=http://your-isolated-preview python scripts/test_adult_personas_ui.py
```

Provider calls are mocked/intercepted in these tests. Clean word guards are conservative and can reject benign words/names; no test is a complete safety, originality or humor classifier. No paid live humor/speed benchmark or native Windows certification is claimed.

For an existing Windows installation, close only the web-server launcher, **leave MongoDB running**, merge the ZIP's `da_roastbox` contents into the existing root and run **`upgrade_21plus.bat`** once. Preserve `.env`, `.data/mongo` and media. Later starts use `start.bat`. See [release notes](RELEASE_HELP_USERCUT_v1.5.md), [pipeline](ADULT_ROAST_PIPELINE.md) and [local installation](LOCAL_INSTALL.md).
