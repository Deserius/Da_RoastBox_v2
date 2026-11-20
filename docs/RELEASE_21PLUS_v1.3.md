# Source update v1.3 — 21+ roast pipeline

Application version: **7.2.0**. The disk-space-safe installer remains **1.2.1**.

## Windows upgrade

1. Close only the old web-server launcher. **Leave MongoDB running.**
2. Extract the ZIP's `da_roastbox` contents over your existing project root. Do not create an unintended nested project. Do not delete `.env`, `.data/mongo`, accounts or media.
3. Double-click **`upgrade_21plus.bat`** once. It preserves keys and storage, explicitly configures the selected paid Claude/GPT chain, installs missing dependencies, builds the UI, starts API 8001/UI 3000 and opens your default browser after readiness checks.
4. Reload old browser tabs and accept the new 21+ disclaimer. Later launches use **`start.bat`**.

For a fresh project, the normal **`start.bat`** performs installation and startup. Bring your own provider credentials; none are included in this source release. Ordinary starts do not silently replace existing `.env` settings. If web servers are already running, the upgrade refuses configuration rather than stopping them or silently skipping migration. Never stop MongoDB or delete its data to fix the launcher.

## What changed

- Confirmed model order preserved: **Claude Sonnet 4.5 → GPT-4.1 → GPT-4o** via OpenRouter. Configured provider backups remain available within the writer deadline.
- Stronger personalized adult comedy direction, locally varied joke devices, surprising concrete payoffs, comic rebuttals and transformed callbacks. High heat welcomes profanity, drug references and non-graphic sex jokes; clean/heat/off-limits boundaries win.
- Compact versioned prompt, conservative local rejection checks and actionable fallback reasons. No compulsory extra vision, ensemble or critic call on the normal successful path.
- Explicit 21+ user/subject attestation in the UI, API and new records. Old 18+ agreement does not auto-accept the new version. This is self-attestation, not verified age or a legal compliance guarantee.
- Total writer-attempt deadline, terminal underage/nonconsent-context errors and request-owned client cleanup.
- Speech cache checked before paid synthesis and isolated by real voice/config/acting/credential scope. Early/final reuse preserves speaker and rap identity.
- Existing shows, reels, credits, credentials and database/media paths preserved. Previously saved shows are not rewritten or recharged.
- Existing v1.2.1 project-local temp/cache, pip no-cache and disk-space checks retained. Free space is still required.

## Validation and limitations

- 17 new offline adult-pipeline regressions passed, plus existing mocked multimodal, lineup and showrunner checks.
- Mocked workspace integration, deployment/auth/billing isolation and native reel-access regressions passed.
- 34 installer/launcher/storage regressions passed (16 one-click, 13 storage, 5 installation).
- Production frontend build passed with pinned Node 22.23.4/Yarn 1.22.22.
- Chromium checks passed at 1440×900 and 390×844 for renewed 21+ consent, adult/clean/heat multipart fields, roast/battle attestation and fresh-tab gating. Generation and voice calls were intercepted.
- Live preview health/diagnostics confirmed version 7.2.0 and the selected model order without deep paid probes. Private config bytes remained unchanged; the original MongoDB process stayed running.

Tests ran on Linux. **Native Windows execution has not been verified.** No paid live roast-quality or speed benchmark was run for this update. Provider/model availability, billing and output vary. The 75-second default writer-attempt budget is not an end-to-end show-speed promise; speech/storage/network cleanup may add time. Local checks do not guarantee funniness, safety or every paraphrased boundary. Upstream providers may bill attempted/canceled work, even when no RoastBox show credit is debited. Review output before sharing.

See [full pipeline details](ADULT_ROAST_PIPELINE.md), [model configuration](AI_PIPELINE.md), and [local installation](LOCAL_INSTALL.md).
