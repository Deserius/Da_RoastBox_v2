#!/usr/bin/env sh
# Bootstrap Python if needed, then install everything into this project folder.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; assert sys.version_info[:2] in ((3,11),(3,12),(3,13))' 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.11–3.13 is required to run install.py."
  if command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
    printf 'Install Python with apt (requires sudo)? [y/N] '
    read -r answer
    case "$answer" in y|Y|yes|YES) sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip;; *) exit 1;; esac
    PYTHON=python3
  elif command -v brew >/dev/null 2>&1; then
    printf 'Install Python 3.13 with Homebrew? [y/N] '
    read -r answer
    case "$answer" in y|Y|yes|YES) brew install python@3.13;; *) exit 1;; esac
    PYTHON=python3.13
  else
    echo 'Install Python 3.13 from https://www.python.org/downloads/ and rerun this script.'
    exit 1
  fi
fi
exec "$PYTHON" install.py "$@"
