#!/usr/bin/env python3
"""Create safe local .env files without overwriting existing configuration."""
import argparse
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--preview", action="store_true", help="enable isolated demo login and local media storage")
args = parser.parse_args()

for part in ("backend", "frontend"):
    sample, target = ROOT / part / ".env.example", ROOT / part / ".env"
    if target.exists():
        print(f"Kept existing {target.relative_to(ROOT)} (not overwritten)")
        continue
    text = sample.read_text()
    if part == "backend":
        text = text.replace("JWT_SECRET=\n", f"JWT_SECRET={secrets.token_urlsafe(48)}\n")
        if args.preview:
            text = text.replace("DB_NAME=da_roastbox\n", "DB_NAME=da_roastbox_preview\n")
            text = text.replace("STORAGE_BACKEND=emergent\n", "STORAGE_BACKEND=local\n")
            text = text.replace("ENABLE_PREVIEW_LOGIN=false\n", "ENABLE_PREVIEW_LOGIN=true\n")
    elif args.preview:
        text = text.replace("REACT_APP_ENABLE_PREVIEW_LOGIN=false\n", "REACT_APP_ENABLE_PREVIEW_LOGIN=true\n")
    target.write_text(text)
    target.chmod(0o600)
    print(f"Created {target.relative_to(ROOT)}")

if args.preview:
    print("Preview accounts are isolated test accounts with non-purchasable demo credits; disable before production.")
