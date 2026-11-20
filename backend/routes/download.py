"""Project source download (zip of /app)."""
import io
import os
import zipfile
from pathlib import Path
from fastapi import APIRouter, HTTPException
from config import ALLOW_SOURCE_DOWNLOAD
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/download", tags=["download"])

APP_ROOT = Path(__file__).resolve().parents[2]

# Folders/files to skip when zipping (heavy or sensitive)
EXCLUDE_DIR_NAMES = {
    "node_modules", ".git", "__pycache__", "venv", ".venv", "audio_cache",
    ".cache", ".yarn", ".next", "dist", "build", ".pytest_cache",
    ".data", ".tools", "local_storage", ".emergent", ".ruff_cache", "memory", "test_reports",
}
EXCLUDE_FILE_NAMES = {".DS_Store", "test_result.md", "test_credentials.md", ".netrc", ".npmrc", ".pypirc"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log", ".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db", ".zip"}


@router.get("/source.zip")
async def download_source():
    if not ALLOW_SOURCE_DOWNLOAD:
        raise HTTPException(status_code=404, detail="Not found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(APP_ROOT):
            # mutate dirs in-place to prune
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_NAMES]
            rel_root = Path(root).relative_to(APP_ROOT)
            for fname in files:
                full = Path(root) / fname
                lowered = fname.lower()
                if (fname in EXCLUDE_FILE_NAMES or full.is_symlink() or full.suffix.lower() in EXCLUDE_SUFFIXES or
                        lowered.startswith(".env") or "token.json" in lowered or "credentials.json" in lowered):
                    continue
                # Skip huge files (>5MB) except known important assets
                try:
                    if full.stat().st_size > 5 * 1024 * 1024:
                        continue
                except OSError:
                    continue
                arc = Path("da_roastbox") / rel_root / fname
                try:
                    zf.write(full, arcname=str(arc))
                except Exception:
                    continue

        # Include the checked-in templates, never the private .env files.
        for part in ("backend", "frontend"):
            example = APP_ROOT / part / ".env.example"
            if example.exists():
                zf.write(example, arcname=f"da_roastbox/{part}/.env.example")

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="da_roastbox_source.zip"'},
    )
