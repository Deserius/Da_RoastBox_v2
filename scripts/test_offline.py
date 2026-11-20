#!/usr/bin/env python3
"""Run explicitly selected checks with providers/network blocked and test-only DBs.

Only loopback MongoDB:27017 and explicitly bound in-process test stubs are allowed. No existing .env is loaded. Each child
uses a temporary media directory and a newly named throwaway database; the
Mongo access guard rejects non-test database names. Never invokes paid QA scripts.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import runpy
import socket
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
SUITE = (
    'test_multimodal_writer.py', 'test_adult_roast_pipeline.py', 'test_adult_personas.py',
    'test_lineup_roasts.py', 'test_roast_showrunner.py', 'test_deployment.py',
    'test_email_auth.py', 'test_preview_limits.py', 'test_rap_battle.py',
    'test_reel_reliability.py', 'test_reel_streaming.py', 'test_voice_first_mix.py',
    'test_voice_leveling.py', 'verify_workspace.py', 'test_render_release.py',
)
DB_PATTERN = re.compile(r'^roastbox_[a-z_]+test_[a-f0-9]{12}$')


def child(script):
    os.environ['ROASTBOX_OFFLINE_GUARD'] = '1'
    sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/scripts')]
    connect, connect_ex, getaddrinfo, bind = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo, socket.socket.bind
    stub_ports = set()
    def guarded_bind(self, address):
        if self.family == socket.AF_UNIX:
            return bind(self, address)
        if not (isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1') and address[1] == 0):
            raise RuntimeError('OFFLINE GUARD: only ephemeral loopback test stubs may bind')
        result = bind(self, address)
        stub_ports.add(self.getsockname()[1])
        return result
    socket.socket.bind = guarded_bind
    def allowed(address):
        return isinstance(address, tuple) and len(address) >= 2 and address[0] in ('127.0.0.1', '::1') and address[1] in ({27017} | stub_ports)
    def guarded_connect(self, address):
        if self.family != socket.AF_UNIX and not allowed(address):
            raise RuntimeError('OFFLINE GUARD: outbound connection prohibited')
        return connect(self, address)
    def guarded_connect_ex(self, address):
        if self.family != socket.AF_UNIX and not allowed(address):
            raise RuntimeError('OFFLINE GUARD: outbound connection prohibited')
        return connect_ex(self, address)
    def guarded_getaddrinfo(host, port, *args, **kwargs):
        if host not in ('localhost', '127.0.0.1', '::1') or int(port or 0) not in ({27017} | stub_ports):
            raise RuntimeError('OFFLINE GUARD: external DNS prohibited')
        return getaddrinfo(host, port, *args, **kwargs)
    socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = guarded_connect, guarded_connect_ex, guarded_getaddrinfo
    # Driver-level access guard; even a misconfigured test cannot select/drop the live DB.
    from pymongo import MongoClient, AsyncMongoClient
    from motor.motor_asyncio import AsyncIOMotorClient
    def database_guard(original, *, allow_admin_ping=False):
        def wrapped(self, name=None, *args, **kwargs):
            if name == 'admin' and allow_admin_ping:
                from types import SimpleNamespace
                database = original(self, name, *args, **kwargs)
                def ping_only(command, *a, **k):
                    if command != 'ping':
                        raise RuntimeError('OFFLINE GUARD: only admin ping is allowed')
                    return database.command(command, *a, **k)
                return SimpleNamespace(command=ping_only)
            if not DB_PATTERN.fullmatch(str(name)):
                raise RuntimeError('OFFLINE GUARD: non-test database access prohibited')
            return original(self, name, *args, **kwargs)
        return wrapped
    for cls in (MongoClient, AsyncMongoClient, AsyncIOMotorClient):
        cls.__getitem__ = database_guard(cls.__getitem__, allow_admin_ping=True)
        # get_database() constructs a database directly in PyMongo; guarding
        # only [] leaves a path to the customer's database. None/default names
        # are rejected too, rather than inferred from a credential-bearing URI.
        cls.get_database = database_guard(cls.get_database, allow_admin_ping=True)
        cls.drop_database = database_guard(cls.drop_database)
        def no_default_database(self, *a, **k):
            raise RuntimeError('OFFLINE GUARD: implicit/default database access prohibited')
        cls.get_default_database = no_default_database
        def no_database_listing(self, *a, **k):
            raise RuntimeError('OFFLINE GUARD: database enumeration prohibited')
        cls.list_database_names = no_database_listing
        cls.list_databases = no_database_listing
    sys.argv = [str(ROOT / 'backend/scripts' / script)]
    runpy.run_path(sys.argv[0], run_name='__main__')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tests', nargs='*', help='Allowlisted script names; default: all checks')
    parser.add_argument('--benchmark', action='store_true', help='Preload API and stress photos in the offline reel check')
    parser.add_argument('--child', choices=SUITE, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        return child(args.child)
    selected = args.tests or SUITE
    if any(s not in SUITE for s in selected):
        parser.error('Unknown script. Paid QA and arbitrary scripts are intentionally not supported.')
    results = []
    for script in selected:
        if not (ROOT / 'backend/scripts' / script).is_file():
            print('MISSING:', script, flush=True);results.append((script, 1));continue
        with tempfile.TemporaryDirectory(prefix='roastbox-offline-') as temp:
            # An allowlist, not a copy of the caller's credential-bearing environment.
            env = {key: os.environ[key] for key in ('PATH', 'HOME', 'SYSTEMROOT', 'TEMP', 'TMP', 'LANG') if key in os.environ}
            env.update({
                'PYTHON_DOTENV_DISABLED': '1', 'PYTHONUNBUFFERED': '1', 'APP_ENV': 'test',
                'ROASTBOX_BENCHMARK': '1' if args.benchmark else '0',
                'REEL_ENCODER_PRESET': 'ultrafast' if args.benchmark else 'veryfast',
                'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
                'MONGO_URL': 'mongodb://127.0.0.1:27017',
                'DB_NAME': 'roastbox_guard_test_' + uuid.uuid4().hex[:12],
                'JWT_SECRET': 'offline-test-only-secret-not-for-deployment',
                'STORAGE_BACKEND': 'local', 'LOCAL_STORAGE_DIR': str(Path(temp) / 'media'),
                'AUDIO_CACHE_DIR': str(Path(temp) / 'audio'),
                # Heavy FFmpeg intermediates belong on workspace disk, not a
                # small tmpfs that would distort the RSS-only capacity probe.
                'TMPDIR': str(ROOT / '.cache/offline-media-tmp'),
                'OPENROUTER_API_KEY': '', 'OPENAI_API_KEY': '', 'EMERGENT_LLM_KEY': '',
                'ELEVENLABS_API_KEY': '', 'STRIPE_API_KEY': '', 'STRIPE_WEBHOOK_SECRET': '',
                'BLOB_READ_WRITE_TOKEN': '', 'RESEND_API_KEY': '',
                'ENABLE_PAID_DIAGNOSTICS': 'false', 'PREVIEW_HOSTED_DAILY_SHOW_LIMIT': '-1',
                'PREVIEW_HOSTED_DAILY_VOICE_LIMIT': '-1', 'RENDER_EXTERNAL_URL': '',
            })
            Path(env['TMPDIR']).mkdir(parents=True, exist_ok=True)
            print('\n=== OFFLINE:', script, '===', flush=True)
            result = subprocess.run([sys.executable, __file__, '--child', script], cwd=ROOT, env=env)
            results.append((script, result.returncode))
    print('\n=== OFFLINE SUMMARY ===', flush=True)
    for script, status in results:
        print(('PASS' if status == 0 else 'FAIL') + ': ' + script, flush=True)
    raise SystemExit(1 if any(status for _, status in results) else 0)


if __name__ == '__main__':
    main()
