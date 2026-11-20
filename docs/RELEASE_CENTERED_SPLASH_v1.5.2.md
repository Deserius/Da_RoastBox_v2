# v1.5.2 — half-width centered splash disclaimer

CSS-only visual follow-up to v1.5.1; backend API 7.4.0, consent/authentication logic, artwork and audio logic are unchanged.

## Requested layout

- Desktop disclaimer panel maximum width: **470 px**, exactly half the previous **940 px** maximum.
- Panel remains horizontally centered and bottom-docked, with the existing translucent glass surface.
- **Enter the Roast** is below the disclaimer, horizontally centered, at up to **240 px** wide. Very narrow screens constrain it to available space.
- Phones retain a readable responsive panel width rather than shrinking their already-small panel by half.
- Removed the previous landscape side-by-side button override so the button stays centered at every tested size.
- Text sizing, explicit 21+ subject/photo/Terms acceptance, disabled-until-accepted Enter, full-notice disclosure and protected direct-link gates remain unchanged.

At 1440 × 900 the new card measures **470 × 192 px**; at 390 × 844 it measures **366 × 200.2 px**. The narrower desktop card wraps naturally and puts Enter underneath instead of beside the notice.

## Validation

`test_compact_splash.py` now asserts panel and button centerlines match the viewport to within one pixel, desktop width is 470 px, the button is no wider than 240 px and sits below the disclaimer. Ten Chromium viewports (200 × 400 through 2560 × 1440) cover bounds, scrolling, touch/mouse/keyboard disclosure behavior, explicit checkbox accept/revoke, sign-in, sound controls and no horizontal overflow. Direct-route protection and the 30-second lobby welcome rotation are also checked. API traffic in these browser tests is intercepted; no real accounts, shows, payments, mail or paid provider calls are created.

The existing responsive/sign-in/email-dialog and original-sound suite remains applicable. Desktop layout is visually reviewed. These checks are local browser/touch emulation, not certification of every physical device.

## Updating an existing v1.5 / v1.5.1 install

No writer migration or settings change is needed for this visual patch. Merge the updated source while preserving `.env`, `.data`, saved shows and media; use `start.bat` to rebuild the changed frontend. If closing a running Windows instance, close only the web-server window with Ctrl+C and leave MongoDB running. Never delete `.data\mongo` or stop MongoDB. Installer v1.2.1 is unchanged.

The workspace live frontend is published assets-first/index-last with old hashed files retained. No MongoDB, API or existing frontend-process restart is needed. Source archives omit private configuration, databases, generated customer media, dependencies and local builds.

## Published result

The existing live app on port 3000 serves `main.7ae988ee.js` (unchanged JavaScript) and `main.5acee222.css`, byte-matched to the staged build. All 12 centered-splash/direct-gate/lobby checks and 11 existing responsive/audio checks passed against the published app. Panel and Enter button centerlines were verified within one pixel at all ten viewport sizes. Prior hashed assets are retained. Backend, installer, private configuration, consent/auth logic, artwork and audio code are unchanged; existing frontend/API/MongoDB processes were not restarted.
