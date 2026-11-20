# Deployment entry points — current target is Render Free

The previous paid Render/disk recipe is superseded. **Do not select a paid instance, persistent disk, trial or paid worker for this beta.**

- **[Complete current Render guide](RENDER_DEPLOYMENT.md)**
- [Required/optional/unnecessary variables](ENVIRONMENT.md)
- [Data preservation and explicit owner-only copy tools](DATA_PRESERVATION.md)
- [Readiness and remaining external gates](RELEASE_READINESS.md)

## Exact runtime

Repository root: `render.yaml` + `Dockerfile`.

The Dockerfile builds React with Node 22.23.4, installs `backend/requirements-runtime.txt` into Python 3.13, bundles FFmpeg through the locked dependency, and copies only the compiled frontend into the runtime image. Provider credentials are runtime secrets, never build args.

`deploy/entrypoint.sh` drops privileges using `gosu`. Backend working directory: `/app/backend`.

```sh
exec python -m uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1
```

`server:app` is `backend/server.py`; it includes all API routers under `/api`, then mounts `FRONTEND_BUILD_DIR=/app/frontend/build` as the SPA. Health check: `/api/ready` (Mongo only, no paid probes). No separate frontend hosting/service or Mongo process in this container.

Public frontend settings: same-origin blank `REACT_APP_BACKEND_URL`, Explore true for this protected beta, source-download false and session-tunnel false. Rebuild when those change.

## Native installation stays separate

`LAUNCH_DA_ROASTBOX.bat` is the prominent Windows double-click entry (`start.bat` remains equivalent). Installer 1.2.2 adds verified Python bootstrapping without winget and retains the richer 1.2.1 storage safeguards. Keep the authoritative native `backend\.env`, database and richer source. Do not overlay this recovered package onto that installation without a separately reviewed backup/diff. Linux dependency probes and browser emulation are not Windows double-click or physical-device certification.

No original local services were restarted to make this handoff and no cloud deployment or authoritative-data transfer is claimed.
