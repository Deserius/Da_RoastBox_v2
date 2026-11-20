import { useEffect, useRef, useState } from "react";
import { Volume2, VolumeX } from "lucide-react";

// The sign-in screen's atmosphere: an original instrumental loop with a hype
// "Welcome to the RoastBox!" call once per 30-second loop. Browsers only allow
// sound after a user gesture, so playback is attempted immediately and, if it
// is blocked, resumed on the visitor's first click, tap or key press.
const BEAT = "/assets/intro/roastbox-landing-beat.mp3";
const WELCOMES = [
  "/assets/intro/roastbox-welcome-1.mp3",
  "/assets/intro/roastbox-welcome-2.mp3",
  "/assets/intro/roastbox-welcome-3.mp3",
];
const BEAT_VOLUME = 0.32;
const DUCKED_VOLUME = 0.12;
const WELCOME_VOLUME = 0.9;
const WELCOME_EVERY_MS = 30000; // One loop of the beat.
const STORAGE_KEY = "roastbox.landing-audio";

function initialMuted() {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "off") return true;
    if (stored === "on") return false;
  } catch { /* Private mode or storage disabled. */ }
  // Motion-sensitive visitors get the control, not an unexpected soundtrack.
  return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

export default function LandingAudio({ active = true }) {
  const beatRef = useRef(null);
  const voiceRef = useRef(null);
  const indexRef = useRef(0);
  const [muted, setMuted] = useState(initialMuted);
  const [blocked, setBlocked] = useState(false);

  useEffect(() => {
    if (!active || muted) return undefined;
    const beat = beatRef.current;
    const voice = voiceRef.current;
    if (!beat || !voice) return undefined;
    beat.volume = BEAT_VOLUME;
    voice.volume = WELCOME_VOLUME;
    let cancelled = false;
    let timer = 0;
    let restore = 0;

    const playVoice = () => {
      if (cancelled) return;
      const track = WELCOMES[indexRef.current % WELCOMES.length];
      indexRef.current += 1;
      voice.src = track;
      // Duck the beat so the announcement lands, then bring the bed back.
      beat.volume = DUCKED_VOLUME;
      const attempt = voice.play();
      const done = () => {
        if (cancelled) return;
        window.clearTimeout(restore);
        restore = window.setTimeout(() => { if (!cancelled) beat.volume = BEAT_VOLUME; }, 2600);
      };
      if (attempt?.then) attempt.then(() => { setBlocked(false); done(); }).catch(done);
      else done();
    };

    const start = () => {
      if (cancelled) return;
      const attempt = beat.play();
      if (attempt?.then) {
        attempt.then(() => { if (!cancelled) setBlocked(false); })
          .catch(() => { if (!cancelled) setBlocked(true); });
      }
      window.clearTimeout(timer);
      // Greet on arrival, then once per loop.
      timer = window.setTimeout(() => {
        playVoice();
        timer = window.setInterval(playVoice, WELCOME_EVERY_MS);
      }, 900);
    };

    const onGesture = () => {
      window.removeEventListener("pointerdown", onGesture);
      window.removeEventListener("keydown", onGesture);
      window.removeEventListener("touchstart", onGesture);
      start();
    };
    start();
    // If the browser refused the first attempt, wait for a real gesture.
    window.addEventListener("pointerdown", onGesture);
    window.addEventListener("keydown", onGesture);
    window.addEventListener("touchstart", onGesture);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      window.clearInterval(timer);
      window.clearTimeout(restore);
      window.removeEventListener("pointerdown", onGesture);
      window.removeEventListener("keydown", onGesture);
      window.removeEventListener("touchstart", onGesture);
      beat.pause();
      voice.pause();
    };
  }, [active, muted]);

  const toggle = () => {
    setMuted((value) => {
      const next = !value;
      try { window.localStorage.setItem(STORAGE_KEY, next ? "off" : "on"); } catch { /* Ignore. */ }
      if (next) setBlocked(false);
      return next;
    });
  };

  if (!active) return null;
  return (
    <div className="landing-audio" data-testid="landing-audio" data-muted={muted ? "true" : "false"} data-blocked={blocked ? "true" : "false"}>
      <audio ref={beatRef} src={BEAT} loop preload="auto" data-testid="landing-beat" />
      <audio ref={voiceRef} preload="auto" data-testid="landing-welcome" />
      <button type="button" className="landing-audio-btn" onClick={toggle}
        aria-pressed={!muted} data-testid="landing-audio-toggle"
        title={muted ? "Turn lobby sound on" : "Mute lobby sound"}>
        {muted ? <VolumeX size={16} aria-hidden="true" /> : <Volume2 size={16} aria-hidden="true" />}
        <span>{muted ? "Sound off" : "Sound on"}</span>
      </button>
      {blocked && !muted && <span className="landing-audio-hint">Tap anywhere for sound</span>}
    </div>
  );
}
