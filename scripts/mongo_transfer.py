#!/usr/bin/env python3
"""Owner-operated MongoDB Database Tools wrapper, defaulting to a NO-WRITE plan.

Never starts/stops MongoDB, edits accounts, invents purchases or drops a target.
--apply is explicit. Export also requires an owner-confirmed write pause for a
consistent standalone dump. Restore refuses a nonempty destination database.
URIs/passwords are passed in a private temporary config, never on argv/stdout.
Install official mongodump/mongorestore separately; no account/signup is needed.
"""
from __future__ import annotations
import argparse
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit


def safe_remote_tls(uri):
    try:
        parsed = urlsplit(uri)
        q = {k.lower(): [v.lower() for v in vals] for k, vals in parse_qs(parsed.query).items()}
        if parsed.scheme not in {'mongodb', 'mongodb+srv'} or not parsed.hostname:
            return False
        host = parsed.hostname.lower().rstrip('.')
        if host == 'localhost' or host.endswith('.localhost'):
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None:
            mapped = getattr(address, 'ipv4_mapped', None)
            if address.is_loopback or address.is_unspecified or (mapped is not None and mapped.is_loopback):
                return False
        return ((parsed.scheme == 'mongodb+srv' or q.get('tls') == ['true'] or q.get('ssl') == ['true'])
                and not any(q.get(k) == ['true'] for k in ('tlsallowinvalidcertificates', 'tlsallowinvalidhostnames', 'tlsinsecure'))
                and q.get('tls') != ['false'] and q.get('ssl') != ['false'])
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['export', 'restore'])
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--source-db-name', help='Only for an intentional namespace rename; normally keep DB_NAME unchanged')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-writes-paused', action='store_true')
    parser.add_argument('--confirm-empty-target', action='store_true')
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps({'plan_only': True, 'mode': args.mode, 'database_writes': 0,
                          'credentials_loaded': False,
                          'next': 'Read docs/DATA_PRESERVATION.md; --apply is an actual owner-controlled transfer.'}, indent=2))
        return
    if args.mode == 'export' and not args.confirm_writes_paused:
        parser.error('Consistent export requires an owner-controlled pause of application writes, NOT stopping MongoDB.')
    if args.mode == 'restore' and not args.confirm_empty_target:
        parser.error('Restore requires explicit confirmation AND an actual empty-target check.')
    try:
        from dotenv import dotenv_values
        from pymongo import MongoClient
        env = dotenv_values(args.env_file, interpolate=False)
        uri, name = env.get('MONGO_URL'), env.get('DB_NAME')
        if not uri or not name: raise ValueError('Explicit Mongo settings required')
        if args.mode == 'restore':
            if not safe_remote_tls(uri): raise ValueError('Restore is restricted to an explicit remote TLS target')
            if not args.archive.is_file(): raise ValueError('Archive is missing')
            with MongoClient(uri, serverSelectionTimeoutMS=10000) as client:
                database = client[name]
                if any(database[c].count_documents({}, limit=1) for c in database.list_collection_names()):
                    raise ValueError('Destination contains records; merge/overwrite is not authorized')
        elif args.archive.exists():
            raise ValueError('Archive already exists; preservation backups are immutable')
        binary = shutil.which('mongodump' if args.mode == 'export' else 'mongorestore')
        if not binary: raise FileNotFoundError('Install official MongoDB Database Tools first')
        args.archive.parent.mkdir(parents=True, exist_ok=True)
        log_path = args.archive.with_name(args.archive.name + '.transfer.log')
        log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        if args.mode == 'export':
            fd = os.open(args.archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        with tempfile.TemporaryDirectory(prefix='.mongo-transfer-', dir=args.archive.parent) as temp:
            config = Path(temp) / 'credentials.yml'
            fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as output: output.write('uri: ' + json.dumps(uri) + '\n')
            command = [binary, '--config=' + str(config), '--gzip', '--archive=' + str(args.archive)]
            if args.mode == 'export':
                command += ['--db=' + name]
            else:
                source_name = args.source_db_name or name
                command += ['--stopOnError', '--nsInclude=' + source_name + '.*']
                if source_name != name:
                    command += ['--nsFrom=' + source_name + '.*', '--nsTo=' + name + '.*']
            with os.fdopen(log_fd, 'wb') as log:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError('Database Tools failed; preserve the private log/partial archive for review')
        print(json.dumps({'completed': True, 'mode': args.mode, 'existing_target_records_overwritten': 0,
                          'next': 'Compare read-only fingerprints and verify media before DATA_IMPORT_CONFIRMED=true.'}, indent=2))
    except Exception as exc:
        print('Transfer stopped (' + type(exc).__name__ + '). No drop/delete was requested. Keep any archive/log private; review before retrying.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
