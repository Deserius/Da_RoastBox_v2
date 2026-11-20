#!/usr/bin/env python3
"""Read-only, no-network Render configuration check. Prints codes, never values.

An explicit private dotenv file is required; ambient credentials are not read.
This does not start the API, log in, probe providers, import data or spend funds.
"""
from __future__ import annotations
import argparse
import fnmatch
import importlib.metadata as md
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from dotenv import dotenv_values
from beta_access import parse_verifier
from runtime_security import configuration_errors, enabled


def inspect_settings(settings):
    env = {str(k): str(v) for k, v in settings.items() if v is not None}
    env.setdefault('APP_ENV', 'beta')
    env['RENDER'] = 'true'
    errors = configuration_errors(env)
    warnings = []
    if env['APP_ENV'] != 'beta':
        errors.append('THIS_HANDOFF_REQUIRES_PASSWORD_PROTECTED_BETA')
    for key in ('OPENROUTER_API_KEY', 'OPENAI_API_KEY', 'STRIPE_API_KEY', 'STRIPE_WEBHOOK_SECRET'):
        if not env.get(key, '').strip():
            errors.append(key + '_REQUIRED_FOR_REQUESTED_HOSTED_FEATURES')
    if env.get('BETA_ACCESS_PASSWORD_HASH'):
        try: parse_verifier(env['BETA_ACCESS_PASSWORD_HASH'])
        except ValueError: errors.append('BETA_PASSWORD_VERIFIER_INVALID')
    if len(env.get('BETA_ACCESS_SIGNING_KEY', '')) < 32:
        errors.append('BETA_SIGNING_KEY_MIN_32_REQUIRED')
    if env.get('BETA_ACCESS_SIGNING_KEY') == env.get('JWT_SECRET'):
        errors.append('BETA_SIGNING_KEY_MUST_BE_SEPARATE_FROM_EXISTING_JWT')
    origin = env.get('APP_BASE_URL') or env.get('RENDER_EXTERNAL_URL') or ''
    host = urlsplit(origin).hostname or ''
    if host and not any(fnmatch.fnmatchcase(host, h.strip()) for h in env.get('ALLOWED_HOSTS', '').split(',')):
        errors.append('ALLOWED_HOSTS_DOES_NOT_INCLUDE_DEPLOYED_HOST')
    if env.get('BLOB_READ_WRITE_TOKEN') and not re.fullmatch(r'vercel_blob_rw_[A-Za-z0-9]+_[^\s]+', env['BLOB_READ_WRITE_TOKEN']):
        errors.append('PRIVATE_BLOB_TOKEN_FORMAT_INVALID')
    if env.get('STRIPE_WEBHOOK_SECRET') and not env['STRIPE_WEBHOOK_SECRET'].startswith('whsec_'):
        errors.append('STRIPE_TEST_WEBHOOK_SIGNING_SECRET_INVALID')
    if not env.get('ELEVENLABS_API_KEY'):
        warnings.append('ELEVENLABS_HOSTED_KEY_ABSENT_PREMIUM_REQUIRES_BYOK_OR_REPORTED_FALLBACK')
    if enabled(env.get('EMAIL_AUTH_ENABLED')) and not (env.get('RESEND_API_KEY') and env.get('EMAIL_FROM')):
        warnings.append('EMAIL_ENABLED_WITHOUT_RENDER_HTTPS_DELIVERY_CHECK_CAPABILITY_STATUS')
    if env.get('REEL_ENCODER_PRESET', 'ultrafast') != 'ultrafast':
        warnings.append('NONDEFAULT_ENCODER_HAS_NOT_PASSED_THE_FREE_MEMORY_PROBE')
    warnings.extend(['NO_REMOTE_PROVIDER_ORIGIN_OR_PRIVATE_STORAGE_VALIDATION_PERFORMED',
                     'VERIFY_FREE_PLAN_ELIGIBILITY_QUOTAS_AND_BILLING_CONTROLS',
                     'PRESERVE_EXISTING_JWT_SECRET_AND_AUTHORITATIVE_DATA'])
    return sorted(set(errors)), sorted(set(warnings))


def pinned_runtime_errors():
    from packaging.requirements import Requirement
    errors = []
    for raw in (ROOT / 'backend/requirements-runtime.txt').read_text().splitlines():
        raw = raw.split(' #', 1)[0].strip()
        if not raw or raw.startswith('#'):
            continue
        req = Requirement(raw)
        if req.marker and not req.marker.evaluate():
            continue
        try:
            if md.version(req.name) not in req.specifier:
                errors.append('RUNTIME_VERSION_MISMATCH:' + req.name)
        except md.PackageNotFoundError:
            errors.append('RUNTIME_PACKAGE_MISSING:' + req.name)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--origin', help='Actual HTTPS app origin; overrides only APP_BASE_URL in memory')
    parser.add_argument('--check-runtime', action='store_true', help='Also compare installed package versions to the runtime lock')
    args = parser.parse_args()
    if not args.env_file.is_file():
        parser.error('The explicit private environment file does not exist.')
    settings = dict(dotenv_values(args.env_file, interpolate=False))
    if args.origin: settings['APP_BASE_URL'] = args.origin
    errors, warnings = inspect_settings(settings)
    if args.check_runtime: errors.extend(pinned_runtime_errors())
    print(json.dumps({'passed': not errors, 'errors': errors, 'warnings': warnings,
                      'scope': 'static configuration/package metadata only; zero network calls'}, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == '__main__':
    main()
