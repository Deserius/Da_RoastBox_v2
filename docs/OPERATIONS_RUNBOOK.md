# Free beta operations and recovery

Current deployment target: one Free Render Docker web service; external TLS Mongo and private remote media. This is not an unattended production/live-payments runbook. See [setup](RENDER_DEPLOYMENT.md), [data preservation](DATA_PRESERVATION.md) and [readiness gates](RELEASE_READINESS.md).

## Keep these controls

- APP_ENV beta, separate beta password/signing key, existing JWT_SECRET, exact allowed host/origin.
- Genuine hosted approved writer/speech; no fake output or unapproved free-model substitution.
- STRIPE_TEST_ONLY true; server-only TEST keys; correct endpoint signing secret; deep paid diagnostics off.
- Unlimited Explore app preview settings as supplied; provider quotas/spending controls still matter. Normal balances/entitlements stay authoritative; new accounts only get 25.
- One Uvicorn worker/instance; ultrafast Free encoder; thread limits and private durable media. No paid disk, worker, tier upgrade or trial to hide a failure.
- Manual deploy/CI only. Do not run keepalive loops to defeat Free sleep, arbitrarily cycle ports, stop an existing MongoDB or replace data folders.

## Health without spending provider funds

`GET /api/health` returns process/version; `GET /api/ready` pings Mongo. They are deliberately exempt from the beta form so Render can use readiness. Neither calls writer, TTS, Stripe or Blob paid diagnostics. Settings reports booleans as **configured/not verified**.

A 503 readiness means Mongo failed; inspect private server logs, TLS URI, network allowlist and credentials locally. Do not paste secrets or turn off certificate validation. Startup can fail earlier on missing data confirmation, unsafe config, indexes or durable storage. Fix the cause; do not suppress a guard or initialize fresh user balances to force a green light.

No public Swagger/OpenAPI/source-download or development login is available in beta. A 401 is normal expired/missing account auth; the Render build intentionally does not retry via the iframe session tunnel. Reauthenticate rather than bypassing authorization.

## Interrupted generation

Generation is still request-driven, not an external durable job queue. If the response is lost, **do not immediately resubmit**: the provider might already have billed and the show might have completed. Refresh account state and check Studio → Recent shows. Request-level deduplication is not a production guarantee.

Staged generation billing/metadata and recovery markers avoid known double-debit/refund paths. Recovery runs only while this single process is awake. Provider charges can exist even if the app rejects/does not bill a failed result. Do not promise refunds of external AI usage or recreate a missing historical show.

## Reels

New H.264/AAC jobs are serialized through shared capacity. They have 120s leases and 20s heartbeats; stale claims use compare-and-set and one-time billing/refund markers. Recovery occurs at startup/periodically while awake, not while the service is asleep. A slow/pending job should be checked through its existing status/Check progress control before choosing Retry.

Video/status/photo routes remain owner-authorized; shared content uses revocable share-scoped routes. Completed video bytes are fetched with account authorization and the Download button creates an automatic local MP4 save in the standalone tested browser. Third-party iframe download restrictions and native/physical browsers still need their own acceptance.

Rendered files can be large: current synthetic ultrafast 60s-budget output was ~66 MB. Quota exhaustion is an availability gate, not permission to make private storage public, erase old customer media or start a paid plan. Existing rendered reels are not silently rewritten when the renderer changes. Default cache pruning preserves old audio.

Disposable `TMPDIR`/audio caches are not durable backups. Normal exception paths close temp files; crashed processes/containers may lose work. Do not indiscriminately delete temp/media paths on a running native installation.

## Stripe TEST only

The backend creates tracked card-only one-time Checkout sessions and uses integer cents. Redirect/query parameters do not grant credits. Settlement retrieves Stripe's session, verifies TEST mode/payment/amount/currency/owner/product, and uses per-operation markers so status polls/webhook replay do not regrant a paid purchase. A timed-out client should check the original session, not create another one.

Webhook endpoint: `POST /api/payments/webhook`, exempt only from the beta form and still signature-verified. Correct signing secret is endpoint-specific. Background reconciliation reads tracked pending TEST sessions while awake; it does not create checkouts.

The one genuine authorized 4242 TEST purchase is consumed. Do not create a new checkout, regrant it, fabricate a ledger or infer permission from its absence in an older snapshot. Never switch live, add refunds/chargebacks/subscriptions or launch live sales without separate review/authorization.

## Deploy/restart/cutover

1. Confirm authoritative data/media and encrypted keys; retain original JWT and backups. Complete the explicit owner-only preservation checklist.
2. Account for in-flight jobs; avoid old/new recovery workers acting on the same unfinished database records. Free supports one instance, not safe multi-worker distributed recovery.
3. Deploy manually; do not overwrite an old V3/V4 project or the native installation.
4. Verify exact origin/host, gate, read-only readiness and existing history/media. The first private-store startup check may consume storage operations; no writer/TTS/checkout probe is required.
5. If rollback is needed, preserve the newer database writes. Do not restore an older dump over a database that accepted new data; reconcile first. Keep the old app/data intact until owner acceptance.

## Backups, privacy and incidents

The app does not replace independent encrypted database/media backups, tested restore procedures, retention/account deletion, abuse reporting, monitoring/alerts or incident response. Source ZIP contains no customer backup or secret. Protect private logs/archives, use least-privilege credentials and provider controls, and avoid logging request bodies, raw credentials or guest photos.

Resetting an email password revokes account sessions; rotating JWT also breaks saved-key decryption and must not be used as a casual deployment fix. Gate password/key rotation should be deliberate; this handoff's helper never overwrites an existing gate file.

If resources/quotas/eligibility cannot be satisfied under the Free-only constraint, keep beta closed and report the specific gate. Do not silently spend money or pretend a mock proved it.
