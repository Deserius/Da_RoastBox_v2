#!/bin/sh
set -eu
# Prepare only an explicitly selected local backend (native/paid-disk installs).
# Render Free uses private remote Blob, not a disk. Always drop root privileges.
if [ "${STORAGE_BACKEND:-local}" = "local" ]; then
  : "${LOCAL_STORAGE_DIR:=/var/data/roastbox}"
  mkdir -p "$LOCAL_STORAGE_DIR"
  chown roastbox:roastbox "$LOCAL_STORAGE_DIR"
fi
exec gosu roastbox "$@"
