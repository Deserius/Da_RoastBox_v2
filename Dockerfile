# One public service: build React, then serve it and /api from FastAPI.
# Build args below are public frontend settings, never provider credentials.
FROM node:22.23.4-bookworm-slim AS frontend-build
WORKDIR /app/frontend
RUN corepack enable
COPY frontend/package.json frontend/yarn.lock ./
RUN yarn install --frozen-lockfile --ignore-engines --non-interactive
COPY frontend/ ./
ARG REACT_APP_BACKEND_URL=""
ARG REACT_APP_ENABLE_PREVIEW_LOGIN="false"
ARG REACT_APP_SOURCE_DOWNLOAD_ENABLED="false"
ARG REACT_APP_ENABLE_SESSION_TUNNEL="false"
ARG REACT_APP_SUPPORT_EMAIL=""
ARG REACT_APP_INSTAGRAM_URL=""
ARG REACT_APP_FACEBOOK_URL=""
ARG REACT_APP_TIKTOK_URL=""
ARG REACT_APP_YOUTUBE_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL \
    REACT_APP_ENABLE_PREVIEW_LOGIN=$REACT_APP_ENABLE_PREVIEW_LOGIN \
    REACT_APP_SOURCE_DOWNLOAD_ENABLED=$REACT_APP_SOURCE_DOWNLOAD_ENABLED \
    REACT_APP_ENABLE_SESSION_TUNNEL=$REACT_APP_ENABLE_SESSION_TUNNEL \
    REACT_APP_SUPPORT_EMAIL=$REACT_APP_SUPPORT_EMAIL \
    REACT_APP_INSTAGRAM_URL=$REACT_APP_INSTAGRAM_URL \
    REACT_APP_FACEBOOK_URL=$REACT_APP_FACEBOOK_URL \
    REACT_APP_TIKTOK_URL=$REACT_APP_TIKTOK_URL \
    REACT_APP_YOUTUBE_URL=$REACT_APP_YOUTUBE_URL \
    GENERATE_SOURCEMAP=false CI=true NODE_OPTIONS=--max-old-space-size=768
RUN yarn build

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    FRONTEND_BUILD_DIR=/app/frontend/build \
    STORAGE_BACKEND=vercel_blob \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    REEL_ENCODER_PRESET=ultrafast TMPDIR=/app/backend/media_tmp
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates gosu libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 roastbox
WORKDIR /app
COPY backend/requirements-runtime.txt /app/backend/requirements-runtime.txt
RUN python -m pip install --no-cache-dir -r /app/backend/requirements-runtime.txt
COPY --chown=roastbox:roastbox backend/ /app/backend/
COPY --from=frontend-build --chown=roastbox:roastbox /app/frontend/build /app/frontend/build
COPY deploy/entrypoint.sh /app/deploy/entrypoint.sh
RUN chmod 755 /app/deploy/entrypoint.sh && mkdir -p /app/backend/audio_cache /app/backend/media_tmp \
    && chown -R roastbox:roastbox /app/backend
WORKDIR /app/backend
EXPOSE 10000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
# Exactly one worker; see docs/DEPLOYMENT.md before changing this.
CMD ["sh", "-c", "exec python -m uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
