# Preserve authoritative data before changing hosting

## Stop conditions

This is an **owner-controlled procedure**, not permission for an agent to export/upload private records, create resources, reset balances, restore over a database or repeat paid QA. Migration helpers have been tested with local fixtures/plans only; **no real transfer was performed**.

The recovered workspace is not guaranteed to contain the richest/current native data. It predates some already-consumed real QA. Identify the **actual authoritative** installation/database and media store first. Keep the richer native installation (including installer 1.2.1) and original env. Do not copy an older recovered database over it. Do not infer a missing purchase is unpaid, invent history or create compensating credits.

Native owner path previously supplied: `E:\Projects\Da_RoastBox_11.06.26_v.1.2\da_roastbox`; private env `backend\.env`. Paths below are examples for a separately extracted clean source folder; substitute actual owner-approved locations privately.

## What must survive

- All users and their existing credits, tiers, permanent unlocks, pass expirations and favorites.
- Sessions, email credentials/tokens, purchases, settlement/idempotency markers and credit ledgers.
- Original roast/battle records, transcripts, writer/voice provenance, shares and reel metadata.
- Generated photos, voice files (including legacy audio cache), reels and any authoritative remote objects.
- **The same `JWT_SECRET`** and encrypted BYOK fields. JWT is also the encryption-key derivation input; do not generate a new one during hosting migration.
- Existing provider credentials, application ownership and privately retained QA receipts.

A source archive is **not a database/media backup**. Its intentional absence of customer data is not a fresh-start instruction. Normal new accounts receive 25 only; no startup migration recharges existing users.

## 1. Establish a consistent source

1. Select the authoritative source and explicitly approve destination account/store/database.
2. Pause **application writes** under the owner's control, including other workers/deployments using that database. Finish or account for in-flight generation/payment jobs.
3. **Do not stop MongoDB. Do not delete or replace `.data/mongo`.** A consistent standalone dump needs writes paused, not the database stopped. The helper does not enforce a cross-app write lock; the owner must really establish the pause.
4. Keep source running/readable and retain independent encrypted backups, private env and all original media. Do not delete source after a copy.
5. Reconcile known missing QA/history against the actual authoritative source/receipts without recreating a generation, checkout or balance credit.

The source preparation itself did not pause/restart the existing services or change source data.

## 2. Read-only inventory

With runtime dependencies installed, explicitly name the private env and actual local media/cache roots:

```bash
python scripts/data_inventory.py snapshot --env-file /PRIVATE/source.env --output .private/source-before.json --media-root /AUTHORITATIVE/local_storage --audio-cache /AUTHORITATIVE/audio_cache
```

Omit a local root only if it genuinely is not part of the authoritative source. `--media-root` contains the `da-roastbox/` object namespace. Remote-only storage needs an owner-authorized export or its own verified inventory; this helper does not magically fetch an old vendor store.

The helper reads Mongo records and hashes them canonically, including BSON identity/types, and streams local file hashes. It never updates Mongo. Output is an exclusive private manifest; an existing report is not replaced. Console output contains counts, not records, emails, balances or keys. Take both inventories while writes remain paused; otherwise equality can legitimately change.

On Windows, protect backup/report/env folders with owner-only ACLs/encryption. POSIX mode 600 is not a substitute for Windows ACLs. Do not commit or attach private manifests or logs.

## 3. Mongo copy — plans first

Install the **official MongoDB Database Tools** (`mongodump`, `mongorestore`) separately on an owner-controlled machine. The helpers do not install software or create accounts.

Safe plans (no credential file loading, no archive, no network/database writes):

```bash
python scripts/mongo_transfer.py export --env-file /PRIVATE/source.env --archive .private/authoritative.archive.gz
python scripts/mongo_transfer.py restore --env-file /PRIVATE/target.env --archive .private/authoritative.archive.gz
```

If keeping the same already-approved external database, **do not export/restore unnecessarily**. Point the new app at that same authoritative Mongo only after assessing simultaneous-app workers and recovery behavior; do not let two deployment generations race over unfinished jobs.

### Explicit owner execution only

These commands perform real private-data operations. They were **not executed** during preparation:

```bash
python scripts/mongo_transfer.py export --env-file /PRIVATE/source.env --archive .private/authoritative.archive.gz --apply --confirm-writes-paused
python scripts/mongo_transfer.py restore --env-file /PRIVATE/target.env --archive .private/authoritative.archive.gz --apply --confirm-empty-target
```

