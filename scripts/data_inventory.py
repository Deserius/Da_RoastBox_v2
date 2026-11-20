#!/usr/bin/env python3
"""Read-only Mongo/media fingerprints for owner-controlled migration comparison.

No customer records, emails, balances, keys or media bytes appear in console
output. The private manifest contains counts, hashes and relative media keys.
Use the authoritative current source, NOT an older recovered workspace snapshot.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def private_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Refuse overwrite: a preservation baseline must remain immutable.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(data, output, indent=2, sort_keys=True)
        output.write('\n')


def fingerprint_database(database):
    from bson.json_util import CANONICAL_JSON_OPTIONS, dumps
    collections = {}
    for name in sorted(database.list_collection_names()):
        digest, count = hashlib.sha256(), 0
        for doc in database[name].find({}).sort('_id', 1):
            digest.update(dumps(doc, json_options=CANONICAL_JSON_OPTIONS, sort_keys=True, separators=(',', ':')).encode())
            digest.update(b'\n')
            count += 1
        collections[name] = {'documents': count, 'sha256': digest.hexdigest()}
    return collections


def file_sha256(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def media_inventory(media_root=None, audio_cache=None):
    files = {}
    if media_root:
        root = Path(media_root).resolve()
        if not root.is_dir(): raise ValueError('Media source directory is missing')
        for path in sorted(root.rglob('*')):
            if path.is_symlink(): raise ValueError('Symlink in private media source')
            if not path.is_file(): continue
            key = path.relative_to(root).as_posix()
            if not key.startswith('da-roastbox/'):
                raise ValueError('Media root must contain the da-roastbox object-prefix folder')
            files[key] = path
    if audio_cache:
        cache = Path(audio_cache).resolve()
        if not cache.is_dir(): raise ValueError('Audio-cache source directory is missing')
        for path in sorted(cache.glob('*.mp3')):
            if path.is_symlink(): raise ValueError('Symlink in audio-cache source')
            key = 'da-roastbox/audio/' + path.name
            if key in files and file_sha256(files[key]) != file_sha256(path):
                raise ValueError('Conflicting durable/cache copies require owner reconciliation')
            files.setdefault(key, path)
    manifest = {key: {'bytes': path.stat().st_size, 'sha256': file_sha256(path)} for key, path in files.items()}
    return files, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    take = modes.add_parser('snapshot')
    take.add_argument('--env-file', type=Path, required=True)
    take.add_argument('--output', type=Path, required=True)
    take.add_argument('--media-root', type=Path)
    take.add_argument('--audio-cache', type=Path)
    compare = modes.add_parser('compare')
    compare.add_argument('before', type=Path); compare.add_argument('after', type=Path)
    args = parser.parse_args()
    try:
        if args.mode == 'compare':
            a, b = json.loads(args.before.read_text()), json.loads(args.after.read_text())
            db_equal = a.get('collections') == b.get('collections')
            media_equal = a.get('media') == b.get('media') if a.get('media') is not None and b.get('media') is not None else None
            print(json.dumps({'database_equal': db_equal, 'media_equal': media_equal,
                              'note': 'null media equality means remote media was not compared; use the verified media-import manifest.'}, indent=2))
            raise SystemExit(0 if db_equal and media_equal is not False else 1)
        from dotenv import dotenv_values
        from pymongo import MongoClient
        env = dotenv_values(args.env_file, interpolate=False)
        uri, name = env.get('MONGO_URL'), env.get('DB_NAME')
        if not uri or not name: raise ValueError('Explicit MONGO_URL and DB_NAME are required')
        with MongoClient(uri, serverSelectionTimeoutMS=10000, appname='roastbox-readonly-inventory') as client:
            collections = fingerprint_database(client[name])
        media = media_inventory(args.media_root, args.audio_cache)[1] if args.media_root or args.audio_cache else None
        private_json(args.output, {'schema': 1, 'collections': collections, 'media': media})
        print(json.dumps({'collections': len(collections), 'documents': sum(x['documents'] for x in collections.values()),
                          'media_objects': len(media) if media is not None else None,
                          'private_manifest_written': True, 'database_writes': 0}, indent=2))
    except SystemExit:
        raise
    except Exception as exc:
        print('Inventory stopped safely (' + type(exc).__name__ + '). No database/media writes were attempted.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
