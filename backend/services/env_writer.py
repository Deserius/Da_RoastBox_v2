"""Persist console-entered credentials into the project's own .env files.

Two requirements pull against each other:

* the values must survive a restart, so they have to reach a file the running
  process reads on boot;
* they must never be committed, because they are real credentials.

So the file is written inside the workspace *and* added to .gitignore. Git keeps
ignoring it, while the workspace (and therefore an Arena preview that runs from
this checkout) keeps using it.

Writes are atomic: a temporary file is renamed over the target so an interrupted
write cannot leave a half-written .env that fails to parse on next boot.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional

log = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent

# Where secrets land. The backend reads this on boot via python-dotenv/config.
SECRETS_FILE = BACKEND_ROOT / ".env"
SECRETS_FILE_LABEL = "backend/.env"

# Never let these be committed. Patterns are written verbatim.
GITIGNORE_RULES = (
    "# Provider credentials entered through the Settings console.",
    "# These are real secrets: keep them on this machine only.",
    "backend/.env",
    "backend/.env.local",
)

_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SAFE_VALUE = re.compile(r"[\r\n\x00]")


class EnvWriteError(RuntimeError):
    """Raised when the .env file cannot be updated safely."""


def _gitignore_path() -> Path:
    return PROJECT_ROOT / ".gitignore"


def ensure_gitignored() -> bool:
    """Make sure the secrets file is ignored. Returns True if a rule was added.

    Rewriting .gitignore is a workspace change, so this only ever *adds* the
    missing rules; existing content is preserved byte for byte.
    """
    path = _gitignore_path()
    try:
        current = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as exc:
        raise EnvWriteError(f"Could not read .gitignore: {exc}") from exc

    lines = {line.strip() for line in current.splitlines()}
    missing = [rule for rule in GITIGNORE_RULES
               if not rule.startswith("#") and rule not in lines]
    if not missing and GITIGNORE_RULES[0] in current:
        return False

    block = "\n".join(GITIGNORE_RULES) + "\n"
    separator = "" if current.endswith("\n") or not current else "\n"
    try:
        path.write_text(f"{current}{separator}\n{block}", encoding="utf-8")
    except OSError as exc:
        raise EnvWriteError(f"Could not update .gitignore: {exc}") from exc
    log.info("Added .env ignore rules to .gitignore")
    return True


def _read_env_file() -> List[str]:
    if not SECRETS_FILE.exists():
        return []
    try:
        return SECRETS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EnvWriteError(f"Could not read {SECRETS_FILE_LABEL}: {exc}") from exc


def _encode(key: str, value: str) -> str:
    """Render one KEY=VALUE line.

    Values are quoted so spaces, '#' and '$' survive a dotenv round-trip; an
    inline comment would otherwise truncate a key.
    """
    if _SAFE_VALUE.search(value):
        raise EnvWriteError(f"{key} contains a newline or NUL byte")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{key}="{escaped}"'


def write_values(values: Dict[str, Optional[str]]) -> List[str]:
    """Insert or replace keys in backend/.env. ``None`` removes the key.

    Returns the keys that changed. The caller is responsible for validating
    names and values first; this function only guarantees a well-formed file.
    """
    clean: Dict[str, Optional[str]] = {}
    for key, value in values.items():
        if not _KEY_RE.match(key or ""):
            raise EnvWriteError(f"Refusing to write an invalid key name: {key!r}")
        if value is not None and _SAFE_VALUE.search(value):
            raise EnvWriteError(f"Refusing to write {key}: value contains a newline")
        clean[key] = value

    if not clean:
        return []

    lines = _read_env_file()
    out: List[str] = []
    # Track which keys a real assignment line already covers.
    seen: Dict[str, int] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out.append(line)
            continue
        match = re.match(r"^([A-Z][A-Z0-9_]*)\s*=", stripped)
        if not match:
            out.append(line)
            continue
        key = match.group(1)
        if key not in clean:
            out.append(line)
            continue
        seen[key] = index
        # Replace in place so file order (and comments) stay intact.
        value = clean[key]
        out.append(line if value is None else _encode(key, value))

    appended: List[str] = []
    for key, value in clean.items():
        if key in seen or value is None:
            continue
        appended.append(_encode(key, value))

    if appended:
        if out and out[-1].strip():
            out.append("")
        out.append("# ---- Added from the Settings console ----")
        out.extend(appended)

    # Collapse the blank line a previous append may have left behind.
    while out and not out[-1].strip():
        out.pop()
    body = "\n".join(out) + "\n"
    _atomic_write(body)
    return sorted(k for k in clean if clean[k] is not None or k in seen)


def _atomic_write(body: str) -> None:
    try:
        SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        handle, tmp_name = tempfile.mkstemp(dir=str(SECRETS_FILE.parent), prefix=".env.", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as handle_obj:
                handle_obj.write(body)
                handle_obj.flush()
                os.fsync(handle_obj.fileno())
            # Keep credentials out of other users' reach where the OS allows it.
            try:
                os.chmod(tmp_name, 0o600)
            except OSError:
                pass
            os.replace(tmp_name, SECRETS_FILE)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        raise EnvWriteError(f"Could not write {SECRETS_FILE_LABEL}: {exc}") from exc


def read_keys() -> List[str]:
    """List the key names currently present in backend/.env (never the values)."""
    keys: List[str] = []
    for line in _read_env_file():
        match = re.match(r"^([A-Z][A-Z0-9_]*)\s*=", line.strip())
        if match:
            keys.append(match.group(1))
    return keys


def is_gitignored() -> bool:
    """Best-effort check that the secrets file will not be committed."""
    path = _gitignore_path()
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        return False
    if "backend/.env" not in text:
        return False
    # Make sure no later negation re-includes it.
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("!") and stripped.lstrip("!").strip() in ("backend/.env", ".env", "*.env"):
            return False
    return True