- Export reads source, writes an exclusive local archive/private log and refuses an existing archive. It relies on your confirmed write pause.
- Restore allows an explicit **remote, certificate-verified TLS** destination only and checks actual target document counts. A nonempty database is refused. No `--drop`, delete, merge or automatic overwrite exists.
- Keep `DB_NAME` unchanged where possible. `--source-db-name ORIGINAL_NAME` is only for an expressly approved namespace rename, not a guess.
- A private temporary Database Tools config carries the URI; it is not placed on the command line or printed. Logs/archives remain private; review them locally.
- Failure can leave a partial archive or partially restored **new** target. Preserve it for review. Do not blindly rerun, delete the target, bypass checks or interpret an empty-check failure as permission to overwrite.
- Keep target application writes stopped through restore and reconciliation. `DATA_IMPORT_CONFIRMED=false` prevents this release app from starting prematurely on Render.

## 4. Media copy — namespace and bytes, not public URLs

Use only the actual owner-approved source and PRIVATE target. Default planning writes a new private local manifest, reads/hashes files, and makes **zero remote requests**:

```bash
python scripts/import_private_media.py --source-media /AUTHORITATIVE/local_storage --audio-cache /AUTHORITATIVE/audio_cache --manifest .private/media-plan.json
```

Explicit owner-only transfer (not run here):

```bash
python scripts/import_private_media.py --source-media /AUTHORITATIVE/local_storage --audio-cache /AUTHORITATIVE/audio_cache --manifest .private/media-applied.json --env-file /PRIVATE/target.env --apply --confirm-authoritative-source-and-private-target
```

It uses only the target file's Blob token, not Mongo, Stripe, AI or ambient credentials. It preserves `da-roastbox/audio/`, `da-roastbox/subjects/` and `da-roastbox/reels/` keys. Legacy cache MP3s map to their stable audio object names. Conflicting durable/cache bytes stop the plan rather than silently choosing one. Symlinks, unsupported namespaces/extensions and excessive objects are refused.

Each existing target object must be byte-identical or the transfer stops. New writes explicitly forbid overwrite and are read back/hash-verified. Identical existing objects are skipped, making a reviewed resume possible with a **new manifest filename**. Nothing is deleted. Partial prior copies remain intact. Upload/download operations and private transfer consume quota.

This is a local-files → private-Blob helper, not a universal vendor migration or public-URL importer. If older records contain vendor-specific absolute URLs/keys, inspect them privately and approve an explicit compatibility/mapping plan. Do not rewrite/re-generate historical shows or substitute new audio to make a missing object appear fixed.

## 5. Compare before permitting startup

Take target read-only database inventory with the same source tool/version:

```bash
python scripts/data_inventory.py snapshot --env-file /PRIVATE/target.env --output .private/target-after.json
python scripts/data_inventory.py compare .private/source-before.json .private/target-after.json
```

`database_equal=true` means canonical collection/document fingerprints match. `media_equal=null` means **remote media was not compared**, not that it passed. Use the verified media-transfer manifest/object counts and retained source hashes for that part, including all legacy cache bytes and remote-only exports. Inspect indexes, representative existing account balances/entitlements, old history, old audio/photos/reels and settlement markers without buying or regenerating anything.

Only after current authoritative data, media and missing-history reconciliation pass may the owner set `DATA_IMPORT_CONFIRMED=true`. Keep all backups/originals. Do not claim a restore rehearsal merely because a mock or plan succeeded.

## 6. Cutover and rollback

- Start only the intended new application worker. Maintain one Uvicorn worker and avoid old/new recovery workers managing the same unfinished jobs simultaneously.
- Verify extra beta gate, authentication, 21+ consent, owner-only media access and existing read-only data on the actual origin.
- Change entry URLs only after owner acceptance. Retain the old application/data for rollback; never overwrite an older project with this recovered source.
- If cutover fails, stop **the new app**, preserve logs/data and return traffic deliberately. Do not restore an older dump over a database that has since accepted new writes; reconcile first.
- Backups, retention, user deletion/reporting and a proven restore/incident procedure remain operational launch work. No live payments or app-store release are authorized by this source handoff.
