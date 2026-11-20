#!/usr/bin/env python3
"""Point yarn.lock's resolved URLs at registry.npmjs.org, reversibly.

Why
---
Every ``resolved`` line in ``frontend/yarn.lock`` points at
``registry.yarnpkg.com``. That hostname is unreachable on some networks
(IPv6-only resolution, corporate DNS filtering, TLS interception, or a blocked
CDN edge). When it is unreachable, ``yarn install`` dies with::

    error Error: Client network socket disconnected before secure TLS
    connection was established

The ``--registry`` flag does NOT help: yarn 1 fetches from the lockfile's
``resolved`` URL and ignores the flag for entries that already have one.

``registry.npmjs.org`` serves byte-identical tarballs (the ``#sha1`` fragment
recorded in the lockfile is the integrity check, and it is preserved), so
rewriting the host is safe. This is a network workaround, not a dependency
change: no version, no range, and no integrity hash is touched.

The caller backs yarn.lock up and restores it after the install, so the repo's
committed lockfile is never a permanent part of the change.

Usage
-----
    python scripts/fix_lockfile_registry.py [path/to/yarn.lock]

Exits 0 whether or not anything needed rewriting.
"""
from __future__ import annotations

import pathlib
import sys

OLD = "https://registry.yarnpkg.com/"
NEW = "https://registry.npmjs.org/"


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")] or ["frontend/yarn.lock"]
    target = pathlib.Path(args[0])
    if not target.is_absolute():
        candidate = pathlib.Path.cwd() / target
        target = (
            candidate
            if candidate.exists()
            else pathlib.Path(__file__).resolve().parents[1] / target
        )
    if not target.exists():
        print(f"   {target.name} not found - skipping")
        return 0

    text = target.read_text(encoding="utf-8")
    count = text.count(OLD)
    if not count:
        print(f"   {target.name} already points at registry.npmjs.org")
        return 0

    target.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print(f"   rewrote {count} lockfile URL(s) to registry.npmjs.org")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
