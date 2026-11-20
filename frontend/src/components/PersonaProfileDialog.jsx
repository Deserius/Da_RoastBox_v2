import { useCallback, useEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Headphones, LoaderCircle, Play, Square, X } from "lucide-react";
import api from "@/lib/api";
import { mediaObjectUrl } from "@/lib/media";
import { useAuth } from "@/lib/AuthContext";
import { PersonaFavoriteButton } from "@/components/PersonaFavoriteButton";
import { watchNarration } from "@/lib/audioFocus";

export const PersonaProfileDialog = ({ persona: p, onClose, onPick, pickLabel, returnFocus }) => {
  const { user } = useAuth();
  const [playback, setPlayback] = useState({ index: -1, state: "idle" });
  const [error, setError] = useState("");
  const audioRef = useRef(null);
  const unwatchRef = useRef(null);
  const urlRef = useRef("");
  const abortRef = useRef(null);
  const sequence = useRef(0);
  const mounted = useRef(false);
  const samples = p.punchlines?.length ? p.punchlines : (p.tagline ? [p.tagline] : []);

  const release = useCallback(() => {
    sequence.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    if (audioRef.current) {
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current.pause();
      audioRef.current = null;
    }
    unwatchRef.current?.();
    unwatchRef.current = null;
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = "";
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; release(); };
  }, [release]);

  // Call play() synchronously on a retry tap: Android can reject autoplay after
  // an async sample fetch even though the original button was tapped.
  const playLoaded = async (index, run) => {
    try {
      await audioRef.current.play();
      if (mounted.current && sequence.current === run) {
        setPlayback({ index, state: "playing" });
        setError("");
      }
    } catch (e) {
      if (!mounted.current || sequence.current !== run) return;
      if (e?.name === "NotAllowedError" && audioRef.current && urlRef.current) {
        setPlayback({ index, state: "blocked" });
        setError("Your browser needs one more tap. Tap this sample again to play it.");
        return;
      }
      release();
      setPlayback({ index: -1, state: "idle" });
      setError("Couldn't play that sample. Please try again.");
    }
  };

  const playSample = async (index) => {
    if (playback.index === index && playback.state === "playing") {
      release();
      setPlayback({ index: -1, state: "idle" });
      setError("");
      return;
    }
    if (playback.index === index && playback.state === "blocked" && audioRef.current) {
      // Keep the already-fetched audio; this retry makes no new voice request.
      playLoaded(index, sequence.current);
      return;
    }
    release();
    const run = sequence.current;
    const abort = new AbortController();
    abortRef.current = abort;
    setPlayback({ index, state: "loading" });
    setError("");
    try {
      const { data } = await api.get(`/personas/${encodeURIComponent(p.id)}/voice-preview`, {
        params: { sample: index }, signal: abort.signal, timeout: 120000,
      });
      const url = await mediaObjectUrl(data.audio_url, abort.signal);
      if (!mounted.current || sequence.current !== run) { URL.revokeObjectURL(url); return; }
      urlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;
      unwatchRef.current = watchNarration(audio);
      audio.onended = () => {
        if (mounted.current && sequence.current === run) {
          release();
          setPlayback({ index: -1, state: "idle" });
        }
      };
      audio.onerror = () => {
        if (mounted.current && sequence.current === run) {
          release();
          setPlayback({ index: -1, state: "idle" });
          setError("Couldn't play that sample. Check your connection and try again.");
        }
      };
      await playLoaded(index, run);
    } catch (e) {
      if (!mounted.current || abort.signal.aborted || sequence.current !== run) return;
      release();
      setPlayback({ index: -1, state: "idle" });
      const detail = e?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Couldn't play that sample. Please try again.");
    }
  };

  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="persona-modal-overlay" />
        <Dialog.Content className="persona-profile" data-testid="persona-detail-modal" style={{ "--persona-color": "var(--accent-alt)" }}
          onCloseAutoFocus={(event) => { if (returnFocus?.current?.isConnected) { event.preventDefault(); returnFocus.current.focus(); } }}>
          <Dialog.Close asChild>
            <button type="button" className="persona-profile-close" aria-label="Close persona profile" data-testid="persona-detail-close-btn"><X size={20} /></button>
          </Dialog.Close>
          <div className="persona-profile-hero">
            <img className="persona-profile-portrait" src={`/${p.image}`} alt="" />
            <div className="persona-profile-heading">
              <div className="persona-eyebrow"><span /> THE ROASTER PROFILE</div>
              <Dialog.Title asChild><h2 data-testid="persona-detail-name">{p.displayName || p.name}</h2></Dialog.Title>
              <Dialog.Description className="persona-profile-meta">
                {p.role}{p.age ? ` · Age ${p.age}` : ""} · {p.is_premium ? "Premium" : "Free"}
              </Dialog.Description>
              {p.tagline && <p className="persona-profile-tagline">“{p.tagline}”</p>}
              <PersonaFavoriteButton persona={p} inModal />
            </div>
          </div>
          <div className="persona-profile-body">
            <section>
              <div className="persona-section-label">THE BIO</div>
              <p className="persona-profile-copy">{p.description || "A Da RoastBox original with a style all their own."}</p>
              {p.comic_inspiration && <p className="persona-inspiration">Comedy inspiration <strong>{p.comic_inspiration}</strong></p>}
            </section>
            <section>
              <div className="persona-section-heading">
                <div><div className="persona-section-label">SAMPLE JOKES</div><p>Tap a line to hear their voice.</p></div>
                <Headphones aria-hidden="true" size={20} />
              </div>
              <div className="persona-sample-list">
                {samples.map((line, index) => {
                  const active = playback.index === index;
                  const loading = active && playback.state === "loading";
                  const playing = active && playback.state === "playing";
                  const blocked = active && playback.state === "blocked";
                  return (
                    <div key={`${index}-${line}`} data-testid={`persona-sample-${index}`}>
                      <button type="button" className={`persona-sample ${playing ? "is-playing" : ""}`} onClick={() => playSample(index)} disabled={loading}
                        aria-label={`${playing ? "Stop" : blocked ? "Tap to play" : "Play"} sample ${index + 1} for ${p.displayName || p.name}`}
                        data-testid={index === 0 ? "persona-voice-preview-btn" : `persona-voice-preview-${index}`}>
                        <span className="persona-sample-play" aria-hidden="true">
                          {loading ? <LoaderCircle className="persona-spin" size={17} /> : playing ? <Square size={14} fill="currentColor" /> : <Play size={16} fill="currentColor" />}
                        </span>
                        <span className="persona-sample-copy"><span className="persona-sample-number">{loading ? "WARMING UP" : playing ? "NOW PLAYING" : blocked ? "TAP TO PLAY" : `SAMPLE ${index + 1}`}</span>
                          <span className="persona-sample-quote">“{line}”</span></span>
                      </button>
                    </div>
                  );
                })}
              </div>
              {error && <p role="alert" className="persona-audio-error">{error}</p>}
              <p className="persona-audio-note">{user?.is_preview
                ? "New voice samples use the shared daily preview limit; cached samples can be replayed."
                : "Voice samples are generated on first play, then cached for replay."}</p>
            </section>
            {!!p.topics?.length && <section><div className="persona-section-label">TOPICS THEY HIT</div>
              <div className="persona-profile-chips">{p.topics.map((topic) => <span key={topic}>{topic}</span>)}</div></section>}
            {!!p.lingo?.length && <section><div className="persona-section-label">SIGNATURE LINGO</div>
              <div className="persona-profile-chips muted">{p.lingo.map((word) => <span key={word}>{word}</span>)}</div></section>}
          </div>
          <div className="persona-profile-actions">
            <button type="button" className="btn-primary" onClick={() => onPick(p)} data-testid="persona-detail-pick-btn">{pickLabel || "Roast with them"}</button>
            <Dialog.Close asChild><button type="button" className="btn-ghost">Close</button></Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
