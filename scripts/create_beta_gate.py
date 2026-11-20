#!/usr/bin/env python3
"""Explicit owner-only provisioning of an ADDITIONAL beta password gate.

Never called at app startup. Never rotates JWT_SECRET or an existing gate file.
The password is prompted without echo and is not written in plaintext.
"""
import argparse
from getpass import getpass
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from beta_access import password_verifier


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.private/beta-gate.env')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Destination already exists. Preserve your existing gate; nothing was changed.')
    password = getpass('Additional beta password (at least 12 characters): ')
    if len(password) < 12 or password != getpass('Confirm beta password: '):
        raise SystemExit('Password too short or confirmation did not match. No file was written.')
    content = 'BETA_ACCESS_PASSWORD_HASH=\'' + password_verifier(password) + "'\n"
    content += 'BETA_ACCESS_SIGNING_KEY=' + secrets.token_urlsafe(48) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output: output.write(content)
    print('Private beta gate file created. Copy its two values into Render manually, without quote characters.')
    print('Keep it out of Git. Existing account credentials, database, JWT and app sessions were not changed.')


if __name__ == '__main__':
    main()
