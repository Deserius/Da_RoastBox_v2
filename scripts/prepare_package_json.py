#!/usr/bin/env python3
"""Make frontend/package.json installable, reversibly.

Problem this solves
-------------------
``frontend/package.json`` pins two ``@emergentbase/*`` devDependencies to
tarballs on ``assets.emergent.sh``, a host that no longer resolves. Any install
of this project therefore fails outright. Those two packages only provide the
Emergent dev overlay and visual editor; ``craco.config.js`` loads them inside a
try/catch and logs "overlay disabled" when they are absent, so the build and the
app are unaffected.

The caller backs ``package.json`` up first and restores it afterwards, so this
never becomes a permanent source change. ``frontend/package.json`` in the
repository stays exactly as shipped.

Why yarn is the supported installer
-----------------------------------
The repo pins 46 transitive versions through the yarn-only ``resolutions``
field, and ``yarn.lock`` records the resulting tree (1457 pinned tarballs). npm
ignores ``resolutions`` and hoists differently, which produces a different and
broken tree: ajv 6 ends up hoisted where ``ajv-keywords@5`` requires ajv 8, and
``craco build`` dies with MODULE_NOT_FOUND inside terser-webpack-plugin.

``--npm-overrides`` exists for an npm-only fallback. It copies ``resolutions``
into npm's ``overrides`` field and rewrites yarn's ``**/parent/child`` glob keys
into npm's nested form. This gets much closer but is not guaranteed to
reproduce yarn's tree; yarn is the tested path.

Usage
-----
    python scripts/prepare_package_json.py [--strip-only|--npm-overrides] [path]
"""
from __future__ import annotations

import json
import pathlib
import sys

OVERLAY_PREFIX = "@emergentbase/"


def translate(resolutions: dict[str, str]) -> dict:
    """Convert yarn ``resolutions`` keys into npm ``overrides`` syntax.

    yarn accepts a glob path naming a nested dependency::

        "**/css-loader/postcss": "8.5.28"
        "**/@eslint/eslintrc/js-yaml": "4.3.2"

    npm expects nesting instead, and rejects a key containing more than one
    slash ("Override without name")::

        {"css-loader": {"postcss": "8.5.28"}}
        {"@eslint/eslintrc": {"js-yaml": "4.3.2"}}
    """
    out: dict = {}
    for key, version in resolutions.items():
        path = key[3:] if key.startswith("**/") else key
        parts: list[str] = []
        for segment in path.split("/"):
            if not segment:
                continue
            if segment.startswith("@") and parts and not parts[-1].startswith("@"):
                parts[-1] = f"{parts[-1]}/{segment}"  # join a scope to its name
            else:
                parts.append(segment)
        if len(parts) == 1:
            out[parts[0]] = version
        elif len(parts) >= 2:
            node = out
            for parent in parts[:-1]:
                child = node.setdefault(parent, {})
                if not isinstance(child, dict):
                    child = node[parent] = {".": child}
                node = child
            node[parts[-1]] = version
    return out


def count_leaves(node) -> int:
    if not isinstance(node, dict):
        return 1
    return sum(count_leaves(v) for v in node.values())


def main(argv: list[str]) -> int:
    strip_only = "--strip-only" in argv
    npm_overrides = "--npm-overrides" in argv
    args = [a for a in argv if not a.startswith("--")] or ["frontend/package.json"]

    target = pathlib.Path(args[0])
    if not target.is_absolute():
        # Prefer the current directory, so callers that already cd'd into
        # frontend/ work; fall back to the project root.
        candidate = pathlib.Path.cwd() / target
        target = (
            candidate
            if candidate.exists()
            else pathlib.Path(__file__).resolve().parents[1] / target
        )
    if not target.exists():
        print(f"ERROR: {target} not found", file=sys.stderr)
        return 1

    data = json.loads(target.read_text(encoding="utf-8"))
    changed = False

    dev = data.get("devDependencies", {})
    removed = sorted(k for k in dev if k.startswith(OVERLAY_PREFIX))
    for key in removed:
        dev.pop(key)
    if removed:
        changed = True
        for key in removed:
            print(f"   removed {key}")

    if npm_overrides and not strip_only:
        resolutions = data.get("resolutions") or {}
        overrides = translate(resolutions)
        if overrides and data.get("overrides") != overrides:
            data["overrides"] = overrides
            changed = True
            print(
                f"   translated {len(resolutions)} resolutions into "
                f"{count_leaves(overrides)} npm override(s)"
            )

    if not changed:
        print("   package.json already installable - nothing to do")
        return 0

    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"   {len(dev)} devDependencies remain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
