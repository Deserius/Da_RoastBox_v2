import { useCallback, useEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import api from "@/lib/api";
import { mediaBlob, saveMediaBlob } from "@/lib/media";
import { useAuth } from "@/lib/AuthContext";
import { useToast } from "@/lib/ToastContext";
import { claimAudioFocus, releaseAudioFocus } from "@/lib/audioFocus";

const ACTIVE = new Set(["charging", "queued", "rendering"]);
const errorDetail = (error, fallback) => typeof error?.response?.data?.detail === "string"
  ? error.response.data.detail : fallback;
const fileSize = (bytes) => `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
const filenameFor = (reel) => reel.filename || `da-roastbox-${reel.length || 60}s-${reel.id.slice(0, 8)}.mp4`;

// Durable, owner-authenticated 1080x1920 MP4 exports. Leaving the page never
// cancels a server render, and reopening a show restores its saved exports.
export const ReelButton = ({ roastId, prepaid = false, autoOpen = false }) => {
  const { refresh } = useAuth();
  const { toast } = useToast();
  const [reel, setReel] = useState(null);
  const [saved, setSaved] = useState([]);
  const [restoring, setRestoring] = useState(true);
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const [restoreError, setRestoreError] = useState("");
  const [requesting, setRequesting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [choosing, setChoosing] = useState(false);
  const [open, setOpen] = useState(false);
  const [videoUrl, setVideoUrl] = useState("");
  const [videoBlob, setVideoBlob] = useState(null);
  const [videoError, setVideoError] = useState("");
  const [mediaAttempt, setMediaAttempt] = useState(0);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [pollNote, setPollNote] = useState("");
  const [pollAttempt, setPollAttempt] = useState(0);
  const epoch = useRef(0);
  const creating = useRef(false);
  const openOnReady = useRef(false);
  const downloadPending = useRef(null);
  const audioFocusOwner = useRef({});

  const remember = useCallback((data) => {
    setReel(data);
    setSaved((items) => [data, ...items.filter((item) => item.id !== data.id)]);
  }, []);

  useEffect(() => {
    const owner = audioFocusOwner.current;
    return () => releaseAudioFocus(owner);
  }, []);
  useEffect(() => { if (!open) releaseAudioFocus(audioFocusOwner.current); }, [open]);

  useEffect(() => {
    const version = ++epoch.current;
    const abort = new AbortController();
    creating.current = false;
    downloadPending.current = null;
    openOnReady.current = autoOpen;
    setReel(null); setSaved([]); setOpen(false); setChoosing(false);
    setRequesting(false); setRestoring(true); setRestoreError(""); setExportError("");
    setPollNote(""); setDownloadBusy(false);
    if (!roastId) { setRestoring(false); return undefined; }
    api.get(`/roast/${roastId}/reels`, { signal: abort.signal }).then(({ data }) => {
      if (epoch.current !== version) return;
      const items = data.reels || [];
      setSaved(items);
      // Resume an in-flight render first; otherwise offer the latest playable
      // export, even if it was created before this styling/version update.
      const latest = items.find((item) => ACTIVE.has(item.status))
        || items.find((item) => item.status === "done") || items[0] || null;
      setReel(latest);
      if (latest?.status === "done" && openOnReady.current) {
        setOpen(true); openOnReady.current = false;
      }
    }).catch((error) => {
      if (epoch.current === version && !abort.signal.aborted) {
        setRestoreError(errorDetail(error, "Couldn't check your saved reels. Retry before creating another export."));
      }
    }).finally(() => { if (epoch.current === version) setRestoring(false); });
    return () => { epoch.current = version + 1; abort.abort(); };
  }, [roastId, autoOpen, restoreAttempt]);

  useEffect(() => {
    if (!reel?.id || !ACTIVE.has(reel.status)) return undefined;
    let stopped = false;
    let timer;
    let failures = 0;
    let checks = 0;
    const abort = new AbortController();
    const check = async () => {
      try {
        const { data } = await api.get(`/reels/${reel.id}`, { signal: abort.signal });
        if (stopped) return;
        failures = 0;
        remember(data);
        if (data.status === "done") {
          setPollNote(""); setChoosing(false);
          if (openOnReady.current) { setOpen(true); openOnReady.current = false; }
          toast("Your HD reel is ready to watch and download.", "success");
          refresh();
          return;
        }
        if (["failed", "unavailable"].includes(data.status)) { refresh(); return; }
        if (++checks > 60) setPollNote("Still rendering. You can leave this page; your reel will be saved with this show.");
        else setPollNote("");
      } catch (error) {
        if (stopped) return;
        failures += 1;
        setPollNote(errorDetail(error, "Connection interrupted. Your render continues on the server; reconnecting…"));
        // Authorization/not-found failures need an explicit retry/login, not
        // an endless disabled button or a new chargeable generation request.
        if ([401, 403, 404].includes(error?.response?.status)) return;
      }
      if (!stopped) timer = setTimeout(check, Math.min(12000, 2500 + failures * 1500));
    };
    timer = setTimeout(check, 1000);
    return () => { stopped = true; clearTimeout(timer); abort.abort(); };
  }, [reel?.id, reel?.status, pollAttempt, remember, refresh, toast]);

  // Preload as soon as the render finishes, not only after opening the dialog.
  // Keep this URL alive when the dialog closes so it can be reopened/downloaded.
  useEffect(() => {
    setVideoUrl(""); setVideoBlob(null); setVideoError("");
    if (downloadPending.current && downloadPending.current !== reel?.id) {
      downloadPending.current = null; setDownloadBusy(false);
    }
    if (reel?.status !== "done" || !reel.video_url) return undefined;
    let active = true;
    let objectUrl;
    const abort = new AbortController();
    mediaBlob(reel.video_url, abort.signal).then(async (blob) => {
      const signature = await blob.slice(4, 8).text();
      if (signature !== "ftyp") throw new Error("The saved file is not a valid MP4. Rebuild this reel.");
      if (!active) return;
      objectUrl = URL.createObjectURL(new Blob([blob], { type: "video/mp4" }));
      setVideoBlob(blob); setVideoUrl(objectUrl);
      if (downloadPending.current === reel.id) {
        saveMediaBlob(blob, filenameFor(reel));
        downloadPending.current = null; setDownloadBusy(false);
        toast("MP4 download started.", "success");
      }
    }).catch((error) => {
      if (!active || abort.signal.aborted) return;
      setVideoError(errorDetail(error, error.message || "Couldn't load this reel. Retry or rebuild the MP4."));
      downloadPending.current = null; setDownloadBusy(false);
    });
    return () => { active = false; abort.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [reel?.id, reel?.status, reel?.video_url, mediaAttempt, toast]); // eslint-disable-line react-hooks/exhaustive-deps

  const download = () => {
    if (!reel || reel.status !== "done" || downloadBusy) return;
    if (videoBlob) {
      try { saveMediaBlob(videoBlob, filenameFor(reel)); toast("MP4 download started.", "success"); }
      catch { setVideoError("Couldn't start the download. Please retry."); }
      return;
    }
    // One click is enough even if the file is still loading. It will save as
    // soon as the authenticated MP4 fetch finishes, with no second link to find.
    downloadPending.current = reel.id;
    setDownloadBusy(true);
    if (videoError) setMediaAttempt((n) => n + 1);
  };

  const create = async (length, regenerate = false) => {
    if (creating.current) return;
    const version = epoch.current;
    creating.current = true;
    setRequesting(true); setExportError(""); setRestoreError(""); setPollNote("");
    setOpen(false); setChoosing(false); openOnReady.current = true;
    try {
      const { data } = await api.post(`/roast/${roastId}/reel`, { length, regenerate }, { timeout: 60000 });
      if (version !== epoch.current) return;
      remember(data);
      if (data.status === "done") { setOpen(true); openOnReady.current = false; }
      else toast(`Creating your ${length}s HD highlight reel. It will open when ready.`, "info");
      refresh();
    } catch (error) {
      if (version !== epoch.current) return;
      setExportError(errorDetail(error, "Couldn't confirm the export. Check saved reels before retrying."));
      // A lost response can hide a successfully queued server job. Recover it
      // through the read-only list endpoint instead of blindly posting again.
      if (!error?.response) setRestoreAttempt((n) => n + 1);
    } finally {
      if (version === epoch.current) { creating.current = false; setRequesting(false); }
    }
  };

  if (!roastId) return null;
  const busy = requesting || (reel && ACTIVE.has(reel.status));
  const done = reel?.status === "done";
  const failed = reel && ["failed", "unavailable"].includes(reel.status);
  const completed = saved.filter((item, index, items) => item.status === "done"
    && items.findIndex((other) => other.status === "done" && other.length === item.length) === index);
  const costHint = prepaid ? "" : " · up to 5 cr";

  return (
    <div className="reel-widget" data-testid="reel-widget">
      {restoring && <p className="reel-status" role="status">Checking saved reels…</p>}
      {restoreError && <p className="reel-error" role="alert">{restoreError} <button className="btn-ghost" onClick={() => setRestoreAttempt((n) => n + 1)}>Retry</button></p>}
      {exportError && <p className="reel-error" role="alert">{exportError}</p>}
      {completed.length > 1 && <div className="reel-saved" aria-label="Saved reel lengths">
        <span>Saved reels</span>
        {completed.map((item) => <button type="button" className="btn-ghost" key={item.id}
          aria-pressed={item.id === reel?.id} onClick={() => { remember(item); setChoosing(false); setOpen(true); }}
          data-testid={`reel-saved-${item.length}`}>{item.length}s</button>)}
      </div>}
      {busy && <div className="reel-progress" role="status" aria-live="polite" data-testid="reel-progress">
        <div><span className="spinner" /> {requesting ? "Starting export…" : `${reel.phase || "Creating your reel"} · ${reel.length || 60}s max`}</div>
        <progress max="100" value={reel?.progress || 0} aria-label="Reel export progress" />
        <small>{pollNote || "Keep browsing — this export is saved with your show."}</small>
        {!requesting && <button type="button" className="btn-ghost" onClick={() => setPollAttempt((n) => n + 1)} data-testid="reel-check-btn">Check progress</button>}
      </div>}
      {failed && !requesting && <div className="reel-error" role="alert" data-testid="reel-export-error">
        <p>{reel.error || "This reel didn't finish. You can retry the export."}</p>
        <button type="button" className="btn-secondary" onClick={() => create(reel.length || 60, true)} data-testid="reel-retry-btn">Retry {reel.length || 60}s reel</button>
        {reel.length === 30 && <button type="button" className="btn-ghost" onClick={() => create(60)}>Try 60s instead</button>}
      </div>}
      {done && !requesting && <Dialog.Root open={open} onOpenChange={setOpen}>
        <div className="reel-complete-actions">
          <Dialog.Trigger asChild><button type="button" className="btn-primary" data-testid="reel-view-btn">🎬 View {reel.length || ""}s Reel</button></Dialog.Trigger>
          <button type="button" className="btn-secondary" onClick={download} disabled={downloadBusy} data-testid="reel-download-direct-btn">{downloadBusy ? "Preparing MP4…" : "⬇ Download MP4"}</button>
          <button type="button" className="btn-ghost" onClick={() => setChoosing((value) => !value)} data-testid="reel-change-length">{choosing ? "Keep this reel" : "Another length"}</button>
        </div>
        <Dialog.Portal>
          <Dialog.Overlay className="modal-overlay reel-overlay" data-testid="reel-modal">
            <Dialog.Content className="modal reel-ready" data-testid="reel-ready">
              <Dialog.Title>🎬 Your {reel.length || ""}s highlight reel</Dialog.Title>
              <Dialog.Description className="reel-preview-hint">Vertical HD MP4 · {fileSize(videoBlob?.size || reel.size_bytes || 0)} · Tap play if autoplay is paused.</Dialog.Description>
              {videoUrl && <video key={videoUrl} src={videoUrl} controls autoPlay playsInline preload="auto" className="reel-video" data-testid="reel-video"
                onPlay={() => claimAudioFocus(audioFocusOwner.current)} onPause={() => releaseAudioFocus(audioFocusOwner.current)}
                onEnded={() => releaseAudioFocus(audioFocusOwner.current)} onError={() => { releaseAudioFocus(audioFocusOwner.current); setVideoError("Playback failed. Retry loading, or download the MP4 to play on your device."); }} />}
              {!videoUrl && !videoError && <p role="status"><span className="spinner" /> Loading your reel…</p>}
              {videoError && <div className="reel-error" role="alert" data-testid="reel-video-error">
                <p>{videoError}</p>
                <button type="button" className="btn-secondary" onClick={() => setMediaAttempt((n) => n + 1)} data-testid="reel-reload-video">Retry loading</button>
                <button type="button" className="btn-ghost" onClick={() => create(reel.length || 60, true)} data-testid="reel-rebuild-btn">Rebuild reel · no extra export charge</button>
              </div>}
              <div className="modal-actions">
                <button type="button" className="btn-primary" onClick={download} disabled={downloadBusy} data-testid="reel-download-btn">{downloadBusy ? "Preparing MP4…" : "⬇ Download MP4"}</button>
                <Dialog.Close asChild><button type="button" className="btn-ghost" data-testid="reel-close-btn">Close</button></Dialog.Close>
              </div>
            </Dialog.Content>
          </Dialog.Overlay>
        </Dialog.Portal>
      </Dialog.Root>}
      {!busy && !restoring && !restoreError && (!done || choosing) && <div className="reel-choice" data-testid="reel-choice">
        <span className="reel-choice-label">🎬 HD Reel{costHint}</span>
        <button type="button" className="btn-secondary" onClick={() => create(30)} aria-label="Export a reel up to 30 seconds" title="Up to 30 seconds" data-testid="reel-30-btn">30s max</button>
        <button type="button" className="btn-secondary" onClick={() => create(60)} aria-label="Export a reel up to 60 seconds" title="Up to 60 seconds" data-testid="reel-60-btn">60s max</button>
      </div>}
    </div>
  );
};
