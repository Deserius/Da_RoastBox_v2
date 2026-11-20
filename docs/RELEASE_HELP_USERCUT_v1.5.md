# Source update v1.5 — useful help, supplied comedy and generation efficiency

Application **7.4.0** · persona/writer revision **`adult21-usercut-v3`** · installer **1.2.1**.

## Delivered changes

- **Removed Comedy Styles checkboxes** from Studio and Battle, their request fields and hidden saved-style influence. Old style drafts are explicitly retired; old shows/legacy API compatibility remain intact.
- **Useful compact info icons throughout** setup, heat/duration, costs/entitlements, roster tools, profiles/samples, Settings/keys, products, consent/email/password forms, share/reels and theater mixing. Hover/focus/tap/keyboard support; Escape/outside/Close dismissal; no accidental toggle, upload or form action. Help stays within phone/modal bounds; Escape closes help before the modal behind it.
- **Exact seven-field merge for all 40 personas/120 samples.** Names, IDs, voices, speech settings, portraits, tiers and protected metadata preserved by a portable SHA-256 contract. The supplied writer replacements are compatibility-merged, not claimed as a byte-identical file replacement.
- **Original, personalized adult-club direction:** ranked photo evidence, multiple angles, varied engines, earned profanity, final-word surprises, listening/rebuttals/transformed callbacks and weakest-third rewrites in place. No shortened requested core set; numbered multimodal Roast plans enforce exact count/speaker order. Separate 10–26-word host lineup roasts, six-word model acting notes and bounded pauses.
- **Clean isolation at both writing and TTS:** separate Clean briefs/effective acting; authored raw fields remain unchanged. Adult defaults remain ON + strongest unlocked heat, with explicit Clean/lower-heat/off-limits and all entitlements preserved.
- **Actual avoidable-work reductions:** dedicated writer IO, script-first streaming, overlap/reuse of four required bookends, credential-scoped ElevenLabs client pooling/account backoff/one fresh-key probe, and scoped concurrent speech singleflight/cache-before-provider lookup. Healthy models/voice quality, full set counts and existing backups retained. Empty audio rejected; canceled work reaped; old local show audio never removed solely for age.
- **Actual elapsed clock and per-response timing**, not a countdown or invented SLA. Writer, additional voice tail and total script+voice times are separately labeled. No past records rewritten.

No saved shows, media, accounts, credentials, billing entitlements or reels are intentionally deleted, rewritten, regenerated or recharged by the update. Native private reel streaming/download and installer disk-space safeguards remain intact.

## Validation performed

- **31 offline supplied-copy/efficiency regressions:** all 40 exact seven-field and protected-metadata hashes; Clean writer/TTS source and actual adapter checks for all 40; exact turns, six-word notes, 10–26-word lineup jokes, pauses, streaming order, writer executor isolation, required-bookend reuse, account isolation/backoff, singleflight/cache/cancellation/empty output and local audio preservation.
- **17 adult-pipeline + 18 persona regressions**, plus multimodal/lineup/showrunner/optional legacy writer, preview-policy and rap regressions. Providers mocked; no paid generation.
- **34 installer regressions:** 5 installation + 16 one-click + 13 storage. Linux execution; not native Windows certification.
- Full isolated workspace, email-auth, deployment, native-reel access and reel reliability checks with mocked providers/SMTP/Stripe and temporary DB/media, cleaned afterward.
- **43 static legacy persona-data checks** only; live-provider portions of the legacy suites were not run.
- Real offline FFmpeg voice leveling/mix checks and a synthetic 30-second-limit reel smoke render: valid H.264/AAC 1080×1920 MP4, whole-line selection and motion; no customer media used.
- Production frontend build with pinned Node **22.23.4**, Yarn **1.22.22**, CI lint and a bounded heap.
- Chromium **1440×900 desktop + 390×844 touch**: 40+ help checks each, keyboard/hover/tap/Escape/outside/Close, nested email/profile/reel/theater help, no unintended actions, actual elapsed clock, fixture timing-response mapping and no retired styles in either generator payload.
- Independent, equal desktop left/right panes and scrolling at **1920×1080, 1440×900, 1280×800, 1024×768**, plus mobile fallback.
- Layout matrix **200, 240, 280, 320, 412, 568, 768, 844, 1024, 1440 and 2560 pixels wide** across Studio/Roasters/Battle/Credits/Settings: no horizontal overflow.
- Four strongest-default profile cases (desktop/mobile × unlocked INFERNO/locked FIRE) and two desktop/mobile explicit 21+ consent cases; saved Clean/Mild survives reload/navigation. All generation/voice calls intercepted.

## Live workspace publication

The tested frontend was atomically published assets-first/index-last, retaining older hashed assets for already-open tabs. API **7.4.0** and all 40 v3 catalog entries pass shallow health/config/Mongo checks. Published-build desktop/mobile smoke checks intercepted all auth/API calls and made no real data writes. The protected MongoDB and existing frontend processes were left running; only the API was selectively restarted after generation/voice leases, reel/refund jobs and pending settlements were clear.

Post-publication verification found **30 existing show/reel records and 1,055 existing media files hash-identical**, with both private environment files unchanged. This preservation check is not an off-site database/media backup or a live-provider benchmark. Reload old tabs to replace their cached controls with the new UI.

## Production qualification — not an absolute guarantee

No paid-provider latency/humor benchmark was run, so this release does **not** claim an X-second show or measured real-provider speedup. The 75-second writer budget is not full-show completion time. Output and provider availability vary; local guards are not semantic safety, plagiarism or humor certification and can false-positive ordinary words/names.

Native Windows execution, physical-device behavior, live Google/SMTP deliverability and real Stripe TEST 4242 checkout were not certified in this refresh. Mock integration checks are not those real-service results. Review credentials, webhook/public URLs, provider budgets, backups, monitoring, privacy/consent/legal requirements and real-service smoke checks before a public production launch. A 21+ checkbox is self-attestation, not verified age. Browser autoplay/embedded-download restrictions can still require a user gesture or outside-preview playback.

## Windows installation / upgrade

1. Close **only the old web-server launcher**. **Do not stop MongoDB or delete `.data\\mongo`.**
2. Merge the ZIP's `da_roastbox` contents into your existing `da_roastbox` root; avoid a second nested project. Keep `backend\\.env`, database and media. No private keys/database/customer media are included in the source archive.
3. Existing project: double-click **`upgrade_21plus.bat`** once. It preserves credentials/data, explicitly applies the confirmed paid Claude/GPT chain, installs missing dependencies, builds and opens the ready app (API **8001**, UI **3000**).
4. Reload old browser tabs. Use **`start.bat`** for later launches; fresh installs can also use `start.bat`. Existing deliberate Clean/lower heat is not wiped.

See [pipeline](ADULT_ROAST_PIPELINE.md), [persona source](ADULT_PERSONAS.md), [AI configuration](AI_PIPELINE.md), [reels](REELS.md) and [installation](LOCAL_INSTALL.md).
