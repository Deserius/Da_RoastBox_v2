"""Optional same-origin production hosting for the compiled React frontend.

The API remains the only handler for /api. Client-side routes fall back to the
SPA shell, while missing files remain 404s instead of returning HTML as JS/audio.
"""
from pathlib import PurePosixPath

from starlette.exceptions import HTTPException
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        # A root mount must never turn an unknown API path into a successful SPA.
        if path == "api":
            return RedirectResponse("/api/", status_code=307)
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if (exc.status_code != 404 or scope.get("method") not in {"GET", "HEAD"}
                    or PurePosixPath(path).suffix):
                raise
            response = await super().get_response("index.html", scope)
        # The app shell references hashed bundles. Ensure a deploy's new shell
        # is revalidated rather than holding old bundle names indefinitely.
        if path in ("", ".", "index.html") or response.media_type == "text/html":
            response.headers["Cache-Control"] = "no-cache"
        return response
