# Mobile backend repair — verification, November 7, 2026

## Live verification completed

- One owner-authorized real roast, using the **3-minute preset**, an original fictional consenting adult aged 35, and the existing approved provider configuration.
- Submitted through the actual password-protected HTTPS app in an Android-sized Chromium browser (412 × 915), not through a mocked generation endpoint.
- Exactly one generation POST; HTTP 200; 15 transcript beats with audio; OpenAI speech; the first served clip was 144,657 bytes. No browser JavaScript errors.
- The photo-picker path successfully prepared an oversized valid JPEG greater than 9 MB before upload. Missing-roaster validation remained visible rather than disappearing into a toast.
- End-to-end request: **30.52 seconds**. Backend measurements: writer 23.825 seconds, remaining voice tail 6.440 seconds, total pipeline 30.265 seconds. This is one observation, not a speed guarantee.
- Unlimited preview charged **0 credits**, leaving the new QA account at its initial **25**.

## Real Stripe TEST payment

The isolated QA account used the normal app Buy button and genuine hosted Stripe Checkout. Exactly one checkout session and one payment submission were used. The supplied genuine TEST credential was retained privately.

- Stripe confirmed `livemode=false`, `payment_status=paid`, and session `status=complete`.
- Standard test card ending **4242**; **499 USD cents**, a $4.99 TEST payment. No live money was charged.
- Automatic return to the protected app succeeded; the real TEST confirmation appeared.
- **50 credits** added: **25 → 75** on the QA account only.
- Repeated owner-scoped status requests still reported 75. Exactly one purchase ledger entry and one applied-session marker exist.
- No fabricated paid status, fake card approval, or customer-account modification was used.

TEST polling/recovery is available when the return page closes. Signed-webhook handling remains guarded by its configured signing secret; no signing secret was fabricated. Configuration readiness alone is not a provider/payment certification.

## Signup and regression checks

New Google, developer, preview, and verified-email accounts explicitly receive **25 credits on creation**. The legacy model fallback is not a migration, and existing balances are not topped up or reset. Preview generation remains unlimited.

Passing suites:

- Full workspace integration (billing, idempotency, recovery, Clean, audio, persona samples).
- Verified-email authentication regression.
- Adult roast pipeline: 17 offline tests.
- Full-stack Google browser/API/MongoDB test with an explicitly stubbed identity provider: new account starts at 25; subsequent login preserves a fixture balance of 73; logout revokes the app session; embedded popup completion succeeds.
- Compact splash/layout suite through 2560 × 1440, direct-route full-consent gate, keyboard/Escape behavior, and lobby audio behavior.
- Frontend production build.

The Google fixture’s earlier failure was a stale descendant-only credit-label selector, followed by an auto-ending intro click race. Both test issues were corrected and the complete suite rerun successfully. These identity fixtures are not a new physical-phone or live-Google OAuth certification.

## Preservation and access audit

All records from the private pre-repair baseline still match their original documents, including **105 existing users**, historical roasts, reels, credit transactions, and existing sessions. Only the isolated new QA account was added. All **95 original media files** remain byte-for-byte unchanged.

Existing non-Stripe environment values are unchanged; the backend environment remains permission-restricted. The authored 40-persona catalog is byte-for-byte identical to the supplied export. The deliberate Stripe TEST credential/flag setup is the authorized environment change.

The additional-password gateway still protects HTML, API, and static access. Anonymous external root and API requests return 401 with no-store caching. Public compiled assets were scanned and do not contain the private configured credentials or gateway password. Normal app authentication and explicit 21+ consent remain required.

## Boundaries — do not overstate

- The workspace had already recovered an **older database snapshot**. Preserving the 105-account/95-media baseline does **not** recover later live-only records missing from that snapshot.
- The recovered source tree is not a certified full replacement for the historical v1.5.2 release. No older-tree replacement source ZIP was issued as part of this mobile verification.
- Native Windows behavior and physical Samsung roast generation were not tested here. The Windows installation and its Mongo data were not touched.
- Optional backup providers were not exercised with additional paid generations. The one authorized real roast has now been used; do not run another paid benchmark without permission.
- The private external link is a temporary Cloudflare tunnel, not permanent hosting. Its additional password and all credentials remain in restricted runtime files, not this document.

The API was restarted to load the repaired source. MongoDB was not stopped or deleted.
