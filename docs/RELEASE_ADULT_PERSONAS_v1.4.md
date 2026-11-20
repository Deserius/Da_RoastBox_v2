# Source update v1.4 — maximum adult persona profiles

Application **7.3.0**. Persona/writer revision **`adult21-personas-max-v2`**.
Installer remains **1.2.1**, retaining the project-local temp/cache/disk-space fix.

## Included

- All **40 existing fictional adult personas** now have individually authored adult character mechanisms, target lenses, sexual/party-drug comparison worlds, profanity placement, rebuttal styles and separate clean-mode writing branches in the actual `backend/data/personas.json`.
- **120 new catalog sample jokes**, revised biographies/taglines/topics and original-character speech directions. No copied comedian routine or named-performer voice imitation instructions in the current writer/TTS briefs.
- Writer integration compiles only selected profiles; it is not just profile-card copy. High heat actively encourages raw profanity, non-graphic consensual adult sexual humor, drug references and personalized clowning, while avoiding a repeated dirty-keyword formula.
- Locally varied inspection lanes cover actual visible clothing/fit/prints, grooming, facial features, expression, pose and accessories. Missing/ambiguous/off-limits details are not invented. The hot-seat guest stays the main target when usable guest material exists.
- Fresh-show default: **adult ON + strongest unlocked heat**, INFERNO for Brutality+/Founder, otherwise FIRE. Existing deliberate Clean/lower-heat/off-limits choices remain authoritative, including tab drafts.
- Final/stream checks suppress obvious catalog-sample copying. Normal success still uses one multimodal writing call, with no new mandatory paid critic, vision pass or character-agent ensemble.
- Profile dialogs show a new **How they cook · 21+** section and all three samples. Opening profiles makes no paid voice call.
- Preview audio uses exact-text/configured-delivery versioning, preventing new text from playing stale v2 audio. Cached actual filenames are respected. A new sample is synthesized only on explicit first play; provider charges/availability apply.

IDs, names, portraits, ages, genders, tiers, actual voice assignments, speech rates/timing, favorite relationships, keys, MongoDB/storage settings and saved shows/reels are preserved. Existing media is not retroactively rewritten, regenerated or recharged.

## Windows upgrade

1. Close only the old web-server launcher. **Leave MongoDB running.**
2. Merge the ZIP's `da_roastbox` contents into the existing project root, without accidentally nesting a second project. Keep `.env`, `.data/mongo` and media.
3. Double-click **`upgrade_21plus.bat`** once. It preserves keys/data, explicitly configures the requested paid Claude Sonnet 4.5 → GPT-4.1 → GPT-4o chain, installs missing dependencies, builds and opens the ready app (API 8001/UI 3000).
4. Reload older tabs. Use **`start.bat`** on later sessions. A fresh installation can also start with `start.bat`.

Setup makes no paid generation/payment request. Existing manually selected Clean or lower heat settings are intentionally not wiped; move the heat slider up and enable Adult if you want to change such a saved choice.

## Validation

- **18 new offline persona tests** passed: all 40/120, actual profile-to-writer integration, separate clean branches, boundaries, source-copy rejection, single-call photos+script, actual route defaults, stream guards and preview version/cache behavior.
- **17 existing adult-pipeline tests** and the mocked multimodal/lineup/showrunner regressions passed.
- Full mocked workspace integration passed, including all three exact sample texts, concurrent preview caching, auth, credits, provider contracts and entitlement enforcement against a throwaway DB/local provider stub.
- **34 installer regressions** passed (16 one-click, 13 storage, 5 installation), plus deployment/auth/storage and native-reel access regressions.
- Production build passed with pinned Node 22.23.4/Yarn 1.22.22.
- Chromium: **1440×900 and 390×844**, both unlocked INFERNO and locked FIRE default cases passed, including three distinct profile dialogs, all three samples, consent/payload fields and preserved explicit Clean/Mild through reload and Battle. Existing desktop/mobile 21+ roast/battle attestation tests passed again. All generation/voice calls intercepted.

No paid live roast-quality or speed benchmark was performed. Tests ran on Linux; **native Windows execution remains unverified**. Humor, provider responses and output vary; these are stronger directions and controls, not a guarantee of the funniest/most disrespectful result every time. The 75-second writer budget is not an end-to-end show-speed promise. 21+ consent is self-attestation, not verified age. Review output before sharing.

See [adult persona schema/behavior](ADULT_PERSONAS.md), [full pipeline](ADULT_ROAST_PIPELINE.md), [roster](PERSONAS.md), and [local installation](LOCAL_INSTALL.md).
