#!/usr/bin/env python3
"""Remove the @emergentbase/* devDependencies from frontend/package.json.

Those packages are pinned in yarn.lock to tarballs on assets.emergent.sh, a host
that no longer resolves, so `yarn install --frozen-lockfile` and `npm install`
both fail. They only provide the Emergent dev overlay and visual editor, which
craco.config.js already loads inside a try/catch and skips when absent.

The caller is expected to back package.json up first and restore it after the
install, so this never becomes a permanent source change. Idempotent: running it
twice is a no-op. Prints what it removed and nothing else.
"""
from __future__ import annotations

import json
import pathlib
import sys

TARGET = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "package.json"
PREFIX = "@emergentbase/"


def main() -> int:
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found", file=sys.stderr)
        return 1

    data = json.loads(TARGET.read_text(encoding="utf-8"))
    dev = data.get("devDependencies", {})
    removed = sorted(k for k in dev if k.startswith(PREFIX))
    for key in removed:
        dev.pop(key)

    if not removed:
        print("   no @emergentbase packages present - nothing to do")
        return 0

    TARGET.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for key in removed:
        print(f"   removed {key}")
    print(f"   {len(dev)} devDependencies remain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
