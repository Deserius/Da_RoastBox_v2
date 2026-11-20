# v1.5.1 — compact, translucent original splash disclaimer

Frontend-only follow-up to v1.5. The backend remains API 7.4.0 / `adult21-usercut-v3`; the writer, personas, access rules, payments, media and installer are unchanged.

## Visual changes

- A short, bottom-docked frosted-glass panel replaces the two opaque nested boxes and redundant headings.
- The original background artwork is retained. Its dark overlay is lighter, revealing more of the logo and character.
- Brief content warning, explicit 21+ checkbox and Enter button remain visible in the default panel.
- **Full notice** opens an accessible native disclosure containing the original full disclaimer and explanation of self-attestation. Tap/click or Enter toggles it; Escape closes it and restores focus. Opening the notice never accepts consent.
- Desktop places Enter alongside the notice; phones stack it below. Sound moves to the top corner when the wider footer would overlap it.

Measured in Chromium with the same viewport and original artwork:

| Viewport | Previous panel height | New panel height | Reduction |
| --- | ---: | ---: | ---: |
| Desktop, 1440 × 900 | 316.5 px | 120.5 px | 61.9% |
| Phone, 390 × 844 | 360.0 px | 200.2 px | 44.4% |

The previous phone panel also required internal scrolling to reach all content. The new default panel does not at the tested common sizes. Expanding the optional full notice can intentionally increase height and enable scrolling on short/narrow screens.

## Safeguards retained

Consent is still an explicit, reversible checkbox choice. It confirms the visitor is 21+, real subjects are 21+ and consent, photo permission is held, and the disclaimer and Terms of Use are accepted. **Enter stays disabled until acceptance.** The existing tab-session consent key and sign-in handoff are unchanged. Self-attestation is not verified age or legal clearance.

Protected/direct links retain the complete, always-visible disclaimer and do not mount protected content before consent. Intro animation, sound playback logic, lobby welcome rotation, authentication and backend code are unchanged.

## Validation

- Production build succeeded in a separate staging directory with source maps disabled.
- `scripts/test_compact_splash.py`: ten viewports from 200 × 400 to 2560 × 1440; default bounds/no horizontal overflow, transparent inner surface, sound control clear of the panel and functional, full notice by touch/mouse/keyboard/Escape, no accidental consent, checkbox accept/revoke, disabled Enter and sign-in handoff. Direct-link full-disclaimer protection and the original looping beat / 30-second welcome rotation also passed.
- Existing `scripts/test_splash_responsive.py`: ten sizes, consent → centered sign-in → email dialog/Escape, plus original intro-sound handoff passed.
- These browser checks intercept API traffic: no real accounts, shows, payments, mail or paid AI/voice requests are created.
- Desktop and phone screenshots were visually reviewed. This is local Chromium/touch-emulation validation, not certification of every physical browser/device.

The UI is published assets first and index last, retaining previously published hashed assets for open tabs. Neither the API process nor MongoDB needs a restart for this patch.

## Existing Windows installation

If already on v1.5/API 7.4, no writer migration or configuration change is needed. Close only the web-server window with Ctrl+C, leave MongoDB running, merge this updated source into the existing project without removing `.env`, `.data`, saved shows or media, then run `start.bat` to rebuild the changed frontend. Never delete `.data\mongo` or stop MongoDB. Installer v1.2.1 is retained.

If upgrading from an earlier release, also follow the v1.5 upgrade instructions in the README. The source ZIP excludes private environment files, databases, generated customer media and machine-local dependencies/builds.

## Published verification

The live frontend on port 3000 now serves `main.7ae988ee.js` and `main.b4895b74.css`, byte-verified against the final staged build. Both browser suites were rerun against that published app: 12 compact-splash/direct-gate/lobby checks and the 11 existing responsive/audio checks passed. No real API writes or paid requests were made by these checks. All 140 previously packaged backend/installer files, original artwork, audio logic and consent-context code were byte-compared with v1.5; protected environment baselines matched. MongoDB, the API and the existing frontend process were not restarted. Old hashed assets remain available for open tabs.
