# Reels: actual encoding, private delivery and Free limits

## User flow

Use a completed owned show → Reels → **30s max** or **60s max**. These are budgets with whole-line selection, not a promise that every clip is exactly 30/60 seconds. The app queues the job, polls its status, opens a completed video and offers one-click **Download MP4**. The download handler waits for authenticated bytes and automatically starts the local file save; it is not a fake success toast.

The tested standalone browser harness confirms MP4 bytes are downloaded, on desktop and a mobile viewport. Third-party iframe download permissions, physical Samsung/other devices and native Windows remain separate acceptance work. Browser emulation is not those proofs.

## Implementation

- `backend/routes/reels.py`: owner/entitlement/price checks, one-time billing/refund markers, pending/running/done/failed status, lease/CAS recovery, private photo/video routes.
- `backend/services/highlight_reel.py`: actual 1080×1920 H.264/AAC composition, comic/guest visuals, readable wrapped captions, motion, voice-first crowd mix and complete selected lines.
- `frontend/src/components/ReelButton.jsx`: create/status/retry/check progress, prior exports, view, authenticated media fetch, automatic MP4 save and error/rebuild controls.

A 120s lease with 20s heartbeat and compare-and-set recovery prevents known overlapping stale-worker refund paths. The single-process shared capacity bounds heavy operations; one Uvicorn worker is required. Prefetch/network/multiuser conditions are not fully modeled by the local probe. Recovery only runs while awake; Free sleep/restart can interrupt work. This is not an external durable queue or end-to-end idempotency guarantee.

## Free memory/codec configuration

Renderer style: `theater-v8-21plus-bounded-memory`.

- Separate serial float-PCM voice/crowd buses and final limiter rather than an unbounded all-input video graph.
- Explicit photo/cache cleanup and Linux native-heap trim between heavy capacity slots.
- Single-thread encode/filter/decode settings, CRF 20, zerolatency, one reference, no B-frames/lookahead.
- `REEL_ENCODER_PRESET=ultrafast` in Docker/Render. Native missing setting defaults to veryfast; allowed presets are ultrafast/superfast/veryfast, but only ultrafast has current constrained Free evidence.
- Disposable Docker `TMPDIR=/app/backend/media_tmp` is created/owned before the non-root process starts. It is **not persistent customer storage**. Test intermediates use excluded workspace disk to avoid accumulated tmpfs distortion.

Do not raise/remove the 480 MiB workload guard, add Uvicorn workers or change the codec and keep claiming the previous result.

## Actual offline measurements

`python scripts/benchmark_free.py` launches only a new guarded test process group, blocks providers/network/non-test databases, imports the API, serially normalizes four 25MP photos and encodes bundled noncustomer audio into both budgets. Linux `/proc` samples API/media/FFmpeg process-tree RSS every 25ms. The standalone offline coordinator is reported separately, not deployed or silently counted as zero.

Passing run: **470.2 MiB API/media workload**, **483.4 MiB total including coordinator**, 38.25s (prior consecutive passes: 469.7/482.9 and 468.9/482.2 MiB) combined local wall time, unchanged 480 MiB workload stop guard.

| Budget | Actual synthetic output | Bytes |
| --- | --- | --- |
| 30s max | 22.6s, 1080×1920 H.264/AAC | 27,627,633 |
| 60s max | 53.1s, 1080×1920 H.264/AAC | 66,052,033 |

Both were fully decoded and motion-checked. This is **not real AI speech, Render CPU/cgroup/whole-service memory, cold-start/concurrent-user, worst-case photo entropy or provider/storage validation**. Earlier other-preset runs failed the guard; an overlapping build run timed out under local memory/tmpfs pressure. A passing synthetic run does not make Free hosting production-ready.

## Durable media and quotas

Release stores completed bytes in the approved private remote store before marking success; a local-only save is not accepted as durable. Owner-authenticated video GET/HEAD and download routes serve it. Share links use dedicated revocable share-scoped media, not public buckets.

Ultrafast lowers encode memory but produces large files. A ~66 MB example consumes a material part of a 1GB free store and transfer allowance; repeated views and authenticated proxy delivery also consume quotas. Confirm current plan eligibility/billing controls and keep beta closed if limits are incompatible. Do not erase historical media, publish it publicly or start a paid tier/trial as an unapproved fix.

Existing completed reels/audio/photos are not rewritten by this renderer update. Source ZIP excludes customer generated files. See [DATA_PRESERVATION.md](DATA_PRESERVATION.md), [operations](OPERATIONS_RUNBOOK.md) and [Free deployment](RENDER_DEPLOYMENT.md).
