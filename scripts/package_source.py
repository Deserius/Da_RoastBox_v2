#!/usr/bin/env python3
"""Build a sanitized source archive without secrets, databases or customer media.

This is a heuristic secret scan, not a substitute for manually reviewing every
file and running a dedicated secret scanner before publishing a repository.
The archive contains app-owned bundled assets, not user-generated shows/media.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {'.git', '.private', '.vercel', '.data', '.tools', '.cache', '.venv', 'venv', 'runtime', 'node_modules',
                 '__pycache__', 'build', 'dist', 'coverage', '.emergent', 'memory', 'test_reports',
                 'audio_cache', 'local_storage', 'media_tmp'}
EXCLUDED_NAMES = {'.DS_Store', 'test_result.md', 'test_credentials.md', 'dump.rdb', '.netrc', '.npmrc', '.pypirc', 'key.properties'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.log', '.pem', '.key', '.p12', '.pfx', '.sqlite', '.sqlite3', '.db', '.zip', '.har', '.jks', '.keystore', '.mobileprovision', '.env', '.bson', '.archive', '.dump', '.wt', '.turtle', '.bak', '.backup', '.tmp', '.ndjson', '.jsonl', '.gz'}
PATTERNS = {
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'Stripe key': re.compile(r'\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b'),
    'Stripe signing secret': re.compile(r'\bwhsec_[A-Za-z0-9]{20,}\b'),
    'OpenAI-style key': re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b'),
    'AWS access key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'Supabase server key': re.compile(r'\bsb_secret_[A-Za-z0-9_-]{16,}\b'),
    'Google API key': re.compile(r'\bAIza[0-9A-Za-z_-]{35}\b'),
    'Blob read-write token': re.compile(r'\bvercel_blob_rw_[A-Za-z0-9]+_[A-Za-z0-9]{20,}\b'),
    'GitHub token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'Vercel token': re.compile(r'\bvcp_[A-Za-z0-9_]{24,}\b'),
    'Resend token': re.compile(r'\bre_[A-Za-z0-9]{24,}\b'),
    'Mongo URI with password': re.compile(r'mongodb(?:\+srv)?://[^\s/:@]+:[^\s/@]+@'),
}


def include_file(path: Path) -> bool:
    if path.is_symlink() or path.name in EXCLUDED_NAMES:
        return False
    lowered = path.name.lower()
    if (lowered.startswith('.env') or '.env.' in lowered) and not lowered.endswith('.env.example'):
        return False
    if 'token.json' in path.name.lower() or 'credentials.json' in path.name.lower() or path.name.lower().endswith('-service-account.json'):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.name.endswith(('.tar.gz', '.tar', '.tgz')):
        return False
    return True


def collect():
    result = []
    for base, dirs, names in os.walk(ROOT, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS and not (Path(base) / d).is_symlink())
        for name in sorted(names):
            path = Path(base) / name
            if include_file(path):
                result.append(path)
    return result


def scan(files):
    findings = []
    for path in files:
        # Source, scripts and config are UTF-8; binary assets are not inspected.
        try:
            if path.stat().st_size > 4_000_000:
                continue
            raw = path.read_bytes()
            if b'\0' in raw:
                continue
            text = raw.decode('utf-8')
        except (UnicodeError, OSError):
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                # Only these explicit documentation/test placeholders are safe;
                # every other credential-bearing Mongo URI is reported.
                if label == 'Mongo URI with password' and match.group() in {
                    'mongodb+srv://<user>:<password>@', 'mongodb://u:p@'
                }:
                    continue
                findings.append((str(path.relative_to(ROOT)), label))
    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', nargs='?', default=str(ROOT.parent / 'da_roastbox_source.zip'))
    parser.add_argument('--flat', action='store_true', help='Dockerfile/render.yaml at ZIP root for GitHub uploads')
    args = parser.parse_args()
    destination = Path(args.destination).expanduser().resolve()
    if destination.is_relative_to(ROOT):
        parser.error('place the archive outside the source directory')
    files = collect()
    findings = scan(files)
    if findings:
        for path, label in findings:
            print(f'POSSIBLE SECRET: {label} in {path}', file=sys.stderr)
        raise SystemExit('Review the findings before packaging. No archive was written.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + '.tmp')
    try:
        with zipfile.ZipFile(tmp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in files:
                archive.write(path, path.relative_to(ROOT).as_posix() if args.flat else (Path('da_roastbox') / path.relative_to(ROOT)).as_posix())
        with zipfile.ZipFile(tmp) as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise RuntimeError(f'Archive verification failed: {corrupt}')
        tmp.replace(destination)
    finally:
        tmp.unlink(missing_ok=True)
    print(f'Created {destination} ({len(files)} files, {destination.stat().st_size:,} bytes).')
    print('Excluded configuration secrets, databases, caches, private generated media, reports and dependencies.')
    print('Heuristic scan passed; manually review before public distribution.')


if __name__ == '__main__':
    main()
