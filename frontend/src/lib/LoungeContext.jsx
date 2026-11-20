import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Music2, Pause, Play, Volume2 } from "lucide-react";
import { subscribeAudioFocus } from "@/lib/audioFocus";
import "@/styles/lounge.css";

const LoungeContext = createContext(null);

export function LoungeProvider({ children }) {
  const audioRef = useRef(null);
  const wantedRef = useRef(false);
  const focusRef = useRef(false);
  const [wanted, setWanted] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [focused, setFocused] = useState(false);
  const [volume, setVolume] = useState(.22);
  const [blocked, setBlocked] = useState(false);

  const playAudio = () => {
    const audio = audioRef.current;
    if (!audio || !wantedRef.current || focusRef.current || document.hidden) return;
    const attempt = audio.play();
    if (attempt?.then) attempt.then(() => setBlocked(false)).catch(() => setBlocked(true));
  };
  useEffect(() => {
    const audio = audioRef.current;
    const unsubscribe = subscribeAudioFocus((active) => {
      focusRef.current = active; setFocused(active);
      if (active) audio?.pause();
      else playAudio();
    });
    const visibility = () => { if (document.hidden) audio?.pause(); else playAudio(); };
    document.addEventListener("visibilitychange", visibility);
    return () => { unsubscribe(); document.removeEventListener("visibilitychange", visibility); audio?.pause(); };
  }, []); // The refs always hold the current intent and focus.
  useEffect(() => { if (audioRef.current) audioRef.current.volume = volume; }, [volume]);

  const toggle = () => {
    if (wantedRef.current && (playing || focused)) {
      wantedRef.current = false; setWanted(false); setBlocked(false); audioRef.current?.pause();
    } else {
      wantedRef.current = true; setWanted(true); setBlocked(false);
      // Invoked directly in the click handler to respect mobile autoplay policy.
      playAudio();
    }
  };
  return (
    <LoungeContext.Provider value={{ wanted, playing, focused, blocked, volume, setVolume, toggle }}>
      {children}
      <audio ref={audioRef} src="/assets/intro/roastbox-lounge-original.mp3" preload="none" loop
        onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onError={() => setBlocked(true)} />
    </LoungeContext.Provider>
  );
}

export function LoungeControl({ compact = false }) {
  const { wanted, playing, focused, blocked, volume, setVolume, toggle } = useContext(LoungeContext);
  const label = wanted && focused ? "Lounge paused for narration" : playing ? "Lounge music playing" : "Lounge music off";
  return (
    <div className={`lounge-control ${compact ? "lounge-compact" : ""}`} data-testid="lounge-control">
      <button type="button" onClick={toggle} aria-pressed={wanted} className="lounge-toggle" data-testid="lounge-toggle"
        aria-label={wanted && (playing || focused) ? "Pause lounge music" : "Play lounge music"}>
        <span className="lounge-icon"><Music2 size={16} aria-hidden="true" /></span>
        <span><strong>THE LOUNGE</strong><small>{label}</small></span>
        {playing ? <Pause size={15} aria-hidden="true" /> : <Play size={15} aria-hidden="true" />}
      </button>
      {wanted && !compact && <label className="lounge-volume"><Volume2 size={15} aria-hidden="true" /><span className="lounge-sr-only">Lounge music volume</span>
        <input type="range" min="0" max="0.6" step="0.02" value={volume} onChange={(event) => setVolume(Number(event.target.value))} data-testid="lounge-volume" />
      </label>}
      {blocked && <p className="lounge-note" role="status">Tap the music button to resume audio.</p>}
    </div>
  );
}
