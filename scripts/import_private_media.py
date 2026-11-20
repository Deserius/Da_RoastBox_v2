#!/usr/bin/env python3
"""Plan, or explicitly copy/verify, private media into an OWNER-APPROVED Blob store.

Default is local dry-run: no token or network required. --apply is an actual
remote write and consumes the owner's storage/operation/transfer allowance.
Never deletes or overwrites an existing object. Mongo, Stripe and AI are unused.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'backend')]
from data_inventory import media_inventory, private_json


async def copy_and_verify(files, manifest, read, write):
    copied, already_equal = 0, 0
    for key, path in files.items():
        wanted = manifest[key]
        existing = await read(key)
        if existing is not None:
            if len(existing) != wanted['bytes'] or hashlib.sha256(existing).hexdigest() != wanted['sha256']:
                raise ValueError('Existing target bytes differ; stopped without overwriting')
            already_equal += 1
            continue
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != wanted['sha256']:
            raise ValueError('Source changed after planning; stopped')
        await write(key, payload, mimetypes.guess_type(key)[0] or 'application/octet-stream', overwrite=False)
        confirmed = await read(key)
        if confirmed is None or hashlib.sha256(confirmed).hexdigest() != wanted['sha256']:
            raise RuntimeError('Remote private-media verification did not match')
        copied += 1
    return copied, already_equal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-media', type=Path, help='LOCAL_STORAGE_DIR containing da-roastbox/')
    parser.add_argument('--audio-cache', type=Path, help='Legacy backend/audio_cache; cached originals are preserved too')
    parser.add_argument('--manifest', type=Path, required=True, help='New private output file; existing manifests are never replaced')
    parser.add_argument('--env-file', type=Path, help='Private target env file; only its Blob token is used')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-authoritative-source-and-private-target', action='store_true')
    args = parser.parse_args()
    if args.manifest.exists(): parser.error('Manifest exists. Preserve it and choose a new filename.')
    if not args.source_media and not args.audio_cache: parser.error('Choose the actual authoritative media/cache source.')
    if args.apply and not (args.env_file and args.confirm_authoritative_source_and_private_target):
        parser.error('Actual copying requires an explicit private env file and source/target confirmation.')
    try:
        files, manifest = media_inventory(args.source_media, args.audio_cache)
        for key in files:
            if not key.startswith(('da-roastbox/audio/', 'da-roastbox/subjects/', 'da-roastbox/reels/')):
                raise ValueError('Unexpected private-media namespace; review before upload')
            if Path(key).suffix.lower() not in {'.mp3', '.jpg', '.jpeg', '.png', '.webp', '.mp4'}:
                raise ValueError('Unexpected private-media format; review before upload')
        total = sum(item['bytes'] for item in manifest.values())
        if total > 1024 ** 3: raise ValueError('Source exceeds the nominal Free 1 GiB store budget; no upload was attempted')
        copied = equal = 0
        if args.apply:
            from dotenv import dotenv_values
            env = dotenv_values(args.env_file, interpolate=False)
            token = env.get('BLOB_READ_WRITE_TOKEN') or ''
            if not token.startswith('vercel_blob_rw_'): raise ValueError('Explicit private Blob token required')
            # Do not load or forward the Mongo/Stripe/AI credentials in this file.
            os.environ['BLOB_READ_WRITE_TOKEN'] = token
            from services import private_blob
            copied, equal = asyncio.run(copy_and_verify(files, manifest, private_blob.get_bytes, private_blob.put_bytes))
        private_json(args.manifest, {'schema': 1, 'applied': args.apply, 'source_objects': manifest,
                                    'verified_objects': len(manifest) if args.apply else 0,
                                    'copied': copied, 'already_identical': equal, 'source_bytes': total})
        print(json.dumps({'dry_run': not args.apply, 'objects': len(manifest), 'bytes': total,
                          'copied': copied, 'already_identical': equal,
                          'all_remote_bytes_verified': bool(args.apply),
                          'warning': 'Owner must check remaining Free allowance and plan/commercial eligibility before --apply.'}, indent=2))
    except Exception as exc:
        print('Media copy stopped (' + type(exc).__name__ + '). Nothing was deleted or intentionally overwritten. A partial copy can be resumed with a NEW report filename.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
