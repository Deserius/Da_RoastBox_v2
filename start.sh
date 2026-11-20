#!/usr/bin/env sh
# One command: reconcile pinned dependencies, build, and launch locally.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec sh ./install.sh --start "$@"
