"""Shared preview session so scripts reuse one account (and its roasts)."""
from pathlib import Path
TOKEN_FILE = Path(__file__).resolve().parents[1] / ".cache" / "preview-session"


def token(base="http://127.0.0.1:8001/api"):
    import httpx
    if TOKEN_FILE.exists():
        value = TOKEN_FILE.read_text().strip()
        if value:
            with httpx.Client(base_url=base, timeout=30.0) as c:
                ok = c.get("/auth/me", headers={"X-Roastbox-Session": value}).status_code == 200
            if ok:
                return value
    with httpx.Client(base_url=base, timeout=30.0) as c:
        value = c.post("/auth/preview-login").json()["session_token"]
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(value)
    TOKEN_FILE.chmod(0o600)
    return value


def client(base="http://127.0.0.1:8001/api", timeout=600.0):
    import httpx
    c = httpx.Client(base_url=base, timeout=timeout)
    c.headers["X-Roastbox-Session"] = token(base)
    return c
