"""Resolve the backend base URL for API tests: env var first, then frontend/.env."""
import os
from pathlib import Path


def _resolve() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
        for line in env_file.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                url = line.split("=", 1)[1].strip().strip('"')
    if not url:
        raise RuntimeError("REACT_APP_BACKEND_URL not set")
    return url.rstrip("/")


BASE_URL = _resolve()
API = f"{BASE_URL}/api"
